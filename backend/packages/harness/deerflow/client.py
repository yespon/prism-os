from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from deerflow.agents.lead_agent.prompt import apply_prompt_template
from deerflow.agents.lead_agent.agent import _build_middlewares
from deerflow.agents.thread_state import ThreadState
from deerflow.config import get_app_config, reload_app_config
from deerflow.config.tenant_context import tenant_context
from deerflow.models.factory import create_chat_model

logger = logging.getLogger(__name__)

AGENT_NAME_PATTERN = __import__("re").compile(r"^[A-Za-z0-9-]+$")


@dataclass(frozen=True, slots=True)
class StreamEvent:
    """A serialized event emitted by the DeerFlow client stream API."""

    type: str
    data: dict[str, Any]


class DeerFlowClient:
    def __init__(
        self,
        config_path: str | None = None,
        checkpointer=None,
        *,
        model_name: str | None = None,
        thinking_enabled: bool = True,
        subagent_enabled: bool = False,
        plan_mode: bool = False,
        agent_name: str | None = None,
    ):
        if config_path is not None:
            reload_app_config(config_path)
        self._app_config = get_app_config()

        if agent_name is not None and not AGENT_NAME_PATTERN.match(agent_name):
            raise ValueError(f"Invalid agent name '{agent_name}'. Must match pattern: {AGENT_NAME_PATTERN.pattern}")

        self._checkpointer = checkpointer
        self._model_name = model_name
        self._thinking_enabled = thinking_enabled
        self._subagent_enabled = subagent_enabled
        self._plan_mode = plan_mode
        self._agent_name = agent_name
        self._agent = None
        self._agent_config_key: tuple | None = None

    def _get_runnable_config(self, thread_id: str, **overrides) -> RunnableConfig:
        configurable = {
            "thread_id": thread_id,
            "user_id": overrides.get("user_id"),
            "model_name": overrides.get("model_name", self._model_name),
            "thinking_enabled": overrides.get("thinking_enabled", self._thinking_enabled),
            "is_plan_mode": overrides.get("plan_mode", self._plan_mode),
            "subagent_enabled": overrides.get("subagent_enabled", self._subagent_enabled),
        }
        if overrides.get("tenant_id") is not None:
            configurable["tenant_id"] = overrides.get("tenant_id")
        return RunnableConfig(
            configurable=configurable,
            recursion_limit=overrides.get("recursion_limit", 100),
        )

    def _ensure_agent(self, config: RunnableConfig):
        cfg = config.get("configurable", {})
        key = (
            cfg.get("model_name"),
            cfg.get("thinking_enabled"),
            cfg.get("is_plan_mode"),
            cfg.get("subagent_enabled"),
            cfg.get("tenant_id"),
            cfg.get("user_id"),
        )

        if self._agent is not None and self._agent_config_key == key:
            return

        thinking_enabled = cfg.get("thinking_enabled", True)
        model_name = cfg.get("model_name")
        subagent_enabled = cfg.get("subagent_enabled", False)
        max_concurrent_subagents = cfg.get("max_concurrent_subagents", 3)
        user_id = cfg.get("user_id")
        tenant_id = cfg.get("tenant_id")

        with tenant_context(user_id=user_id, tenant_id=tenant_id):
            kwargs: dict[str, Any] = {
                "model": create_chat_model(name=model_name, thinking_enabled=thinking_enabled),
                "tools": self._get_tools(model_name=model_name, subagent_enabled=subagent_enabled),
                "middleware": _build_middlewares(config, model_name=model_name, agent_name=self._agent_name),
                "system_prompt": apply_prompt_template(
                    subagent_enabled=subagent_enabled,
                    max_concurrent_subagents=max_concurrent_subagents,
                    agent_name=self._agent_name,
                    user_id=user_id,
                ),
                "state_schema": ThreadState,
            }
        checkpointer = self._checkpointer
        if checkpointer is None:
            from deerflow.agents.checkpointer import get_checkpointer

            checkpointer = get_checkpointer()
        if checkpointer is not None:
            kwargs["checkpointer"] = checkpointer

        from deerflow.agents import create_agent

        self._agent = create_agent(**kwargs)
        self._agent_config_key = key
        logger.info("Agent created: agent_name=%s, model=%s, thinking=%s", self._agent_name, model_name, thinking_enabled)

    @staticmethod
    def _get_tools(*, model_name: str | None, subagent_enabled: bool):
        from deerflow.tools import get_available_tools

        return get_available_tools(model_name=model_name, subagent_enabled=subagent_enabled)

    @staticmethod
    def _serialize_message(msg) -> dict:
        if isinstance(msg, AIMessage):
            d: dict[str, Any] = {"type": "ai", "content": msg.content, "id": getattr(msg, "id", None)}
            if msg.tool_calls:
                d["tool_calls"] = [{"name": tc["name"], "args": tc["args"], "id": tc.get("id")} for tc in msg.tool_calls]
            if getattr(msg, "usage_metadata", None):
                d["usage_metadata"] = msg.usage_metadata
            return d
        if isinstance(msg, ToolMessage):
            return {
                "type": "tool",
                "content": DeerFlowClient._extract_text(msg.content),
                "name": getattr(msg, "name", None),
                "tool_call_id": getattr(msg, "tool_call_id", None),
                "id": getattr(msg, "id", None),
            }
        if isinstance(msg, HumanMessage):
            return {"type": "human", "content": msg.content, "id": getattr(msg, "id", None)}
        if isinstance(msg, SystemMessage):
            return {"type": "system", "content": msg.content, "id": getattr(msg, "id", None)}
        return {"type": "unknown", "content": str(msg), "id": getattr(msg, "id", None)}

    @staticmethod
    def _extract_text(content) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            if content and all(isinstance(block, str) for block in content):
                chunk_like = len(content) > 1 and all(
                    isinstance(block, str)
                    and len(block) <= 20
                    and any(ch in block for ch in '{}[]":,')
                    for block in content
                )
                return "".join(content) if chunk_like else "\n".join(content)

            pieces: list[str] = []
            pending_str_parts: list[str] = []

            def flush_pending_str_parts() -> None:
                if pending_str_parts:
                    pieces.append("".join(pending_str_parts))
                    pending_str_parts.clear()

            for block in content:
                if isinstance(block, str):
                    pending_str_parts.append(block)
                    continue
                flush_pending_str_parts()
                if isinstance(block, dict):
                    text_value = block.get("text")
                    if isinstance(text_value, str):
                        pieces.append(text_value)
                        continue
                    if block.get("type") == "text":
                        maybe_text = block.get("text")
                        if isinstance(maybe_text, str):
                            pieces.append(maybe_text)
            flush_pending_str_parts()
            return "\n".join(piece for piece in pieces if piece)
        return str(content)
