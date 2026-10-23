"""Original-owner cleanup and honest interruption results under live withdrawal."""

import asyncio
from types import SimpleNamespace

import pytest
from test_langgraph_proxy import proxy_setup as proxy_fixture

from app.alerting.diagnosis_run_control import DiagnosisAuthorityWithdrawn, interrupt_owned_runs, wait_authorized_result
from app.integrations.file_access import verify_thread
from app.models.governance import PlatformThreadBindingRecord
from app.platform.execution.trust import ThreadBindingRepository
from deerflow.database.models import TenantMembership
from deerflow.runtime import ExecutionTrustError

proxy_setup = proxy_fixture


@pytest.mark.anyio
@pytest.mark.parametrize("response", ["confirmed", "accepted", "empty", "list-failed", "cancel-failed", "wrong-thread", "unowned", "changed-owner"])
async def test_interrupt_requires_original_owner_and_observed_terminal_state(proxy_setup, response):
    _, _, factory = proxy_setup
    await ThreadBindingRepository(factory).create("guard-thread", "tenant-a", "user-1")
    calls = []

    async def listing(thread, **kwargs):
        if response == "list-failed":
            raise TimeoutError("lost list response")
        if response == "empty" or kwargs["status"] == "pending":
            return []
        if response == "changed-owner":
            async with factory() as session:
                row = await session.get(PlatformThreadBindingRecord, "guard-thread")
                row.user_id = "user-2"
                session.add(row)
                await session.commit()
        return [{"run_id": "owned-run", "thread_id": "foreign-thread" if response == "wrong-thread" else thread}]

    async def cancel(*args, **kwargs):
        calls.append(("cancel", args, kwargs))
        if response == "cancel-failed":
            raise TimeoutError("lost cancel response")

    async def get(*args):
        return {"run_id": args[1], "thread_id": args[0], "status": "interrupted" if response == "confirmed" else "running"}

    client = SimpleNamespace(runs=SimpleNamespace(list=listing, cancel=cancel, get=get))
    result = await interrupt_owned_runs(client, "guard-thread", "tenant-a", "user-2" if response == "unowned" else "user-1", factory, timeout=0.15)
    assert result.status == ("confirmed" if response == "confirmed" else "unknown")
    assert result.external_effects == "unknown"
    assert len(calls) == (1 if response in {"confirmed", "accepted", "cancel-failed"} else 0)


@pytest.mark.anyio
async def test_withdrawal_while_waiting_cleans_local_wait_and_records_remote_unknown(proxy_setup):
    from sqlalchemy import select

    _, _, factory = proxy_setup
    await ThreadBindingRepository(factory).create("guard-thread", "tenant-a", "user-1")
    started, local_stopped = asyncio.Event(), asyncio.Event()

    async def waiting():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            local_stopped.set()

    async def validate():
        async with factory() as session:
            await verify_thread(session, "tenant-a", "user-1", "guard-thread")

    cancellations = []

    async def listing(thread, **kwargs):
        return [{"run_id": "owned-run"}] if kwargs["status"] == "running" else []

    async def cancel(*args, **kwargs):
        cancellations.append(True)
        raise TimeoutError("unknown remote outcome")

    client = SimpleNamespace(runs=SimpleNamespace(list=listing, cancel=cancel))

    async def interrupt():
        return await interrupt_owned_runs(client, "guard-thread", "tenant-a", "user-1", factory)

    task = asyncio.create_task(wait_authorized_result(waiting(), validate, interrupt, interval=0.01))
    await started.wait()
    async with factory() as session:
        row = (await session.exec(select(TenantMembership).where(TenantMembership.tenant_id == "tenant-a", TenantMembership.user_id == "user-1"))).scalars().one()
        row.status = "inactive"
        session.add(row)
        await session.commit()
    with pytest.raises(DiagnosisAuthorityWithdrawn) as outcome:
        await asyncio.wait_for(task, 2)
    assert outcome.value.interruption.status == "unknown"
    assert local_stopped.is_set() and cancellations == [True]


