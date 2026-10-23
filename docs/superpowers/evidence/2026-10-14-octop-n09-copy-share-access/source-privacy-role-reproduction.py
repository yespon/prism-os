"""Current configuration disclosure and share authorization must use live facts."""
import asyncio

from sqlalchemy import select
from test_agent_skill_references import configured, scoped_client  # noqa: F401
from test_skill_reference_transactions import durable_sqlite  # noqa: F401
from app.models.agents import CustomAgent
from deerflow.database.models import TenantMembership


def test_private_configuration_not_disclosed_to_other_member_through_discovery(configured):
    http, factory, _, _ = configured
    async def create():
        async with factory() as db:
            db.add(CustomAgent(id='private-foreign', tenant_id='tenant-a', user_id='other-user', name='private-foreign', system_prompt='PRIVATE CONFIGURATION'))
            role = (await db.exec(select(TenantMembership))).scalars().one()
            role.role = 'tenant_member'
            db.add(role)
            await db.commit()
    asyncio.run(create())
    result = http.get('/api/agents?show_all=true')
    assert result.status_code == 200
    assert 'PRIVATE CONFIGURATION' not in result.text


def test_cached_admin_claim_does_not_authorize_sharing_after_role_withdrawal(configured):
    http, factory, _, _ = configured
    created = http.post('/api/agents',json={'name':'before-role-withdrawal','system_prompt':'Owned configuration','skill_binding_mode':'selected','skill_resources':[]})
    assert created.status_code == 201
    async def revoke():
        async with factory() as db:
            role = (await db.exec(select(TenantMembership))).scalars().one()
            role.role = 'tenant_member'
            db.add(role)
            await db.commit()
    asyncio.run(revoke())
    result = http.put('/api/agents/before-role-withdrawal',json={'is_shared':True},headers={'x-tenant-role':'tenant_admin'})
    assert result.status_code == 403, result.text
