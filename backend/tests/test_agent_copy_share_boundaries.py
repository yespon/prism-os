"""Original live configuration access and source-bound target resource authorization."""

import asyncio

import pytest
from sqlalchemy import select
from test_agent_skill_references import configured as resource_fixture
from test_agent_skill_references import scoped_client  # noqa: F401
from test_skill_reference_transactions import durable_sqlite  # noqa: F401

from app.integrations.agent_skill_references import current_skill_prompt
from app.models.agents import CustomAgent
from deerflow.database.models import TenantMembership

configured = resource_fixture


def source(configured):
    http, _, _, resources = configured
    response = http.post("/api/agents",json={"name":"copy-source","system_prompt":"SOURCE ROLE","skill_binding_mode":"selected","skill_resources":[resources["personal"]]})
    assert response.status_code == 201, response.text
    return response.json()


def clone(http, original, **changes):
    payload = {"name":"copied-agent","source_agent_id":original["id"],"source_revision":original["revision"],**changes}
    return http.post("/api/agents/copy-source/copy",json=payload)


def modify(factory, function):
    async def update():
        async with factory() as db:
            await function(db)
            await db.commit()
    asyncio.run(update())


def test_copy_keeps_source_version_provenance_in_original_metadata_and_new_identity(configured):
    http, factory, _, _ = configured
    original = source(configured)
    response = clone(http, original)
    assert response.status_code == 201, response.text
    copied = response.json()
    assert copied["id"] != original["id"] and copied["skill_resources"] == original["skill_resources"]
    assert copied["system_prompt"] == original["system_prompt"]
    async def read():
        async with factory() as db:
            row = await db.get(CustomAgent,copied["id"])
            return row.meta_info, await current_skill_prompt(db,row.name,"tenant-a","user-a",selected_agent_id=row.id)
    metadata, prompt = asyncio.run(read())
    assert metadata["prismos_copy_origin"] == {"version":1,"agent_id":original["id"],"revision":original["revision"],"tenant_id":"tenant-a"}
    assert "PERSONAL ONLY" in prompt and "PUBLIC ONLY" not in prompt


def test_copy_to_shared_cannot_inherit_private_resource_but_can_explicitly_choose_target(configured):
    http, factory, _, resources = configured
    original = source(configured)
    denied = clone(http, original,is_shared=True)
    assert denied.status_code == 403, denied.text
    assert not http.get("/api/agents/copied-agent").status_code == 200
    copied = clone(http,original,is_shared=True,skill_binding_mode="selected",skill_resources=[resources["tenant"]])
    assert copied.status_code == 201, copied.text
    assert copied.json()["is_shared"] and copied.json()["skill_resources"] == [resources["tenant"]]
    async def prompt():
        async with factory() as db:
            return await current_skill_prompt(db,"copied-agent","tenant-a","user-a",selected_agent_id=copied.json()["id"])
    assert "SHARED ONLY" in asyncio.run(prompt()) and "PERSONAL ONLY" not in asyncio.run(prompt())


@pytest.mark.parametrize("problem", ["changed-source", "wrong-id", "foreign-actor", "foreign-tenant", "withdrawn"])
def test_copy_refuses_stale_or_inaccessible_source_without_creating_target(configured, problem):
    http, factory, _, _ = configured
    original = source(configured)
    async def change(db):
        if problem == "withdrawn":
            row = (await db.exec(select(TenantMembership))).scalars().one()
            row.status = "inactive"
        else:
            row = await db.get(CustomAgent,original["id"])
            if problem == "changed-source":
                row.description="NEW CURRENT VERSION"
            elif problem == "foreign-actor":
                row.user_id="other-user"
            elif problem == "foreign-tenant":
                row.tenant_id="other-tenant"
            else:
                return
        db.add(row)
    modify(factory,change)
    result = clone(http,original,**({"source_agent_id":"wrong-id"} if problem == "wrong-id" else {}))
    assert result.status_code in {403,404,409}, result.text
    async def targets():
        async with factory() as db:
            return (await db.exec(select(CustomAgent).where(CustomAgent.name=="copied-agent"))).scalars().all()
    assert asyncio.run(targets()) == []


