from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import mimetypes
import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

import deerflow.agents as agents_module
from deerflow.agents import create_agent
from deerflow.agents.lead_agent.agent import _build_middlewares
from deerflow.agents.lead_agent.prompt import apply_prompt_template
from deerflow.agents.memory import updater as memory_updater
from deerflow.agents.thread_state import ThreadState
from deerflow.config import get_app_config, reload_app_config
from deerflow.config.extensions_config import ExtensionsConfig, get_extensions_config, reload_extensions_config
from deerflow.config.memory_config import get_memory_config
from deerflow.config.paths import get_paths
from deerflow.config.tenant_context import tenant_context
from deerflow.models.factory import create_chat_model
from deerflow.skills import loader as skills_loader
from deerflow.skills.installer import install_skill_from_archive
from deerflow.uploads import manager as upload_manager
from deerflow.utils import file_conversion

logger = logging.getLogger(__name__)

AGENT_NAME_PATTERN = __import__("re").compile(r"^[A-Za-z0-9-]+$")

# This import is intentionally module-level.  The client is a public harness
# boundary and callers/tests may replace the pure harness seam without importing
# the Gateway layer.
PathTraversalError = upload_manager.PathTraversalError


def get_uploads_dir(thread_id: str, user_id: str = "local", tenant_id: str | None = None) -> Path:
    """Resolve a Client upload directory using the harness-local user scope."""
    return upload_manager.get_uploads_dir(thread_id, user_id=user_id, tenant_id=tenant_id)


def ensure_uploads_dir(thread_id: str, user_id: str = "local", tenant_id: str | None = None) -> Path:
    """Create and resolve a Client upload directory using the local user scope."""
    return upload_manager.ensure_uploads_dir(thread_id, user_id=user_id, tenant_id=tenant_id)


_ORIGINAL_CREATE_AGENT = create_agent


