import logging

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime
from langgraph.types import Command

from deerflow.config.paths import get_paths
from deerflow.runtime import get_agent_persistence_provider

logger = logging.getLogger(__name__)


def _create_agent_in_db(
    agent_name: str,
    soul: str,
    description: str,
    user_id: str,
    tenant_id: str | None,
) -> None:
    """Create a custom agent through the host application's provider."""
    persister = get_agent_persistence_provider()
    if persister is None:
        raise RuntimeError("Custom-agent persistence is not configured by the host application")
    persister(
        agent_name=agent_name,
        soul=soul,
        description=description,
        user_id=user_id,
        tenant_id=tenant_id,
    )


@tool
def setup_agent(
    soul: str,
    description: str,
    runtime: ToolRuntime,
) -> Command:
    """Setup the custom DeerFlow agent.

    Args:
        soul: Full SOUL.md content defining the agent's personality and behavior.
        description: One-line description of what the agent does.
    """

    agent_name: str | None = runtime.context.get("agent_name") if runtime.context else None
    user_id: str | None = runtime.context.get("user_id") if runtime.context else None
    tenant_id: str | None = runtime.context.get("tenant_id") if runtime.context else None

    try:
        if agent_name:
            # Custom agent — write to DB
            _create_agent_in_db(
                agent_name=agent_name,
                soul=soul,
                description=description,
                user_id=user_id,
                tenant_id=tenant_id,
            )
            logger.info(f"[agent_creator] Created custom agent '{agent_name}' in DB (user={user_id})")
        else:
            # Default agent — write global SOUL.md (filesystem remains for default)
            paths = get_paths()
            soul_file = paths.base_dir / "SOUL.md"
            soul_file.parent.mkdir(parents=True, exist_ok=True)
            soul_file.write_text(soul, encoding="utf-8")
            logger.info(f"[agent_creator] Updated global SOUL.md at {soul_file}")

        return Command(
            update={
                "created_agent_name": agent_name,
                "messages": [
                    ToolMessage(
                        content=f"Agent '{agent_name}' created successfully!",
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    except Exception as e:
        logger.error(f"[agent_creator] Failed to create agent '{agent_name}': {e}", exc_info=True)
        return Command(
            update={
                "messages": [
                    ToolMessage(content=f"Error: {e}", tool_call_id=runtime.tool_call_id)
                ]
            }
        )
