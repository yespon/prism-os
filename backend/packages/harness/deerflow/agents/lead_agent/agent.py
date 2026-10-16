from __future__ import annotations

import logging
import os

from langchain.agents import create_agent
from langgraph_sdk.runtime import ServerRuntime, _ReadRuntime

from deerflow.agents.lead_agent.prompt import apply_prompt_template
from deerflow.agents.middlewares.summarization_middleware import (
    DeerflowSummarizationMiddleware,
)
from deerflow.agents.middlewares.title_middleware import TitleMiddleware
from deerflow.agents.middlewares.todo_middleware import TodoMiddleware
from deerflow.agents.middlewares.tool_error_handling_middleware import (
    build_lead_runtime_middlewares,
)
from deerflow.agents.middlewares.view_image_middleware import ViewImageMiddleware
from deerflow.agents.thread_state import ThreadState
from deerflow.config import get_app_config
from deerflow.config.agents_config import (
    _db_agent_to_config,
    _run_async,
    load_agent_config,
)
from deerflow.config.summarization_config import get_summarization_config
from deerflow.config.tenant_context import tenant_context
from deerflow.config.title_config import get_title_config
from deerflow.database.user_config_store import load_enabled_tenant_model_names
from deerflow.models.factory import create_chat_model
from deerflow.runtime import (
    ExecutionTrustError,
    get_agent_context_provider,
    get_execution_middleware_provider,
    get_execution_validator,
    get_governed_action_provider,
    get_skill_prompt_provider,
    get_terminal_agent_provider,
    load_runtime_adapters,
)

logger = logging.getLogger(__name__)


def _create_summarization_middleware(model_name: str):
    """Create summarization middleware if enabled in config."""
    config = get_summarization_config()
    if config.enabled:
        return DeerflowSummarizationMiddleware(conversation_model_name=model_name)
    return None


def _create_todo_list_middleware(is_plan_mode: bool):
    return TodoMiddleware()


def _build_middlewares(config, model_name: str, agent_name: str | None = None):
    configurable = config.get("configurable", {})
    is_plan_mode = configurable.get("is_plan_mode", False)

    middlewares = list(build_lead_runtime_middlewares(lazy_init=True))

    summarization_middleware = _create_summarization_middleware(model_name)
    if summarization_middleware is not None:
        middlewares.append(summarization_middleware)

    todo_list_middleware = _create_todo_list_middleware(is_plan_mode)
    if todo_list_middleware is not None:
        middlewares.append(todo_list_middleware)

    model_config = get_app_config().get_model_config(model_name)
    if model_config and model_config.supports_vision:
        middlewares.append(ViewImageMiddleware())

    title_config = get_title_config()
    if title_config.enabled:
        middlewares.append(TitleMiddleware())

    return middlewares


def _resolve_model_name(requested_model_name: str | None, *, allowed_model_names: set[str] | None = None) -> str:
    app_config = get_app_config()
    available_names = [model.name for model in app_config.models]

    if not available_names:
        raise ValueError("No models configured")

    if requested_model_name:
        if allowed_model_names is not None and requested_model_name not in allowed_model_names:
            raise ValueError(f"Model '{requested_model_name}' is not available for the current tenant")
        if requested_model_name not in available_names:
            raise ValueError(f"Model '{requested_model_name}' not found in available models: {available_names}")
        return requested_model_name

    if allowed_model_names:
        for name in available_names:
            if name in allowed_model_names:
                return name
        raise ValueError("No tenant-allowed models configured")

    return available_names[0]


