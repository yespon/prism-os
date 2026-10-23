"""Knowledge embedding dispatch (R2 week 2).

Priority: a tenant-configured embedding model (model_type=embedding in
tenant_model_configs, OpenAI-compatible /embeddings) when ready, else the
deterministic hash embedding. Credentials are read from the model config
by the caller and never logged; failures degrade visibly through the
document index_state machine rather than silently.
"""

from __future__ import annotations

from collections.abc import Sequence

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.knowledge.retrieve import hash_embed_chunks
from deerflow.database.session import get_session_factory

_BATCH_LIMIT = 64


async def resolve_embedding_model(tenant_id: str, session_factory: async_sessionmaker[AsyncSession] | None = None) -> dict | None:
    """Return the tenant's enabled embedding model config, or None."""
    factory = session_factory or get_session_factory()
    from deerflow.database.models import TenantModelConfig

    async with factory() as session:
        rows = (await session.exec(
            select(TenantModelConfig).where(TenantModelConfig.tenant_id == tenant_id)
        )).all()
    for row in rows:
        settings = row.settings if isinstance(row.settings, dict) else {}
        model_type = row.model_type or settings.get("model_type")
        enabled = settings.get("enabled", True)
        if model_type != "embedding" or not enabled:
            continue
        if settings.get("base_url") and settings.get("api_key"):
            return {"model": row.model, "base_url": settings["base_url"], "api_key": settings["api_key"]}
    return None


def _embed_remote_batched(client: httpx.Client, base: str, headers: dict, model: str, texts: Sequence[str]) -> list[list[float]]:
    """Embed through an OpenAI-compatible endpoint in order-preserving slices."""
    if not texts:
        return []
    out: list[list[float]] = []
    for start in range(0, len(texts), _BATCH_LIMIT):
        batch = list(texts[start : start + _BATCH_LIMIT])
        response = client.post(f"{base.rstrip('/')}/embeddings", headers=headers,
                               json={"model": model, "input": batch})
        response.raise_for_status()
        data = response.json().get("data")
        if not isinstance(data, list) or len(data) != len(batch):
            raise RuntimeError("knowledge embedding response count mismatch")
        out.extend(list(item["embedding"]) for item in data)
    return out


async def embed_for_tenant(tenant_id: str, texts: Sequence[str]) -> list[list[float]]:
    """Embed texts for a tenant: remote embedding model when configured, else hash."""
    model = await resolve_embedding_model(tenant_id)
    if model is None:
        return hash_embed_chunks(texts)
    with httpx.Client(timeout=60.0) as client:
        return _embed_remote_batched(
            client, model["base_url"],
            {"Authorization": f"Bearer {model['api_key']}"}, model["model"], texts,
        )
