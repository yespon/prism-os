"""Tests for lead agent runtime model resolution behavior."""

from __future__ import annotations

import pytest

from deerflow.agents.lead_agent import agent as lead_agent_module
from deerflow.config.app_config import AppConfig
from deerflow.config.model_config import ModelConfig
from deerflow.config.sandbox_config import SandboxConfig


def _make_app_config(models: list[ModelConfig]) -> AppConfig:
    return AppConfig(
        models=models,
        sandbox=SandboxConfig(use="deerflow.sandbox.local:LocalSandboxProvider"),
    )


def _make_model(name: str, *, supports_thinking: bool) -> ModelConfig:
    return ModelConfig(
        name=name,
        display_name=name,
        description=None,
        use="langchain_openai:ChatOpenAI",
        model=name,
        supports_thinking=supports_thinking,
        supports_vision=False,
    )


def test_resolve_model_name_raises_when_model_not_found(monkeypatch):
    app_config = _make_app_config(
        [
            _make_model("default-model", supports_thinking=False),
            _make_model("other-model", supports_thinking=True),
        ]
    )

    monkeypatch.setattr(lead_agent_module, "get_app_config", lambda: app_config)

    with pytest.raises(
        ValueError,
        match="not found in available models",
    ):
        lead_agent_module._resolve_model_name("missing-model")


def test_resolve_model_name_uses_first_when_no_model_specified(monkeypatch):
    app_config = _make_app_config(
        [
            _make_model("first-model", supports_thinking=False),
            _make_model("other-model", supports_thinking=True),
        ]
    )

    monkeypatch.setattr(lead_agent_module, "get_app_config", lambda: app_config)

    resolved = lead_agent_module._resolve_model_name(None)

    assert resolved == "first-model"


def test_resolve_model_name_raises_when_no_models_configured(monkeypatch):
    app_config = _make_app_config([])

    monkeypatch.setattr(lead_agent_module, "get_app_config", lambda: app_config)

    with pytest.raises(
        ValueError,
        match="No models configured",
    ):
        lead_agent_module._resolve_model_name("missing-model")


def test_make_lead_agent_disables_thinking_when_model_does_not_support_it(monkeypatch):
    app_config = _make_app_config([_make_model("safe-model", supports_thinking=False)])

    import deerflow.tools as tools_module

    monkeypatch.setattr(lead_agent_module, "get_app_config", lambda: app_config)
    monkeypatch.setattr(tools_module, "get_available_tools", lambda **kwargs: [])
    monkeypatch.setattr(lead_agent_module, "_build_middlewares", lambda config, model_name, agent_name=None: [])

    captured: dict[str, object] = {}

    def _fake_create_chat_model(*, name, thinking_enabled, reasoning_effort=None):
        captured["name"] = name
        captured["thinking_enabled"] = thinking_enabled
        captured["reasoning_effort"] = reasoning_effort
        return object()

    monkeypatch.setattr(lead_agent_module, "create_chat_model", _fake_create_chat_model)
    monkeypatch.setattr(lead_agent_module, "create_agent", lambda **kwargs: kwargs)

    result = lead_agent_module.make_lead_agent(
        {
            "configurable": {
                "model_name": "safe-model",
                "thinking_enabled": True,
                "is_plan_mode": False,
                "subagent_enabled": False,
            }
        }
    )

    assert captured["name"] == "safe-model"
    assert captured["thinking_enabled"] is False
    assert result["model"] is not None


def test_make_lead_agent_raises_when_requested_model_is_stale(monkeypatch):
    app_config = _make_app_config(
        [
            _make_model("default-model", supports_thinking=False),
            _make_model("other-model", supports_thinking=True),
        ]
    )

    import deerflow.tools as tools_module

    monkeypatch.setattr(lead_agent_module, "get_app_config", lambda: app_config)
    monkeypatch.setattr(tools_module, "get_available_tools", lambda **kwargs: [])
    monkeypatch.setattr(lead_agent_module, "_build_middlewares", lambda config, model_name, agent_name=None: [])

    with pytest.raises(
        ValueError,
        match="not found in available models",
    ):
        lead_agent_module.make_lead_agent(
            {
                "configurable": {
                    "model_name": "stale-model",
                    "thinking_enabled": False,
                    "is_plan_mode": False,
                    "subagent_enabled": False,
                }
            }
        )


