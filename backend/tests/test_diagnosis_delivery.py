"""Fresh current authority on the original incident checkpoint delivery path."""

import pytest
from sqlalchemy import select
from test_langgraph_proxy import proxy_setup as proxy_fixture

from app.alerting.diagnosis_delivery import verify_delivery
from app.models.agents import CustomAgent
from app.models.alerting import Incident
from app.models.governance import PlatformThreadBindingRecord
from app.platform.execution.trust import ThreadBindingRepository
from deerflow.database.models import TenantMembership
from deerflow.runtime import ExecutionTrustError

proxy_setup = proxy_fixture


@pytest.mark.anyio
@pytest.mark.parametrize("change", ["membership", "agent", "owner", "replacement"])
async def test_delivery_rechecks_current_authority_before_replay_or_live_output(proxy_setup, change):
    _, _, factory = proxy_setup
    await ThreadBindingRepository(factory).create("delivery-thread", "tenant-a", "user-1")
    async with factory() as session:
        session.add(Incident(id="delivery-incident", tenant_id="tenant-a", incident_key="DELIVERY", thread_id="delivery-thread", agent_id="agent-1", diagnosis_result="PRIVATE REPLAY"))
        await session.commit()
    assert await verify_delivery(factory, "tenant-a", "user-1", "diagnosis", "agent-1", "delivery-incident", "delivery-thread") == "delivery-thread"
    async with factory() as session:
        if change == "membership":
            row = (await session.exec(select(TenantMembership).where(TenantMembership.tenant_id == "tenant-a", TenantMembership.user_id == "user-1"))).scalars().one()
            row.status = "inactive"
        elif change == "agent":
            row = await session.get(CustomAgent, "agent-1")
            row.enabled = False
        elif change == "owner":
            row = await session.get(PlatformThreadBindingRecord, "delivery-thread")
            row.user_id = "user-2"
        else:
            row = await session.get(Incident, "delivery-incident")
            row.thread_id = "replacement-thread"
        session.add(row)
        await session.commit()
    with pytest.raises(ExecutionTrustError):
        await verify_delivery(factory, "tenant-a", "user-1", "diagnosis", "agent-1", "delivery-incident", "delivery-thread")
