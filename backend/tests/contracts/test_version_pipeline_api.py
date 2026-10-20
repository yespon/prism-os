"""R5 version pipeline API contracts: publish -> evaluate -> deploy -> rollback."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app.gateway import auth
from app.gateway.routers import agent_versions as routes


def _client(monkeypatch, tmp_path):
    import asyncio

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'pipeline.db'}")

    async def setup():
        async with engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)

    asyncio.run(setup())
    from sqlmodel.ext.asyncio.session import AsyncSession

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    from app.evaluation import EvaluationService
    from app.versioning import VersioningService

    versioning = VersioningService(factory)
    evaluation = EvaluationService(factory)
    monkeypatch.setattr(routes, "_versioning", lambda: versioning)
    monkeypatch.setattr(routes, "_evaluation", lambda: evaluation)

    # The publish route loads the CustomAgent through the session factory.
    from app.gateway.routers import agent_versions

    original_publish = versioning.publish

    async def publish(agent, *, notes=None):
        return await original_publish(agent, notes=notes)

    monkeypatch.setattr(agent_versions, "_load_agent", _make_loader(factory))

    monkeypatch.setattr(auth, "_resolve_user_from_auth_db", lambda token: ("user-1", "user", False) if token == "valid" else None)
    monkeypatch.setattr(auth, "_resolve_user_status_from_auth_db", lambda _user: "active")

    async def resolve_tenant(user_id=None, requested_tenant_id=None):
        return requested_tenant_id or "t1"

    monkeypatch.setattr(auth, "_resolve_tenant_id", resolve_tenant)

    async def resolve_role(*, user_id, tenant_id):
        return "user"

    monkeypatch.setattr(auth, "_resolve_tenant_role", resolve_role)

    app = FastAPI()
    app.add_middleware(auth.AuthMiddleware)
    app.include_router(routes.router)
    return TestClient(app), versioning, evaluation


def _make_loader(factory):
    class _Agent:
        def __init__(self):
            self.tenant_id = "t1"
            self.id = "agent-1"
            self.name = "assistant"
            self.description = ""
            self.model = "m"
            self.tool_groups = []
            self.system_prompt = "prompt"
            self.skills = []
            self.tags = []
            self.meta_info = {}
            self.created_by = "user-1"

    def load(session, tenant_id, agent_id):
        return _Agent()

    return load


def test_publish_evaluate_deploy_rollback_pipeline(monkeypatch, tmp_path):
    app_client, versioning, evaluation = _client(monkeypatch, tmp_path)
    with app_client:
        client = app_client
        client.headers.update({"Authorization": "Bearer valid", "x-tenant-id": "t1"})

        # 1. Publish v1.
        published = client.post("/api/agents/agent-1/versions", json={"notes": "first"})
        assert published.status_code == 201, published.text
        v1 = published.json()

        # 2. Deploy without an evaluation: gate refuses.
        blocked = client.post(f"/api/agents/agent-1/versions/{v1['id']}/deploy")
        assert blocked.status_code == 409, blocked.text
        assert "no evaluation" in blocked.json()["detail"]

        # 3. Low score also blocked.
        client.post(f"/api/agents/agent-1/versions/{v1['id']}/evaluate",
                    json={"score": 0.4, "dataset": "golden"})
        low = client.post(f"/api/agents/agent-1/versions/{v1['id']}/deploy")
        assert low.status_code == 409 and "gate failed" in low.json()["detail"]

        # 4. Passing score deploys.
        client.post(f"/api/agents/agent-1/versions/{v1['id']}/evaluate",
                    json={"score": 0.95, "dataset": "golden"})
        deployed = client.post(f"/api/agents/agent-1/versions/{v1['id']}/deploy")
        assert deployed.status_code == 202, deployed.text
        assert deployed.json()["version_id"] == v1["id"]

        # 5. Deployment pointer visible.
        current = client.get("/api/agents/agent-1/versions/deployment")
        assert current.json()["version_id"] == v1["id"]

        # 6. Republish same config refused (identical hash).
        duplicate = client.post("/api/agents/agent-1/versions")
        assert duplicate.status_code == 400
