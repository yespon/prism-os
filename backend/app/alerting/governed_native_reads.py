"""Carry server-verified diagnosis scope to shared native file primitives."""

import os
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

from langchain.agents.middleware import AgentMiddleware

from app.alerting.governed_ticket_tool import ticket_canary_enabled
from deerflow.runtime import ExecutionTrustError

_scope = ContextVar("prismos_governed_reader_scope", default=None)
_recorded = ContextVar("prismos_recorded_file_read", default=None)


def _key(scope, call_id, path):
    return (*(scope.get(k) for k in ("tenant_id", "user_id", "thread_id", "incident_id", "agent_id")), call_id, sha256(path.encode()).hexdigest())


@contextmanager
def recorded_read(scope, call_id, path):
    token = _recorded.set(_key(scope, call_id, path))
    try:
        yield
    finally:
        _recorded.reset(token)


def requires_governed_read(context, operation, path):
    frame = _scope.get()
    action = operation[0] if isinstance(operation, tuple) else operation
    if frame is None or action not in {"read", "read_bytes"}:
        return False
    scope, call_id = frame
    keys = ("tenant_id", "user_id", "thread_id", "agent_id") if scope.get("agent_id") is not None else ("tenant_id", "user_id", "thread_id")
    if any(context.get(k) != scope[k] for k in keys) or not isinstance(call_id, str) or not call_id or not ticket_canary_enabled(scope["tenant_id"]):
        raise ExecutionTrustError("Current governed reader identity or canary unavailable")
    return _recorded.get() != _key(scope, call_id, path)


async def guard_native_read(context, operation, path, callback):
    if not requires_governed_read(context, operation, path):
        return await callback()
    from app.alerting import governed_read_tool as reads

    scope, call_id = _scope.get()
    try:
        if not await reads.active_requester(scope["tenant_id"], scope["user_id"]):
            raise ExecutionTrustError("Current governed reader unavailable")
        action = operation[0] if isinstance(operation, tuple) else operation
        path_hash = sha256(path.encode()).hexdigest()
        request_id = "native-read-" + sha256(f"{scope['thread_id']}:{call_id}:{action}:{path_hash}".encode()).hexdigest()
        existing = await reads.PolicyDecisionRepository().get_by_request(scope["tenant_id"], request_id)
        execution = existing.execution if existing else reads.ticket_execution(scope)
        if not reads.execution_matches_diagnosis_scope(execution, scope):
            raise ExecutionTrustError("Governed read execution changed")
        now = datetime.now(UTC)
        context_input = reads.ActionContextInput(tenant_id=scope["tenant_id"], execution=execution, action="read_file", risk_class="read_only", resource_id=scope["incident_id"], parameters={"path_sha256": path_hash, "operation": action})
        request = reads.PolicyRequest(
            tenant_id=scope["tenant_id"], request_id=request_id, execution=execution, action="read_file", risk_class="read_only", resource_id=scope["incident_id"], context_hash=reads.hash_action_context(context_input), requested_at=now
        )
        configuration = reads.PolicyConfiguration(policy_id="aiops-read-file-m1", version=os.getenv("PRISMOS_GOVERNED_READ_POLICY_VERSION", "v1") or "v1", rules={"read_file": reads.PolicyRule(risk_class="read_only", verdict="allow")})
        decision = await reads.PolicyService().evaluate_and_record(request, configuration, at=now)
        if decision.verdict != "allow" or decision.policy_version != configuration.version or now >= decision.expires_at:
            raise ExecutionTrustError("Native read denied by current Policy")
        if not await reads.active_requester(scope["tenant_id"], scope["user_id"]):
            raise ExecutionTrustError("Governed reader authorization changed")

        async def outcome(value):
            await reads.AuditEventRepository().append(
                reads.AuditEvent(
                    tenant_id=scope["tenant_id"],
                    event_id=reads.stable_platform_id("event", "native-read-result", f"{decision.decision_id}:{uuid4().hex}"),
                    event_type="action.read_result",
                    action="read_file",
                    outcome=value,
                    execution=decision.execution,
                    policy_decision_id=decision.decision_id,
                    resource_id=scope["incident_id"],
                    recorded_at=datetime.now(UTC),
                )
            )

        with recorded_read(scope, call_id, path):
            try:
                result = await callback()
            except Exception:
                await outcome("failed")
                raise
        await outcome("failed" if result is None or isinstance(result, str) and result.startswith("Error:") else "succeeded")
        return result
    except Exception:
        raise ExecutionTrustError("Current governed read authorization or audit unavailable") from None


class GovernedReadMiddleware(AgentMiddleware):
    """Tool-call context is set by the trusted graph factory, never client JSON."""

    def __init__(self, scope):
        self.scope = dict(scope)

    def wrap_tool_call(self, request, handler):
        token = _scope.set((self.scope, request.tool_call.get("id")))
        try:
            return handler(request)
        finally:
            _scope.reset(token)

    async def awrap_tool_call(self, request, handler):
        token = _scope.set((self.scope, request.tool_call.get("id")))
        try:
            return await handler(request)
        finally:
            _scope.reset(token)


def governed_read_middleware(scope):
    return [GovernedReadMiddleware(scope)] if ticket_canary_enabled(scope["tenant_id"]) else []
