import pytest

from app.services.policy_safety import map_safety_results
from app.services.terminal.security import CommandSecurityResult
from deerflow.guardrails.provider import GuardrailDecision


@pytest.mark.parametrize("terminal,expected", [("allow", "allow"), ("ask", "ask"), ("block", "block")])
def test_legacy_terminal_result_maps_exactly(terminal, expected) -> None:
    signals = map_safety_results(terminal=CommandSecurityResult(terminal))
    assert signals.terminal_action == expected


def test_guardrail_denial_maps_to_restrictive_signal() -> None:
    signals = map_safety_results(guardrail=GuardrailDecision(allow=False))
    assert signals.guardrail_allow is False
    assert signals.terminal_action is None


def test_no_legacy_result_does_not_supply_permission() -> None:
    signals = map_safety_results()
    assert signals.guardrail_allow is None
    assert signals.terminal_action is None
