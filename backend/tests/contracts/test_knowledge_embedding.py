"""R2 embedding dispatch contracts: resolution and remote batching."""

from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.knowledge.embedding import _embed_remote_batched, embed_for_tenant, resolve_embedding_model
from app.knowledge.retrieve import hash_embed_chunks


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, embeddings_map):
        self.embeddings_map = embeddings_map
        self.calls = []

    def post(self, url, headers=None, json=None, **kwargs):
        self.calls.append(url)
        return _FakeResponse({"data": [{"embedding": self.embeddings_map[t]} for t in json["input"]]})


def test_remote_batched_preserves_order():
    texts = [f"chunk-{i}" for i in range(70)]  # crosses the 64-batch limit
    vectors = {t: [float(len(t)), 1.0] for t in texts}
    client = _FakeClient(vectors)
    out = _embed_remote_batched(client, "https://embed.example/v1", {}, "m", texts)
    assert out == [vectors[t] for t in texts]


@pytest.mark.anyio
async def test_embed_for_tenant_degrades_to_hash_without_model(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'embed.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    with patch("app.knowledge.embedding.get_session_factory", lambda: factory):
        result = await embed_for_tenant("t1", ["alpha beta", "gamma"])
    expected = hash_embed_chunks(["alpha beta", "gamma"])
    assert result == expected
    await engine.dispose()


@pytest.mark.anyio
async def test_resolve_embedding_model_requires_ready_config(tmp_path):
    from deerflow.database.models import TenantModelConfig

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'embed2.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session, session.begin():
        session.add(TenantModelConfig(
            tenant_id="t1", user_id="owner", name="embed", model="e-large",
            model_type="embedding",
            settings={"model_type": "embedding", "enabled": True,
                      "base_url": "https://embed.example/v1", "api_key": "secret"},
        ))
        session.add(TenantModelConfig(
            tenant_id="t1", user_id="owner", name="embed-off", model="e-off",
            model_type="embedding",
            settings={"model_type": "embedding", "enabled": False,
                      "base_url": "https://off.example/v1", "api_key": "x"},
        ))

    with patch("app.knowledge.embedding.get_session_factory", lambda: factory):
        resolved = await resolve_embedding_model("t1")
        none = await resolve_embedding_model("t2")
    assert resolved == {"model": "e-large", "base_url": "https://embed.example/v1", "api_key": "secret"}
    assert none is None
    await engine.dispose()