def _validate_execution_context(config: dict) -> dict[str, str] | None:
    """Consume trusted identity before assembling any Agent tools."""
    if os.getenv("PRISMOS_TRUSTED_GRAPH_CONTEXT", "off").lower() != "required" and not (config.get("configurable", {}).get("agent_id") or config.get("context", {}).get("agent_id")):
        return
    cfg = config.get("configurable", {}) or {}
    context = config.get("context", {}) or {}
    thread_id = cfg.get("thread_id") or context.get("thread_id")
    identity_claimed = bool(context) or any(key in cfg for key in ("user_id", "tenant_id", "agent_name", "agent_id", "is_bootstrap", "prismos_execution_capability"))
    if not thread_id and not identity_claimed:
        return  # schema/assistant discovery without an execution context
    for key in ("thread_id", "user_id", "tenant_id", "agent_name", "agent_id", "is_bootstrap", "prismos_execution_capability"):
        if key in cfg and key in context and cfg[key] != context[key]:
            raise ExecutionTrustError("conflicting graph execution context")
    user_id = cfg.get("user_id") or context.get("user_id")
    tenant_id = cfg.get("tenant_id") or context.get("tenant_id")
    agent_name = cfg.get("agent_name") or context.get("agent_name")
    token = cfg.get("prismos_execution_capability") or context.get("prismos_execution_capability")
    if not all((thread_id, user_id, tenant_id)):
        raise ExecutionTrustError("trusted graph execution identity required")
    if not isinstance(token, str) or not token:
        raise ExecutionTrustError("trusted execution capability required")
    load_runtime_adapters()
    validator = get_execution_validator()
    if validator is None:
        raise ExecutionTrustError("trusted graph execution validator unavailable")
    result = _run_async(validator(token, tenant_id, user_id, thread_id, agent_name))
    incident_id = result.get("incident_id") if isinstance(result, dict) else result
    agent_id = result.get("agent_id") if isinstance(result, dict) else None
    requested_id = cfg.get("agent_id") or context.get("agent_id")
    if requested_id is not None and requested_id != agent_id:
        raise ExecutionTrustError("native Agent selection is not covered by the capability")
    if incident_id or agent_id:
        authority = {key: result.get(key) for key in ("diagnosis_source_id", "diagnosis_source_revision", "diagnosis_incident_id")} if isinstance(result, dict) else {}
        return {"tenant_id": tenant_id, "user_id": user_id, "thread_id": thread_id, "agent_name": agent_name, "incident_id": incident_id, "agent_id": agent_id, **authority}



def _make_history_agent(config):
    """Reconstruct ordinary lead topology for SDK state/history formatting only.

    Gateway checks the current member and thread owner before forwarding reads.
    State inspection has no run identity and must not load current Agent/Skill
    resources (an owner may still read history after an Agent is paused).
    The SDK read handler only calls aget_state/aget_state_history on this graph.
    """
    from deerflow.tools import get_available_tools

    cfg = config.get("configurable", {}) or {}
    model_name = _resolve_model_name(cfg.get("model_name") or cfg.get("model"))
    return create_agent(
        model=create_chat_model(name=model_name, thinking_enabled=False),
        tools=get_available_tools(model_name=model_name, subagent_enabled=cfg.get("subagent_enabled", False)),
        middleware=_build_middlewares(config, model_name=model_name),
        state_schema=ThreadState,
    )