def test_build_middlewares_uses_resolved_model_name_for_vision(monkeypatch):
    app_config = _make_app_config(
        [
            _make_model("stale-model", supports_thinking=False),
            ModelConfig(
                name="vision-model",
                display_name="vision-model",
                description=None,
                use="langchain_openai:ChatOpenAI",
                model="vision-model",
                supports_thinking=False,
                supports_vision=True,
            ),
        ]
    )

    monkeypatch.setattr(lead_agent_module, "get_app_config", lambda: app_config)
    monkeypatch.setattr(lead_agent_module, "_create_summarization_middleware", lambda *_args: None)
    monkeypatch.setattr(lead_agent_module, "_create_todo_list_middleware", lambda is_plan_mode: None)

    middlewares = lead_agent_module._build_middlewares(
        {"configurable": {"model_name": "stale-model", "is_plan_mode": False, "subagent_enabled": False}},
        model_name="vision-model",
    )

    assert any(isinstance(m, lead_agent_module.ViewImageMiddleware) for m in middlewares)


def test_make_lead_agent_rejects_model_outside_tenant_allowlist(monkeypatch):
    app_config = _make_app_config(
        [
            _make_model("default-model", supports_thinking=False),
            _make_model("tenant-model", supports_thinking=False),
        ]
    )

    import deerflow.tools as tools_module

    monkeypatch.setattr(lead_agent_module, "get_app_config", lambda: app_config)
    monkeypatch.setattr(lead_agent_module, "load_enabled_tenant_model_names", lambda tenant_id: ["tenant-model"])
    monkeypatch.setattr(lead_agent_module, "load_agent_config", lambda *args, **kwargs: None)
    monkeypatch.setattr(tools_module, "get_available_tools", lambda **kwargs: [])
    monkeypatch.setattr(lead_agent_module, "_build_middlewares", lambda config, model_name, agent_name=None: [])

    with pytest.raises(ValueError, match="not available for the current tenant"):
        lead_agent_module.make_lead_agent(
            {
                "configurable": {
                    "tenant_id": "tenant-a",
                    "model_name": "default-model",
                    "thinking_enabled": False,
                    "is_plan_mode": False,
                    "subagent_enabled": False,
                }
            }
        )


def test_make_lead_agent_uses_tenant_allowlist_default(monkeypatch):
    app_config = _make_app_config(
        [
            _make_model("default-model", supports_thinking=False),
            _make_model("tenant-model", supports_thinking=False),
        ]
    )

    import deerflow.tools as tools_module

    monkeypatch.setattr(lead_agent_module, "get_app_config", lambda: app_config)
    monkeypatch.setattr(lead_agent_module, "load_enabled_tenant_model_names", lambda tenant_id: ["tenant-model"])
    monkeypatch.setattr(lead_agent_module, "load_agent_config", lambda *args, **kwargs: None)
    monkeypatch.setattr(tools_module, "get_available_tools", lambda **kwargs: [])
    monkeypatch.setattr(lead_agent_module, "_build_middlewares", lambda config, model_name, agent_name=None: [])

    captured: dict[str, object] = {}

    def _fake_create_chat_model(*, name, thinking_enabled, reasoning_effort=None):
        captured["name"] = name
        captured["thinking_enabled"] = thinking_enabled
        captured["reasoning_effort"] = reasoning_effort
        return object()

    monkeypatch.setattr(lead_agent_module, "create_chat_model", _fake_create_chat_model)
    monkeypatch.setattr(lead_agent_module, "create_agent", lambda **kwargs: kwargs)

    result = lead_agent_module.make_lead_agent(
        {
            "configurable": {
                "tenant_id": "tenant-a",
                "thinking_enabled": False,
                "is_plan_mode": False,
                "subagent_enabled": False,
            }
        }
    )

    assert captured["name"] == "tenant-model"
    assert result["model"] is not None


