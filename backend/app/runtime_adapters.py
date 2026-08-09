"""PrismOS integrations for the standalone DeerFlow harness runtime."""

from __future__ import annotations

import asyncio
import concurrent.futures
import uuid

from sqlalchemy import select

from app.agent.prompts import TERMINAL_AGENT_SYSTEM_PROMPT
from app.agent.terminal_tools import get_terminal_tools, set_terminal_context
from app.models.agents import CustomAgent
from deerflow.database.session import get_session_factory
from deerflow.runtime import (
    register_agent_config_provider,
    register_agent_persistence_provider,
    register_terminal_agent_provider,
)


def _run_async(coro):
    """Run an async provider from synchronous LangGraph callbacks."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coro).result()


def _load_agent(name: str, user_id: str | None, tenant_id: str | None) -> CustomAgent | None:
    async def _query() -> CustomAgent | None:
        session_factory = get_session_factory()
        async with session_factory() as session:
            statement = select(CustomAgent).where(
                CustomAgent.tenant_id == tenant_id,
                CustomAgent.user_id.in_([user_id, "tenant-shared"]),
                CustomAgent.name == name,
            )
            result = await session.exec(statement)
            agents = result.all()
            for agent in agents:
                if agent.user_id == user_id:
                    return agent
            return agents[0] if agents else None

    return _run_async(_query())


def _list_agents(user_id: str | None, tenant_id: str | None) -> list[CustomAgent]:
    async def _query() -> list[CustomAgent]:
        session_factory = get_session_factory()
        async with session_factory() as session:
            statement = (
                select(CustomAgent)
                .where(CustomAgent.tenant_id == tenant_id, CustomAgent.user_id == user_id)
                .order_by(CustomAgent.name)
            )
            result = await session.exec(statement)
            return result.all()

    return _run_async(_query())


def _persist_agent(
    *, agent_name: str, soul: str, description: str, user_id: str | None, tenant_id: str | None
) -> None:
    async def _create() -> None:
        session_factory = get_session_factory()
        async with session_factory() as session:
            session.add(
                CustomAgent(
                    id=str(uuid.uuid4()),
                    tenant_id=tenant_id or "default",
                    user_id=user_id or "unknown",
                    name=agent_name,
                    description=description,
                    system_prompt=soul,
                    enabled=True,
                    created_by=user_id,
                )
            )
            await session.commit()

    _run_async(_create())


register_agent_config_provider(_load_agent, _list_agents)
register_agent_persistence_provider(_persist_agent)
register_terminal_agent_provider(
    get_tools=get_terminal_tools,
    set_context=set_terminal_context,
    system_prompt=TERMINAL_AGENT_SYSTEM_PROMPT,
)