def make_lead_agent(config, runtime: ServerRuntime | None = None):
    # Only the SDK server supplies this object. A client config flag cannot turn
    # a run into a history read or consume/replay a one-use execution capability.
    if isinstance(runtime, _ReadRuntime) and runtime.access_context == "threads.read":
        return _make_history_agent(config)
    trusted_execution = _validate_execution_context(config)
    trusted_action = trusted_execution if trusted_execution and trusted_execution.get("incident_id") else None
    trusted_agent_id = trusted_execution.get("agent_id") if trusted_execution else None
    load_runtime_adapters()
    from deerflow.tools import get_available_tools
    from deerflow.tools.builtins import setup_agent

    cfg = config.get("configurable", {})
    runtime_context = config.get("context", {})

    thinking_enabled = cfg.get("thinking_enabled", runtime_context.get("thinking_enabled", True))
    reasoning_effort = cfg.get("reasoning_effort", runtime_context.get("reasoning_effort", None))
    requested_model_name = cfg.get("model_name") or cfg.get("model") or runtime_context.get("model_name") or runtime_context.get("model")
    is_plan_mode = cfg.get("is_plan_mode", runtime_context.get("is_plan_mode", False))
    subagent_enabled = cfg.get("subagent_enabled", runtime_context.get("subagent_enabled", False))
    max_concurrent_subagents = cfg.get("max_concurrent_subagents", runtime_context.get("max_concurrent_subagents", 3))
    is_bootstrap = cfg.get("is_bootstrap", runtime_context.get("is_bootstrap", False))
    agent_name = cfg.get("agent_name") or runtime_context.get("agent_name")
    user_id = cfg.get("user_id") or runtime_context.get("user_id")
    tenant_id = cfg.get("tenant_id") or runtime_context.get("tenant_id")
    skill_name = cfg.get("skill_name") or runtime_context.get("skill_name")

    if runtime_context and "configurable" in config:
        cfg.setdefault("user_id", user_id)
        cfg.setdefault("tenant_id", tenant_id)
        cfg.setdefault("is_plan_mode", is_plan_mode)

    if trusted_agent_id and is_bootstrap:
        raise ExecutionTrustError("Native Agent capability cannot select bootstrap mode")

    tenant_allowed_model_names: set[str] | None = None
    if isinstance(tenant_id, str) and tenant_id.strip():
        tenant_allowed_model_names = set(load_enabled_tenant_model_names(tenant_id.strip()))

    with tenant_context(user_id=user_id, tenant_id=tenant_id):
        # ------------------------------------------------------------------
        # Built-in Terminal Agent (SSH-based remote host operations)
        # ------------------------------------------------------------------
        if agent_name == "terminal-agent" and not trusted_agent_id:
            return _make_terminal_agent(config)

        native_context = None
        if trusted_agent_id:
            context_provider = get_agent_context_provider()
            if context_provider is None:
                raise ExecutionTrustError("Native Agent context provider unavailable")
            authority = {key: trusted_execution.get(key) for key in ("diagnosis_source_id", "diagnosis_source_revision", "diagnosis_incident_id")}
            native_context = context_provider(agent_name, user_id, tenant_id, trusted_agent_id, skill_name, cfg.get("skill_resource_id") or runtime_context.get("skill_resource_id"), **authority)
            if native_context is None or native_context.record is None:
                raise ExecutionTrustError("Current native Agent unavailable")
            agent_config = _db_agent_to_config(native_context.record)
        else:
            agent_config = load_agent_config(agent_name, user_id=user_id) if not is_bootstrap else None
        if agent_name and not is_bootstrap and agent_config is None:
            raise ValueError(f"Agent '{agent_name}' is unavailable or disabled")
        agent_model_name = agent_config.model if agent_config and agent_config.model else None

        model_name = _resolve_model_name(
            requested_model_name or agent_model_name,
            allowed_model_names=tenant_allowed_model_names,
        )

        app_config = get_app_config()
        model_config = app_config.get_model_config(model_name) if model_name else None

        if model_config is None:
            raise ValueError("No chat model could be resolved. Please configure at least one model in config.yaml or provide a valid 'model_name'/'model' in the request.")
        if thinking_enabled and not model_config.supports_thinking:
            logger.warning("Thinking mode is enabled but model '%s' does not support it; fallback to non-thinking mode.", model_name)
            thinking_enabled = False

        logger.info(
            "Create Agent(%s) -> thinking_enabled: %s, reasoning_effort: %s, model_name: %s, is_plan_mode: %s, subagent_enabled: %s, max_concurrent_subagents: %s, tenant_id: %s, skill_name: %s",
            agent_name or "default",
            thinking_enabled,
            reasoning_effort,
            model_name,
            is_plan_mode,
            subagent_enabled,
            max_concurrent_subagents,
            tenant_id,
            skill_name,
        )

        if "metadata" not in config:
            config["metadata"] = {}

        config["metadata"].update(
            {
                "agent_name": agent_name or "default",
                "model_name": model_name or "default",
                "thinking_enabled": thinking_enabled,
                "reasoning_effort": reasoning_effort,
                "is_plan_mode": is_plan_mode,
                "subagent_enabled": subagent_enabled,
                "tenant_id": tenant_id,
            }
        )

        if is_bootstrap:
            return create_agent(
                model=create_chat_model(name=model_name, thinking_enabled=thinking_enabled),
                tools=get_available_tools(model_name=model_name, subagent_enabled=subagent_enabled) + [setup_agent],
                middleware=_build_middlewares(config, model_name=model_name),
                system_prompt=apply_prompt_template(
                    subagent_enabled=subagent_enabled,
                    max_concurrent_subagents=max_concurrent_subagents,
                    available_skills={"bootstrap"},
                    user_id=user_id,
                ),
                state_schema=ThreadState,
            )

        agent_skills = set(agent_config.skills) if (agent_config and agent_config.skills is not None) else None
        effective_skills = {skill_name} if skill_name else agent_skills
        if native_context is not None:
            verified_skill_section = native_context.skill_section
        else:
            skill_provider = get_skill_prompt_provider()
            verified_skill_section = skill_provider(agent_name, tenant_id, user_id, skill_name, cfg.get("skill_resource_id") or runtime_context.get("skill_resource_id")) if skill_provider else None
        action_provider = get_governed_action_provider()
        action_tools = action_provider(trusted_action) if trusted_action and action_provider else []
        action_prompt = (
            "\nFor this incident diagnosis, create a ticket only if the evidence warrants one. Use create_governed_incident_ticket and report its returned platform status; never claim a ticket was created unless the status is submitted."
            if action_tools
            else ""
        )

        available_tools = get_available_tools(
            model_name=model_name,
            groups=agent_config.tool_groups if agent_config else None,
            subagent_enabled=subagent_enabled,
        )
        middleware_provider = get_execution_middleware_provider()
        execution_middlewares = middleware_provider(trusted_action) if trusted_action and middleware_provider else []
        governed_names = {tool.name for tool in action_tools if getattr(tool, "name", None)}
        available_tools = [tool for tool in available_tools if getattr(tool, "name", None) not in governed_names]
        return create_agent(
            model=create_chat_model(name=model_name, thinking_enabled=thinking_enabled, reasoning_effort=reasoning_effort),
            tools=available_tools + action_tools,
            middleware=_build_middlewares(config, model_name=model_name, agent_name=agent_name) + execution_middlewares,
            system_prompt=apply_prompt_template(
                subagent_enabled=subagent_enabled,
                max_concurrent_subagents=max_concurrent_subagents,
                agent_name=agent_name,
                available_skills=effective_skills if verified_skill_section is None else None,
                **({"skill_section_override": verified_skill_section} if verified_skill_section is not None else {}),
                **({"agent_soul_override": agent_config.system_prompt} if trusted_agent_id else {}),
                user_id=user_id,
            )
            + action_prompt,
            state_schema=ThreadState,
        )


