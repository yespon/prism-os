"""Narrow mapping from legacy safety results to platform Policy inputs."""

from app.platform.policy.evaluator import SafetySignals
from app.services.terminal.security import CommandSecurityResult
from deerflow.guardrails.provider import GuardrailDecision


def map_safety_results(
    *,
    guardrail: GuardrailDecision | None = None,
    terminal: CommandSecurityResult | None = None,
) -> SafetySignals:
    """Legacy allow cannot override a platform rule; block and ask can restrict it."""
    return SafetySignals(
        guardrail_allow=None if guardrail is None else guardrail.allow,
        terminal_action=None if terminal is None else terminal.action,
    )
