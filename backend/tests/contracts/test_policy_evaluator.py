import asyncio
from datetime import UTC, datetime

import pytest

from app.platform.contracts import ExecutionEnvelope, IdentityRef, PolicyRequest
from app.platform.policy.evaluator import PolicyConfiguration, PolicyEvaluator, PolicyRule, SafetySignals

NOW = datetime(2026, 9, 24, 10, 0, tzinfo=UTC)


def _request(action: str = "ticket.create", risk_class: str = "side_effect") -> PolicyRequest:
    execution = ExecutionEnvelope(
        tenant_id="tenant-a", task_id="task-1", run_id="run-1", correlation_id="alert-1",
        workload=IdentityRef(kind="workload", id="agent-1", tenant_id="tenant-a"),
        actor=IdentityRef(kind="user", id="user-1", tenant_id="tenant-a"), occurred_at=NOW,
    )
    return PolicyRequest(
        tenant_id="tenant-a", request_id="request-1", execution=execution,
        action=action, risk_class=risk_class, resource_id="incident-1",
        context_hash="a" * 64, requested_at=NOW,
    )


def _config(verdict: str = "require_approval") -> PolicyConfiguration:
    return PolicyConfiguration(
        policy_id="aio-ops-m1", version="v1",
        rules={
            "read_file": PolicyRule(risk_class="read_only", verdict="allow"),
            "ticket.create": PolicyRule(risk_class="side_effect", verdict=verdict),
        },
    )


@pytest.mark.anyio
@pytest.mark.parametrize("verdict", ["allow", "deny", "require_approval"])
async def test_explicit_rule_yields_three_branch_decision(verdict) -> None:
    result = await PolicyEvaluator().evaluate(_request(), _config(verdict), at=NOW)
    assert result.verdict == verdict
    assert result.policy_id == "aio-ops-m1"
    assert result.policy_version == "v1"
    assert result.context_hash == "a" * 64
    assert result.expires_at > result.decided_at


@pytest.mark.anyio
async def test_read_only_allow_requires_explicit_rule() -> None:
    allowed = await PolicyEvaluator().evaluate(_request("read_file", "read_only"), _config(), at=NOW)
    unknown = await PolicyEvaluator().evaluate(_request("other.read", "read_only"), _config(), at=NOW)
    assert allowed.verdict == "allow"
    assert unknown.verdict == "deny"
    assert unknown.reason_code == "policy.unconfigured_action"


@pytest.mark.anyio
async def test_missing_configuration_and_risk_mismatch_fail_closed() -> None:
    missing = await PolicyEvaluator().evaluate(_request(), None, at=NOW)
    misclassified = await PolicyEvaluator().evaluate(_request(risk_class="read_only"), _config("allow"), at=NOW)
    assert (missing.verdict, missing.reason_code) == ("deny", "policy.unconfigured")
    assert (misclassified.verdict, misclassified.reason_code) == ("deny", "policy.risk_mismatch")


@pytest.mark.anyio
async def test_safety_seeds_only_restrict_rules() -> None:
    async def blocked(_request):
        return SafetySignals(guardrail_allow=False, terminal_action="allow")

    async def asks(_request):
        return SafetySignals(guardrail_allow=True, terminal_action="ask")

    async def clear(_request):
        return SafetySignals(guardrail_allow=True, terminal_action="allow")

    evaluator = PolicyEvaluator()
    assert (await evaluator.evaluate(_request(), _config("allow"), blocked, at=NOW)).verdict == "deny"
    assert (await evaluator.evaluate(_request(), _config("allow"), asks, at=NOW)).verdict == "require_approval"
    assert (await evaluator.evaluate(_request(), _config("deny"), clear, at=NOW)).verdict == "deny"
    assert (await evaluator.evaluate(_request(), _config("allow"), clear, at=NOW)).verdict == "allow"


@pytest.mark.anyio
async def test_provider_failure_or_timeout_denies_even_explicit_allow() -> None:
    async def broken(_request):
        raise RuntimeError("secret provider detail")

    async def slow(_request):
        await asyncio.sleep(0.05)
        return SafetySignals()

    evaluator = PolicyEvaluator(provider_timeout_seconds=0.001)
    failed = await evaluator.evaluate(_request(), _config("allow"), broken, at=NOW)
    timed_out = await evaluator.evaluate(_request(), _config("allow"), slow, at=NOW)
    assert (failed.verdict, failed.reason_code) == ("deny", "policy.provider_error")
    assert (timed_out.verdict, timed_out.reason_code) == ("deny", "policy.provider_timeout")
    assert "secret" not in failed.model_dump_json()


def test_invalid_configuration_cannot_enable_side_effect_by_accident() -> None:
    with pytest.raises(ValueError, match="risk_class"):
        PolicyRule(risk_class="unknown", verdict="allow")
    with pytest.raises(ValueError, match="verdict"):
        PolicyRule(risk_class="side_effect", verdict="maybe")
    with pytest.raises(ValueError, match="timeout"):
        PolicyEvaluator(provider_timeout_seconds=0)


@pytest.mark.anyio
async def test_side_effect_without_execution_actor_is_denied() -> None:
    request = _request()
    missing_actor = request.model_copy(update={
        "execution": request.execution.model_copy(update={"actor": None}),
    })
    result = await PolicyEvaluator().evaluate(missing_actor, _config("allow"), at=NOW)
    assert (result.verdict, result.reason_code) == ("deny", "policy.missing_actor")
