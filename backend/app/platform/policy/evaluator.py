"""Deterministic three-branch Policy evaluation; no Action execution here."""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import MappingProxyType
from typing import Literal

from app.platform.contracts import PolicyDecision, PolicyRequest

RiskClass = Literal["read_only", "side_effect"]
Verdict = Literal["allow", "deny", "require_approval"]
TerminalAction = Literal["allow", "ask", "block"]


@dataclass(frozen=True)
class PolicyRule:
    risk_class: RiskClass
    verdict: Verdict

    def __post_init__(self) -> None:
        if self.risk_class not in ("read_only", "side_effect"):
            raise ValueError("invalid risk_class")
        if self.verdict not in ("allow", "deny", "require_approval"):
            raise ValueError("invalid verdict")


@dataclass(frozen=True)
class PolicyConfiguration:
    policy_id: str
    version: str
    rules: Mapping[str, PolicyRule]
    ttl_seconds: int = 300

    def __post_init__(self) -> None:
        if not self.policy_id.strip() or not self.version.strip():
            raise ValueError("policy_id and version are required")
        if self.ttl_seconds <= 0:
            raise ValueError("policy TTL must be positive")
        if any(not action.strip() or not isinstance(rule, PolicyRule) for action, rule in self.rules.items()):
            raise ValueError("invalid Policy rule")
        object.__setattr__(self, "rules", MappingProxyType(dict(self.rules)))


@dataclass(frozen=True)
class SafetySignals:
    """Trusted adapters map Guardrail allow/deny and Terminal allow/ask/block here."""

    guardrail_allow: bool | None = None
    terminal_action: TerminalAction | None = None

    def __post_init__(self) -> None:
        if self.guardrail_allow is not None and not isinstance(self.guardrail_allow, bool):
            raise ValueError("invalid Guardrail signal")
        if self.terminal_action not in (None, "allow", "ask", "block"):
            raise ValueError("invalid Terminal signal")


SafetyProvider = Callable[[PolicyRequest], Awaitable[SafetySignals]]


class PolicyEvaluator:
    def __init__(self, *, provider_timeout_seconds: float = 2.0) -> None:
        if provider_timeout_seconds <= 0:
            raise ValueError("provider timeout must be positive")
        self._provider_timeout_seconds = provider_timeout_seconds

    async def evaluate(
        self,
        request: PolicyRequest,
        configuration: PolicyConfiguration | None,
        safety_provider: SafetyProvider | None = None,
        *,
        at: datetime | None = None,
    ) -> PolicyDecision:
        decided_at = at or datetime.now(UTC)
        policy_id = configuration.policy_id if configuration else "m1-default-deny"
        policy_version = configuration.version if configuration else "unconfigured"
        verdict: Verdict = "deny"
        reason = "policy.unconfigured"
        ttl_seconds = configuration.ttl_seconds if configuration else 300
        rule = configuration.rules.get(request.action) if configuration else None
        if configuration is not None:
            if rule is None:
                reason = "policy.unconfigured_action"
            elif rule.risk_class != request.risk_class:
                reason = "policy.risk_mismatch"
            elif request.risk_class == "side_effect" and request.execution.actor is None:
                reason = "policy.missing_actor"
            else:
                verdict = rule.verdict
                reason = "policy.rule"
                if safety_provider is not None:
                    try:
                        signals = await asyncio.wait_for(
                            safety_provider(request), timeout=self._provider_timeout_seconds,
                        )
                        if not isinstance(signals, SafetySignals):
                            raise ValueError("invalid safety provider result")
                    except TimeoutError:
                        verdict, reason = "deny", "policy.provider_timeout"
                    except Exception:
                        verdict, reason = "deny", "policy.provider_error"
                    else:
                        if signals.guardrail_allow is False or signals.terminal_action == "block":
                            verdict, reason = "deny", "policy.safety_block"
                        elif signals.terminal_action == "ask" and verdict == "allow":
                            verdict, reason = "require_approval", "policy.safety_approval"
        identifier = sha256(f"{request.tenant_id}:{request.request_id}".encode()).hexdigest()[:32]
        return PolicyDecision(
            tenant_id=request.tenant_id,
            decision_id=f"decision_{identifier}",
            request_id=request.request_id,
            execution=request.execution,
            action=request.action,
            risk_class=request.risk_class,
            resource_id=request.resource_id,
            context_hash=request.context_hash,
            verdict=verdict,
            policy_id=policy_id,
            policy_version=policy_version,
            reason_code=reason,
            decided_at=decided_at,
            expires_at=decided_at + timedelta(seconds=ttl_seconds),
        )