def test_copy_all_and_empty_target_choices_are_explicit_not_name_fallbacks(configured):
    http, _, _, _ = configured
    original = source(configured)
    all_current = clone(http,original,skill_binding_mode="all")
    assert all_current.status_code == 201 and all_current.json()["skill_binding_mode"] == "all" and all_current.json()["skill_resources"] == []
    empty = clone(http,original,name="empty-copy",skill_binding_mode="selected",skill_resources=[])
    assert empty.status_code == 201 and empty.json()["skills"] == [] and empty.json()["skill_resources"] == []
    duplicate = clone(http,original)
    assert duplicate.status_code == 409


def test_actual_discovery_hides_foreign_configuration_and_cached_admin_cannot_share(configured):
    http, factory, _, _ = configured
    original = source(configured)
    async def role_and_foreign(db):
        db.add(CustomAgent(id="foreign-config",tenant_id="tenant-a",user_id="other-user",name="foreign-config",system_prompt="PRIVATE CONFIGURATION"))
        row = (await db.exec(select(TenantMembership))).scalars().one()
        row.role = "member"
        db.add(row)
    modify(factory,role_and_foreign)
    found = http.get("/api/agents?show_all=true",headers={"x-tenant-role":"tenant_admin"})
    assert found.status_code == 200 and "PRIVATE CONFIGURATION" not in found.text
    foreign = next(row for row in found.json()["agents"] if row["id"] == "foreign-config")
    assert foreign["revision"] is None and foreign["system_prompt"] is None and foreign["base_system_prompt"] == ""
    denied = http.put("/api/agents/copy-source",json={"is_shared":True},headers={"x-tenant-role":"tenant_admin"})
    assert denied.status_code == 403
    denied_copy = clone(http,original,is_shared=True,skill_binding_mode="selected",skill_resources=[])
    assert denied_copy.status_code == 403
    allowed = clone(http,original)
    assert allowed.status_code == 201


def test_member_withdrawal_hides_configuration_and_blocks_delete_and_copy(configured):
    http,factory,_,_ = configured
    original=source(configured)
    async def withdraw(db):
        row = (await db.exec(select(TenantMembership))).scalars().one()
        row.status="inactive"
        db.add(row)
    modify(factory,withdraw)
    for result in [http.get("/api/agents"),http.get("/api/agents/copy-source"),http.put("/api/agents/copy-source",json={"description":"changed"}),http.delete("/api/agents/copy-source"),clone(http,original)]:
        assert result.status_code==403 and "SOURCE ROLE" not in result.text


def test_current_member_profile_preserves_owned_content_and_refuses_alias_or_withdrawal(configured, monkeypatch):
    from app.gateway.routers import agents
    from deerflow.config.paths import Paths
    http,factory,root,_ = configured
    paths=Paths(str(root.parent/"profile-data"))
    monkeypatch.setattr(agents,"get_paths",lambda:paths)
    created=http.put("/api/user-profile",json={"content":"OWN PROFILE"})
    assert created.status_code==200 and http.get("/api/user-profile").json()["content"]=="OWN PROFILE"
    actual=paths.user_md_file(user_id="user-a",tenant_id="tenant-a")
    private=root.parent/"private-host.txt"
    private.write_text("HOST PROFILE SECRET")
    actual.unlink()
    actual.symlink_to(private)
    denied=http.get("/api/user-profile")
    assert denied.status_code>=400 and "HOST PROFILE SECRET" not in denied.text
    overwritten=http.put("/api/user-profile",json={"content":"must not write host"})
    assert overwritten.status_code>=400 and private.read_text()=="HOST PROFILE SECRET"
    async def withdraw(db):
        row=(await db.exec(select(TenantMembership))).scalars().one()
        row.status="inactive"
        db.add(row)
    modify(factory,withdraw)
    assert http.get("/api/user-profile").status_code==403
    assert http.put("/api/user-profile",json={"content":"withdrawn"}).status_code==403
