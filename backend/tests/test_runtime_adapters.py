"""Contracts for the optional application integrations used by the harness."""

from __future__ import annotations

from deerflow.config.agents_config import AgentConfig
from deerflow.runtime import (
    get_agent_config_provider,
    get_agent_persistence_provider,
    get_terminal_agent_provider,
    load_runtime_adapters,
    register_agent_config_provider,
    register_agent_persistence_provider,
    register_terminal_agent_provider,
    reset_runtime_adapters,
)


def test_runtime_adapters_can_be_registered_and_reset() -> None:
    def load(name, user_id, tenant_id):
        return AgentConfig(name=name)

    def list_agents(user_id, tenant_id):
        return [AgentConfig(name="one")]

    def persist(**kwargs):
        return None

    def get_tools():
        return []

    def set_context(context):
        return None

    terminal = {
        "get_tools": get_tools,
        "set_context": set_context,
        "system_prompt": "terminal",
    }

    try:
        register_agent_config_provider(load, list_agents)
        register_agent_persistence_provider(persist)
        register_terminal_agent_provider(**terminal)

        assert get_agent_config_provider() == (load, list_agents)
        assert get_agent_persistence_provider() is persist
        assert get_terminal_agent_provider() == terminal
    finally:
        reset_runtime_adapters()

    assert get_agent_config_provider() == (None, None)
    assert get_agent_persistence_provider() is None
    assert get_terminal_agent_provider() is None


def test_load_runtime_adapters_imports_explicit_module(monkeypatch) -> None:
    module_name = "runtime_adapter_fixture_for_test"

    class AdapterModule:
        def register(self) -> None:
            register_agent_config_provider(
                lambda name, user_id, tenant_id: AgentConfig(name=name),
                lambda user_id, tenant_id: [],
            )
            register_agent_persistence_provider(lambda **kwargs: None)
            register_terminal_agent_provider(
                get_tools=lambda: [],
                set_context=lambda context: None,
                system_prompt="terminal",
            )

    adapter = AdapterModule()

    def import_module(name: str):
        assert name == module_name
        adapter.register()
        return adapter

    monkeypatch.setattr("deerflow.runtime.importlib.import_module", import_module)
    monkeypatch.setenv("PRISMOS_RUNTIME_ADAPTER_MODULE", module_name)
    reset_runtime_adapters()

    load_runtime_adapters()

    assert get_agent_config_provider()[0] is not None
    assert get_agent_persistence_provider() is not None
    assert get_terminal_agent_provider() is not None
    reset_runtime_adapters()


def test_adapter_module_registration_shape() -> None:
    """Keep the registration API usable by a host module's import side effect."""
    def register() -> None:
        register_agent_config_provider(
            lambda name, user_id, tenant_id: AgentConfig(name=name),
            lambda user_id, tenant_id: [],
        )
        register_agent_persistence_provider(lambda **kwargs: None)
        register_terminal_agent_provider(
            get_tools=lambda: [],
            set_context=lambda context: None,
            system_prompt="terminal",
        )

    reset_runtime_adapters()
    register()
    assert get_agent_config_provider()[0] is not None
    assert get_agent_persistence_provider() is not None
    assert get_terminal_agent_provider() is not None
    reset_runtime_adapters()
