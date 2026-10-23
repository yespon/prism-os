"""An old Approval is not a capability under a different current Policy."""

from datetime import timedelta

import pytest
from test_governed_ticket import NOW
from test_governed_ticket import ticket_setup as ticket_fixture

from app.platform.policy.evaluator import PolicyConfiguration, PolicyRule

ticket_setup = ticket_fixture


@pytest.mark.anyio
@pytest.mark.parametrize('current', [('ticket-m1', 'v2', 'deny'), ('ticket-m1', 'v2', 'allow'), ('other-policy', 'v1', 'require_approval'), ('ticket-m1', 'v1', 'deny'), None])
async def test_approved_old_policy_cannot_consume_or_submit_under_a_changed_configuration(ticket_setup, current):
    make, execution, state, approvals, reviewer, _, _, submissions, _ = ticket_setup
    adapter = make('require_approval')
    waiting = await adapter.execute(execution, 'policy-change-request', 'incident-1', at=NOW)
    assert waiting.status == 'awaiting_approval'
    await reviewer.review('tenant-a', waiting.approval_id, 'admin-1', 'approve', at=NOW + timedelta(seconds=1))
    adapter._configuration = None if current is None else PolicyConfiguration(
        policy_id=current[0], version=current[1], rules={'ticket.create': PolicyRule(risk_class='side_effect', verdict=current[2])},
    )
    with pytest.raises(ValueError, match='policy changed'):
        await adapter.execute(execution, 'policy-change-request', 'incident-1', at=NOW + timedelta(seconds=2))
    assert state.calls == []
    assert (await approvals.get_by_decision('tenant-a', waiting.decision_id))[0].status == 'approved'
    assert await submissions.get('tenant-a', waiting.decision_id) is None