def _get_create_agent():
    """Return the active agent factory across both supported injection seams."""
    if create_agent is not _ORIGINAL_CREATE_AGENT:
        return create_agent
    return agents_module.create_agent


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
        key_parts = [
            cfg.get("model_name"),
            cfg.get("thinking_enabled"),
            cfg.get("is_plan_mode"),
            cfg.get("subagent_enabled"),
        ]
        if cfg.get("tenant_id") is not None:
            key_parts.append(cfg["tenant_id"])
        if cfg.get("user_id") is not None:
            key_parts.append(cfg["user_id"])
        key = tuple(key_parts)

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

        self._agent = _get_create_agent()(**kwargs)
        self._agent_config_key = key
        logger.info("Agent created: agent_name=%s, model=%s, thinking=%s", self._agent_name, model_name, thinking_enabled)

    @staticmethod
    def _get_tools(*, model_name: str | None, subagent_enabled: bool):
        from deerflow.tools import get_available_tools

        return get_available_tools(model_name=model_name, subagent_enabled=subagent_enabled)

    @staticmethod
    def _serialize_message(msg) -> dict:
        if isinstance(msg, AIMessage):
            d: dict[str, Any] = {"type": "ai", "content": DeerFlowClient._extract_text(msg.content), "id": getattr(msg, "id", None)}
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

    @staticmethod
    def _model_to_dict(model: Any) -> dict[str, Any]:
        """Serialize the public, non-secret model configuration fields."""
        result: dict[str, Any] = {
            "name": getattr(model, "name", ""),
            "model": getattr(model, "model", getattr(model, "name", "")),
            "display_name": getattr(model, "display_name", None),
            "description": getattr(model, "description", None),
            "supports_thinking": bool(getattr(model, "supports_thinking", False)),
            "supports_reasoning_effort": bool(getattr(model, "supports_reasoning_effort", False)),
        }
        for field in ("supports_text2image", "enabled"):
            value = getattr(model, field, None)
            if isinstance(value, bool):
                result[field] = value
        for field in ("max_input_tokens", "model_type"):
            value = getattr(model, field, None)
            if isinstance(value, (int, str)) or value is None:
                result[field] = value
        return result

    @staticmethod
    def _skill_to_dict(skill: Any) -> dict[str, Any]:
        return {
            "name": getattr(skill, "name", ""),
            "description": getattr(skill, "description", ""),
            "license": getattr(skill, "license", None),
            "category": getattr(skill, "category", "custom"),
            "enabled": bool(getattr(skill, "enabled", True)),
        }

    def list_models(self) -> dict[str, list[dict[str, Any]]]:
        return {"models": [self._model_to_dict(model) for model in self._app_config.models]}

    def get_model(self, model_name: str) -> dict[str, Any] | None:
        model = self._app_config.get_model_config(model_name)
        return self._model_to_dict(model) if model is not None else None

    def list_skills(self, *, enabled_only: bool = False) -> dict[str, list[dict[str, Any]]]:
        return {"skills": [self._skill_to_dict(skill) for skill in skills_loader.load_skills(enabled_only=enabled_only)]}

    def get_skill(self, skill_name: str) -> dict[str, Any] | None:
        for skill in skills_loader.load_skills(enabled_only=False):
            if skill.name == skill_name:
                return self._skill_to_dict(skill)
        return None

    @staticmethod
    def _config_dump(value: Any) -> dict[str, Any]:
        if hasattr(value, "model_dump"):
            return value.model_dump(by_alias=True)
        return dict(value)

    def get_mcp_config(self) -> dict[str, Any]:
        config = get_extensions_config()
        return {
            "mcp_servers": {
                name: self._config_dump(server) for name, server in config.mcp_servers.items()
            }
        }

    @staticmethod
    def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
        """Write JSON via a same-directory temporary file and atomic replace."""
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temp_path.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
            os.replace(temp_path, path)
        except BaseException:
            temp_path.unlink(missing_ok=True)
            raise

    def _invalidate_agent(self) -> None:
        self._agent = None
        self._agent_config_key = None

    def update_mcp_config(self, mcp_servers: dict[str, Any]) -> dict[str, Any]:
        path = ExtensionsConfig.resolve_config_path()
        if path is None:
            raise FileNotFoundError("Cannot locate extensions config file")
        current = get_extensions_config()
        skills = getattr(current, "skills", {})
        skills_payload = {
            name: self._config_dump(state) for name, state in getattr(skills, "items", lambda: [])()
        }
        payload = {"mcpServers": mcp_servers, "skills": skills_payload}
        self._atomic_write_json(path, payload)
        reloaded = reload_extensions_config(path)
        self._invalidate_agent()
        return {
            "mcp_servers": {
                name: self._config_dump(server) for name, server in reloaded.mcp_servers.items()
            }
        }

    def update_skill(self, skill_name: str, *, enabled: bool) -> dict[str, Any]:
        skills = skills_loader.load_skills(enabled_only=False)
        if not any(skill.name == skill_name for skill in skills):
            raise ValueError(f"Skill '{skill_name}' not found")
        path = ExtensionsConfig.resolve_config_path()
        if path is None:
            raise FileNotFoundError("Cannot locate extensions config file")
        current = get_extensions_config()
        mcp_servers = getattr(current, "mcp_servers", {})
        mcp_payload = {
            name: self._config_dump(server) for name, server in getattr(mcp_servers, "items", lambda: [])()
        }
        skill_states = getattr(current, "skills", {})
        skill_payload = {
            name: self._config_dump(state) for name, state in getattr(skill_states, "items", lambda: [])()
        }
        skill_payload[skill_name] = {"enabled": enabled}
        self._atomic_write_json(path, {"mcpServers": mcp_payload, "skills": skill_payload})
        reload_extensions_config(path)
        updated = next((skill for skill in skills_loader.load_skills(enabled_only=False) if skill.name == skill_name), None)
        if updated is None:
            raise RuntimeError(f"Skill '{skill_name}' disappeared after configuration write")
        self._invalidate_agent()
        return self._skill_to_dict(updated)

    def install_skill(self, archive_path: str | Path) -> dict[str, Any]:
        if not Path(archive_path).exists():
            raise FileNotFoundError(f"Skill file not found: {archive_path}")
        if Path(archive_path).is_dir():
            raise ValueError(f"Path is not a file: {archive_path}")
        if Path(archive_path).suffix.lower() != ".skill":
            raise ValueError("File must have .skill extension")
        return install_skill_from_archive(archive_path)

    def get_memory(self) -> dict[str, Any]:
        return memory_updater.get_memory_data()

    def reload_memory(self) -> dict[str, Any]:
        return memory_updater.reload_memory_data()

    @staticmethod
    def _memory_config_to_dict(config: Any) -> dict[str, Any]:
        return {
            "enabled": bool(config.enabled),
            "storage_path": config.storage_path,
            "debounce_seconds": config.debounce_seconds,
            "max_facts": config.max_facts,
            "fact_confidence_threshold": config.fact_confidence_threshold,
            "injection_enabled": config.injection_enabled,
            "max_injection_tokens": config.max_injection_tokens,
        }

    def get_memory_config(self) -> dict[str, Any]:
        return self._memory_config_to_dict(get_memory_config())

    def get_memory_status(self) -> dict[str, Any]:
        return {"config": self.get_memory_config(), "data": self.get_memory()}

    def _thread_upload_dir(self, thread_id: str) -> Path:
        return ensure_uploads_dir(thread_id)

    @staticmethod
    def _convert_sync(path: Path) -> Path | None:
        return asyncio.run(file_conversion.convert_file_to_markdown(path))

    def _convert_upload(self, path: Path, executor: concurrent.futures.Executor | None) -> Path | None:
        if path.suffix.lower() not in file_conversion.CONVERTIBLE_EXTENSIONS:
            return None
        if executor is not None:
            return executor.submit(self._convert_sync, path).result()
        try:
            return asyncio.run(file_conversion.convert_file_to_markdown(path))
        except RuntimeError as exc:
            if "asyncio.run() cannot be called" not in str(exc):
                raise
            # The caller is already inside an event loop; isolate conversion in
            # one worker so this synchronous harness API remains usable there.
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(self._convert_sync, path).result()

    def upload_files(self, thread_id: str, paths: list[str | Path]) -> dict[str, Any]:
        uploads_dir = self._thread_upload_dir(thread_id)
        existing = {
            item["filename"] for item in upload_manager.list_files_in_dir(uploads_dir)["files"]
        }
        executor: concurrent.futures.ThreadPoolExecutor | None = None
        try:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                pass
            else:
                executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

            uploaded: list[dict[str, Any]] = []
            for source in paths:
                source_path = Path(source)
                if not source_path.exists():
                    raise FileNotFoundError(source_path)
                if not source_path.is_file():
                    raise ValueError(f"Path is not a file: {source_path}")
                filename = upload_manager.claim_unique_filename(source_path.name, existing)
                destination = uploads_dir / filename
                destination.write_bytes(source_path.read_bytes())
                info: dict[str, Any] = {
                    "filename": filename,
                    "size": str(destination.stat().st_size),
                    "path": str(destination),
                    "virtual_path": upload_manager.upload_virtual_path(filename),
                    "artifact_url": upload_manager.upload_artifact_url(thread_id, filename),
                    "attachment_id": upload_manager.upload_attachment_id(thread_id, filename),
                    "content_type": upload_manager.guess_content_type(filename),
                }
                if filename != source_path.name:
                    info["original_filename"] = source_path.name
                try:
                    markdown_path = self._convert_upload(destination, executor)
                except Exception:
                    logger.warning("Upload conversion failed for %s", filename, exc_info=True)
                    markdown_path = None
                if markdown_path is not None:
                    info["markdown_file"] = markdown_path.name
                uploaded.append(info)
            return {
                "success": True,
                "files": uploaded,
                "message": f"Successfully uploaded {len(uploaded)} file(s)",
            }
        finally:
            if executor is not None:
                executor.shutdown(wait=True)

    def list_uploads(self, thread_id: str) -> dict[str, Any]:
        result = upload_manager.list_files_in_dir(get_uploads_dir(thread_id))
        return upload_manager.enrich_file_listing(result, thread_id)

    def delete_upload(self, thread_id: str, filename: str) -> dict[str, Any]:
        return upload_manager.delete_file_safe(
            get_uploads_dir(thread_id), filename,
            convertible_extensions=file_conversion.CONVERTIBLE_EXTENSIONS,
        )

    def get_artifact(self, thread_id: str, path: str) -> tuple[bytes, str]:
        if not path.lstrip("/").startswith("mnt/user-data"):
            raise ValueError("Path must start with /mnt/user-data")
        try:
            actual = get_paths().resolve_virtual_path("local", thread_id, path)
        except ValueError as exc:
            raise PathTraversalError(str(exc)) from exc
        if not actual.exists():
            raise FileNotFoundError(path)
        if not actual.is_file():
            raise ValueError(f"Artifact path is not a file: {path}")
        return actual.read_bytes(), mimetypes.guess_type(str(actual))[0] or "application/octet-stream"

    def reset_agent(self) -> None:
        self._invalidate_agent()

    def stream(self, prompt: str, thread_id: str | None = None, **overrides) -> AsyncIterator[StreamEvent]:
        thread_id = thread_id or uuid.uuid4().hex
        config = self._get_runnable_config(thread_id, **overrides)
        self._ensure_agent(config)
        context = {
            "thread_id": thread_id,
            "agent_name": self._agent_name,
            "user_id": overrides.get("user_id"),
            "tenant_id": overrides.get("tenant_id"),
        }
        seen_ids: set[str] = set()
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        for chunk in self._agent.stream(
            {"messages": [HumanMessage(content=prompt)]},
            config=config,
            context=context,
            stream_mode=["messages-tuple", "values"],
        ):
            if not isinstance(chunk, dict):
                continue
            messages = chunk.get("messages", [])
            for message in messages:
                message_id = getattr(message, "id", None)
                if message_id is not None and message_id in seen_ids:
                    continue
                if message_id is not None:
                    seen_ids.add(message_id)
                serialized = self._serialize_message(message)
                message_usage = serialized.get("usage_metadata")
                if isinstance(message_usage, dict):
                    for key in usage:
                        usage[key] += message_usage.get(key, 0) or 0
                if serialized["type"] == "human":
                    continue
                yield StreamEvent(type="messages-tuple", data=serialized)
            yield StreamEvent(type="values", data=chunk)
        yield StreamEvent(type="end", data={"usage": usage})

    def chat(self, prompt: str, thread_id: str | None = None, **overrides) -> str:
        last_text = ""
        for event in self.stream(prompt, thread_id=thread_id, **overrides):
            if event.type == "messages-tuple" and event.data.get("type") == "ai":
                text = self._extract_text(event.data.get("content", ""))
                if text:
                    last_text = text
        return last_text