@pytest.mark.anyio
async def test_failed_admission_never_starts_remote_request():
    calls = []

    async def waiting():
        calls.append("started")
        return "result"

    async def validate():
        raise ExecutionTrustError("withdrawn before admission")

    async def interrupt():
        pytest.fail("No remote request was started")

    with pytest.raises(ExecutionTrustError):
        await wait_authorized_result(waiting(), validate, interrupt)
    assert calls == []


@pytest.mark.anyio
async def test_authority_change_inside_returning_request_discards_the_result():
    current = True

    async def validate():
        if not current:
            raise ExecutionTrustError("withdrawn while returning")

    async def waiting():
        nonlocal current
        current = False
        return "REVOKED RESULT"

    async def interrupt():
        from app.alerting.diagnosis_run_control import InterruptionResult

        return InterruptionResult("unknown")

    with pytest.raises(DiagnosisAuthorityWithdrawn):
        await wait_authorized_result(waiting(), validate, interrupt)


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["confirmed", "lost", "empty", "other-member"])
async def test_original_cancel_endpoint_checks_owner_and_persists_honest_outcome(proxy_setup, monkeypatch, mode):
    import langgraph_sdk
    from sqlalchemy import select

    from app.gateway.routers import alerts
    from app.models.alerting import Incident, IncidentAction
    from deerflow.database.session import get_session

    client, _, factory = proxy_setup
    await ThreadBindingRepository(factory).create("cancel-thread", "tenant-a", "user-1")
    async with factory() as session:
        session.add(Incident(id="cancel-incident", tenant_id="tenant-a", incident_key="CANCEL-TEST", thread_id="cancel-thread", agent_id="agent-1", diagnosis_status="running"))
        await session.commit()
    app = client._transport.app
    app.include_router(alerts.router)

    async def dependency():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = dependency
    monkeypatch.setattr(alerts, "get_session_factory", lambda: factory)
    local_stops, remote_calls = [], []
    monkeypatch.setattr(alerts.diagnosis_task_manager, "cancel_task", lambda incident: local_stops.append(incident))

    async def listing(thread, **kwargs):
        return [{"run_id": "cancel-run", "thread_id": thread}] if mode != "empty" and kwargs["status"] == "running" else []

    async def cancel(thread, run, **kwargs):
        remote_calls.append(run)
        if mode == "lost":
            raise TimeoutError("lost cancellation reply")

    async def get(thread, run):
        return {"run_id": run, "thread_id": thread, "status": "interrupted"}

    monkeypatch.setattr(langgraph_sdk, "get_client", lambda **kwargs: SimpleNamespace(runs=SimpleNamespace(list=listing, cancel=cancel, get=get)))
    response = await client.post("/api/incidents/cancel-incident/diagnose/cancel", headers={"x-test-user": "user-2"} if mode == "other-member" else {})
    async with factory() as session:
        incident = await session.get(Incident, "cancel-incident")
        actions = (await session.exec(select(IncidentAction).where(IncidentAction.incident_id == "cancel-incident"))).scalars().all()
    if mode == "other-member":
        assert response.status_code == 404
        assert not local_stops and not remote_calls and not actions
        assert incident.diagnosis_status == "running"
    else:
        assert response.status_code == 200
        assert response.json()["status"] == ("cancelled" if mode == "confirmed" else "unknown")
        assert incident.diagnosis_status == ("cancelled" if mode == "confirmed" else "failed")
        assert incident.diagnosis_error.startswith("cancel_requested:")
        assert len(actions) == 1 and actions[0].action_payload["interruption"] == ("confirmed" if mode == "confirmed" else "unknown")
        assert actions[0].action_payload["external_effects"] == "unknown"
        assert len(remote_calls) == (0 if mode == "empty" else 1)
