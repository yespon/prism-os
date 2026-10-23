"""Fresh delivery authorization for original incident checkpoints and buffers."""

from app.models.alerting import Incident
from app.platform.execution.trust import ThreadBindingRepository
from deerflow.runtime import ExecutionTrustError


async def verify_delivery(factory, tenant, actor, name, agent, incident_id, thread=None, *, new_thread_pending=False):
    from app.runtime_adapters import verify_native_selection

    async with factory() as session:
        await verify_native_selection(session, tenant, actor, name, agent, diagnosis_incident_id=incident_id)
        incident = await session.get(Incident, incident_id, populate_existing=True)
        if thread and incident.thread_id and thread != incident.thread_id:
            raise ExecutionTrustError("Diagnosis delivery thread changed")
        active_thread = thread if new_thread_pending else thread or incident.thread_id
    if active_thread:
        await ThreadBindingRepository(factory).get(active_thread, tenant, actor)
    return active_thread
