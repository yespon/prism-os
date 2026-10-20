"""Agent version pipeline API: publish, evaluate, deploy, rollback (R5)."""

from fastapi import APIRouter, Depends, HTTPException, Request

from app.gateway.authorization import require_tenant_context

router = APIRouter(prefix="/api/agents/{agent_id}/versions", tags=["agent-versions"])


def _versioning():
    from app.versioning import VersioningService

    return VersioningService()


def _evaluation():
    from app.evaluation import EvaluationService

    return EvaluationService()


async def _load_agent(session, tenant_id: str, agent_id: str):
    from app.models.agents import CustomAgent

    agent = await session.get(CustomAgent, agent_id)
    if agent is None or agent.tenant_id != tenant_id:
        raise HTTPException(404, "Agent not found")
    return agent


def _version_response(record) -> dict:
    return {
        "id": record.id, "agent_id": record.agent_id, "version_no": record.version_no,
        "version_hash": record.version_hash, "notes": record.notes,
        "published_by": record.published_by, "published_at": record.published_at,
    }


@router.get("")
async def list_versions(agent_id: str, request: Request, _ctx: None = Depends(require_tenant_context)) -> dict:
    tenant_id = request.state.tenant_id
    return {"versions": [_version_response(v) for v in await _versioning().list_versions(tenant_id, agent_id)]}


@router.post("", status_code=201)
async def publish_version(agent_id: str, request: Request, body: dict | None = None,
                          _ctx: None = Depends(require_tenant_context)) -> dict:
    """Snapshot the agent's current configuration as an immutable version."""
    tenant_id = request.state.tenant_id
    from deerflow.database.session import get_session_factory

    from app.versioning import VersioningError

    async with get_session_factory()() as session:
        agent = await _load_agent(session, tenant_id, agent_id)
    try:
        record = await _versioning().publish(agent, notes=(body or {}).get("notes"))
    except VersioningError as error:
        raise HTTPException(400, str(error)) from error
    return _version_response(record)


@router.post("/{version_id}/evaluate", status_code=201)
async def evaluate_version(agent_id: str, version_id: str, request: Request, body: dict,
                           _ctx: None = Depends(require_tenant_context)) -> dict:
    """Record an evaluation score for a version."""
    tenant_id = request.state.tenant_id
    from app.evaluation import EvaluationError

    score = body.get("score")
    dataset = body.get("dataset", "golden")
    if not isinstance(score, (int, float)):
        raise HTTPException(400, "score is required (number within [0, 1])")
    try:
        record = await _evaluation().record(
            tenant_id, version_id, dataset=str(dataset), score=float(score),
            details=body.get("details"))
    except EvaluationError as error:
        raise HTTPException(400, str(error)) from error
    return {"evaluation_id": record.evaluation_id, "score": record.score, "passed": record.passed}


@router.post("/{version_id}/deploy", status_code=202)
async def deploy_version(agent_id: str, version_id: str, request: Request,
                         _ctx: None = Depends(require_tenant_context)) -> dict:
    """Deploy a version; the evaluation gate must pass first."""
    tenant_id = request.state.tenant_id
    from app.evaluation import EvaluationError
    from app.versioning import VersioningError

    try:
        await _evaluation().enforce_gate(tenant_id, version_id)
        deployment = await _versioning().deploy(
            tenant_id, agent_id, version_id, deployed_by=request.state.user_id)
    except EvaluationError as error:
        raise HTTPException(409, str(error)) from error
    except VersioningError as error:
        raise HTTPException(400, str(error)) from error
    return {
        "agent_id": deployment.agent_id, "version_id": deployment.version_id,
        "previous_version_id": deployment.previous_version_id,
    }


@router.post("/rollback")
async def rollback_version(agent_id: str, request: Request,
                           _ctx: None = Depends(require_tenant_context)) -> dict:
    tenant_id = request.state.tenant_id
    from app.versioning import VersioningError

    try:
        deployment = await _versioning().rollback(tenant_id, agent_id, deployed_by=request.state.user_id)
    except VersioningError as error:
        raise HTTPException(409, str(error)) from error
    return {"agent_id": deployment.agent_id, "version_id": deployment.version_id}


@router.get("/deployment")
async def get_deployment(agent_id: str, request: Request,
                         _ctx: None = Depends(require_tenant_context)) -> dict:
    tenant_id = request.state.tenant_id
    deployment = await _versioning().get_deployment(tenant_id, agent_id)
    if deployment is None:
        return {"version_id": None}
    return {
        "agent_id": deployment.agent_id, "version_id": deployment.version_id,
        "previous_version_id": deployment.previous_version_id,
        "deployed_by": deployment.deployed_by, "deployed_at": deployment.deployed_at,
    }