def _make_terminal_agent(config: dict):
    """Build the built-in terminal agent for SSH-based remote host operations.

    Injects terminal-specific tools (execute_command, read_file, write_file,
    grep_search, web_fetch) and the terminal system prompt.
    """
    provider = get_terminal_agent_provider()
    if provider is None:
        raise RuntimeError("Terminal-agent tools are not configured by the host application")

    cfg = config.get("configurable", {})
    runtime_context = config.get("context", {}) or cfg  # LangGraph SDK puts context values into configurable

    is_bootstrap = cfg.get("is_bootstrap", runtime_context.get("is_bootstrap", False))

    # Extract terminal-specific context from the request
    terminal_context = {
        "mode": runtime_context.get("mode", "agent"),
        "selected_assets": runtime_context.get("selected_assets", []),
        "terminal_session_id": runtime_context.get("terminal_session_id", ""),
        "thread_id": runtime_context.get("thread_id") or cfg.get("thread_id"),
        "tenant_id": runtime_context.get("tenant_id", "default"),
        "user_id": runtime_context.get("user_id", "unknown"),
    }
    logger.info(f"[_make_terminal_agent] selected_assets: {len(terminal_context['selected_assets'])}, mode: {terminal_context['mode']}")
    if provider.get("authorize") is not None:
        provider["authorize"](terminal_context)
    provider["set_context"](terminal_context)

    # Resolve model
    requested_model_name = cfg.get("model_name") or cfg.get("model") or runtime_context.get("model_name") or runtime_context.get("model")
    current_tenant = runtime_context.get("tenant_id")
    allowed_models = set(load_enabled_tenant_model_names(current_tenant)) if isinstance(current_tenant, str) and current_tenant else None
    model_name = _resolve_model_name(requested_model_name or None, allowed_model_names=allowed_models)

    # Build the agent
    from deerflow.tools.builtins import setup_agent

    tools = provider["get_tools"]()
    if is_bootstrap:
        tools = tools + [setup_agent]

    return create_agent(
        model=create_chat_model(name=model_name),
        tools=tools,
        middleware=[],
        system_prompt=provider["system_prompt"],
        state_schema=ThreadState,
    )
