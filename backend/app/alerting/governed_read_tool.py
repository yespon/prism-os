"""Read-only Policy PEP for the trusted incident diagnosis sandbox Tool."""

import asyncio
import os
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

from langchain.tools import ToolRuntime, tool

from app.alerting.governed_native_reads import governed_read_middleware as governed_read_middleware
from app.alerting.governed_native_reads import recorded_read
from app.alerting.governed_ticket import active_requester
from app.alerting.governed_ticket_tool import execution_matches_diagnosis_scope, ticket_canary_enabled, ticket_execution
from app.platform.audit.repository import AuditEventRepository
from app.platform.contracts import ActionContextInput, AuditEvent, PolicyRequest, hash_action_context, stable_platform_id
from app.platform.policy.evaluator import PolicyConfiguration, PolicyRule
from app.platform.policy.repository import PolicyDecisionRepository
from app.platform.policy.service import PolicyService
from deerflow.sandbox.tools import read_file_tool


def governed_read_file_tool(scope: dict[str, str]):
    """Override the built-in read_file only in a server-scoped diagnosis canary."""
    if not ticket_canary_enabled(scope["tenant_id"]):
        return None

    @tool("read_file", parse_docstring=True)
    async def read_file(
        runtime: ToolRuntime,
        description: str,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> str:
        """Read a sandbox text file after a durable read-only Policy decision.

        Args:
            description: Explain why you are reading the file.
            path: Absolute path to the sandbox file.
            start_line: Optional starting line, inclusive.
            end_line: Optional ending line, inclusive.
        """
        tenant_id = scope["tenant_id"]
        if not ticket_canary_enabled(tenant_id):
            raise PermissionError("governed read_file is disabled")
        context_identity = runtime.context or {}
        identity_keys = ("tenant_id", "user_id", "thread_id", "agent_id") if scope.get("agent_id") is not None else ("tenant_id", "user_id", "thread_id")
        if any(context_identity.get(key) != scope[key] for key in identity_keys):
            raise PermissionError("sandbox identity differs from trusted diagnosis scope")
        call_id = runtime.tool_call_id
        if not isinstance(call_id, str) or not call_id:
            raise PermissionError("trusted read_file Tool call ID required")
        if not await active_requester(tenant_id, scope["user_id"]):
            raise PermissionError("requester is no longer authorized")
        request_id = "read-" + sha256(f"{scope['thread_id']}:{call_id}".encode()).hexdigest()
        decisions = PolicyDecisionRepository()
        existing = await decisions.get_by_request(tenant_id, request_id)
        execution = existing.execution if existing else ticket_execution(scope)
        if not execution_matches_diagnosis_scope(execution, scope):
            raise PermissionError("diagnosis read identity changed")
        now = datetime.now(UTC)
        context = ActionContextInput(
            tenant_id=tenant_id, execution=execution, action="read_file", risk_class="read_only",
            resource_id=scope["incident_id"], parameters={
                "path_sha256": sha256(path.encode()).hexdigest(),
                "start_line": start_line, "end_line": end_line,
            },
        )
        request = PolicyRequest(
            tenant_id=tenant_id, request_id=request_id, execution=execution,
            action="read_file", risk_class="read_only", resource_id=scope["incident_id"],
            context_hash=hash_action_context(context), requested_at=now,
        )
        configuration = PolicyConfiguration(
            policy_id="aiops-read-file-m1",
            version=os.getenv("PRISMOS_GOVERNED_READ_POLICY_VERSION", "v1") or "v1",
            rules={"read_file": PolicyRule(risk_class="read_only", verdict="allow")},
        )
        decision = await PolicyService().evaluate_and_record(request, configuration, at=now)
        if decision.verdict != "allow" or decision.policy_version != configuration.version or now >= decision.expires_at:
            raise PermissionError("read_file denied by platform Policy")
        if not await active_requester(tenant_id, scope["user_id"]):
            raise PermissionError("requester authorization changed")
        with recorded_read(scope, call_id, path):
            result = await asyncio.to_thread(
                read_file_tool.func, runtime=runtime, description=description, path=path,
                start_line=start_line, end_line=end_line,
            )
        completed_at = datetime.now(UTC)
        await AuditEventRepository().append(AuditEvent(
            tenant_id=tenant_id,
            event_id=stable_platform_id("event", "read-file-result", f"{decision.decision_id}:{uuid4().hex}"),
            event_type="action.read_result", action="read_file",
            outcome="failed" if result.startswith("Error:") else "succeeded",
            execution=decision.execution, policy_decision_id=decision.decision_id,
            resource_id=scope["incident_id"], recorded_at=completed_at,
        ))
        return result

    return read_file