def test_make_lead_agent_accepts_tenant_id_from_context(monkeypatch):
    app_config = _make_app_config(
        [
            _make_model("default-model", supports_thinking=False),
            _make_model("tenant-model", supports_thinking=False),
        ]
    )

    import deerflow.tools as tools_module

    monkeypatch.setattr(lead_agent_module, "get_app_config", lambda: app_config)
    monkeypatch.setattr(lead_agent_module, "load_enabled_tenant_model_names", lambda tenant_id: ["tenant-model"] if tenant_id == "tenant-a" else [])
    monkeypatch.setattr(lead_agent_module, "load_agent_config", lambda *args, **kwargs: None)
    monkeypatch.setattr(tools_module, "get_available_tools", lambda **kwargs: [])
    monkeypatch.setattr(lead_agent_module, "_build_middlewares", lambda config, model_name, agent_name=None: [])

    captured: dict[str, object] = {}

    def _fake_create_chat_model(*, name, thinking_enabled, reasoning_effort=None):
        captured["name"] = name
        captured["thinking_enabled"] = thinking_enabled
        captured["reasoning_effort"] = reasoning_effort
        return object()

    monkeypatch.setattr(lead_agent_module, "create_chat_model", _fake_create_chat_model)
    monkeypatch.setattr(lead_agent_module, "create_agent", lambda **kwargs: kwargs)

    result = lead_agent_module.make_lead_agent(
        {
            "context": {
                "tenant_id": "tenant-a",
                "thinking_enabled": False,
                "is_plan_mode": False,
                "subagent_enabled": False,
            }
        }
    )

    assert captured["name"] == "tenant-model"
    assert result["model"] is not None


def test_make_lead_agent_applies_tenant_context_to_prompt_building(monkeypatch):
    app_config = _make_app_config([_make_model("default-model", supports_thinking=False)])

    import deerflow.tools as tools_module

    monkeypatch.setattr(lead_agent_module, "get_app_config", lambda: app_config)
    monkeypatch.setattr(lead_agent_module, "load_agent_config", lambda *args, **kwargs: None)
    monkeypatch.setattr(lead_agent_module, "load_enabled_tenant_model_names", lambda tenant_id: ["default-model"])
    monkeypatch.setattr(tools_module, "get_available_tools", lambda **kwargs: [])
    monkeypatch.setattr(lead_agent_module, "_build_middlewares", lambda config, model_name, agent_name=None: [])
    monkeypatch.setattr(lead_agent_module, "create_chat_model", lambda **kwargs: object())
    monkeypatch.setattr(lead_agent_module, "create_agent", lambda **kwargs: kwargs)

    captured: dict[str, object] = {}

    def _fake_apply_prompt_template(*, subagent_enabled=False, max_concurrent_subagents=3, agent_name=None, available_skills=None, user_id=None):
        from deerflow.config.tenant_context import get_current_tenant_id

        captured["tenant_id"] = get_current_tenant_id()
        captured["user_id"] = user_id
        return "prompt"

    monkeypatch.setattr(lead_agent_module, "apply_prompt_template", _fake_apply_prompt_template)

    lead_agent_module.make_lead_agent(
        {
            "context": {
                "tenant_id": "tenant-a",
                "user_id": "user-a",
                "model_name": "default-model",
                "thinking_enabled": False,
                "is_plan_mode": False,
                "subagent_enabled": False,
            }
        }
    )

    assert captured == {"tenant_id": "tenant-a", "user_id": "user-a"}


def test_named_disabled_agent_does_not_fall_back_to_default(monkeypatch):
    monkeypatch.setattr(lead_agent_module, "load_agent_config", lambda *args, **kwargs: None)
    monkeypatch.setattr(lead_agent_module, "load_runtime_adapters", lambda: None)

    with pytest.raises(ValueError, match="unavailable or disabled"):
        lead_agent_module.make_lead_agent({"context": {"agent_name": "disabled-agent"}})
