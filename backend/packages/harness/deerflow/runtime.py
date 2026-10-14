"""Optional application integrations for the standalone DeerFlow harness.

The harness exposes small provider seams instead of importing an application
package.  A host application can register providers directly or set
``PRISMOS_RUNTIME_ADAPTER_MODULE`` to a module that performs registration when
loaded.
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


class ExecutionTrustError(PermissionError):
    """A graph execution identity or one-use capability is untrusted."""


@dataclass(frozen=True)
class NativeAgentContext:
    """One local host read of native configuration and its Skill prompt."""

    record: Any
    skill_section: str | None


ExecutionValidator = Callable[[str | None, str, str, str, str | None], Any]


AgentLoader = Callable[[str, str | None, str | None], Any]
AgentLister = Callable[[str | None, str | None], list[Any]]
AgentPersister = Callable[..., None]

_agent_loader: AgentLoader | None = None
_agent_lister: AgentLister | None = None
_agent_persister: AgentPersister | None = None
_terminal_provider: dict[str, Any] | None = None
_governed_action_provider: Callable[[dict[str, str]], list[Any]] | None = None
_execution_validator: ExecutionValidator | None = None
_agent_identity_provider: Callable[..., Any] | None = None
_agent_context_provider: Callable[..., NativeAgentContext] | None = None
_skill_prompt_provider: Callable[..., str | None] | None = None
_skill_file_provider: Callable[..., Any] | None = None
_skill_command_provider: Callable[..., Any] | None = None
_file_access_provider: Callable[..., Any] | None = None
_loaded_adapter_module: str | None = None


def register_agent_config_provider(loader: AgentLoader, lister: AgentLister) -> None:
    """Register host-owned agent configuration accessors."""
    global _agent_loader, _agent_lister
    _agent_loader = loader
    _agent_lister = lister


def get_agent_config_provider() -> tuple[AgentLoader | None, AgentLister | None]:
    """Return the registered agent configuration accessors, if any."""
    return _agent_loader, _agent_lister


def register_agent_persistence_provider(persister: AgentPersister) -> None:
    """Register host-owned custom-agent persistence."""
    global _agent_persister
    _agent_persister = persister


def get_agent_persistence_provider() -> AgentPersister | None:
    """Return the registered custom-agent persistence callback."""
    return _agent_persister


def register_terminal_agent_provider(
    *, get_tools: Callable[[], list[Any]], set_context: Callable[[dict[str, Any]], None], system_prompt: str
) -> None:
    """Register host-owned terminal tools and prompt."""
    global _terminal_provider
    _terminal_provider = {
        "get_tools": get_tools,
        "set_context": set_context,
        "system_prompt": system_prompt,
    }


def get_terminal_agent_provider() -> dict[str, Any] | None:
    """Return the registered terminal integration, if any."""
    return _terminal_provider


def register_governed_action_provider(provider: Callable[[dict[str, str]], list[Any]]) -> None:
    """Register a host-owned Tool factory for a verified graph execution."""
    global _governed_action_provider
    _governed_action_provider = provider


def get_governed_action_provider() -> Callable[[dict[str, str]], list[Any]] | None:
    return _governed_action_provider


def register_execution_validator(validator: ExecutionValidator) -> None:
    """Register the host's durable one-use capability consumer."""
    global _execution_validator
    _execution_validator = validator


def get_execution_validator() -> ExecutionValidator | None:
    return _execution_validator


def register_agent_identity_provider(provider: Callable[..., Any]) -> None:
    global _agent_identity_provider
    _agent_identity_provider = provider


def get_agent_identity_provider():
    return _agent_identity_provider


def register_agent_context_provider(provider: Callable[..., NativeAgentContext]) -> None:
    global _agent_context_provider
    _agent_context_provider = provider


def get_agent_context_provider():
    return _agent_context_provider


def register_skill_prompt_provider(provider: Callable[..., str | None]) -> None:
    global _skill_prompt_provider
    _skill_prompt_provider = provider


def get_skill_prompt_provider():
    return _skill_prompt_provider


def register_skill_file_provider(provider: Callable[..., Any]) -> None:
    global _skill_file_provider
    _skill_file_provider = provider


def get_skill_file_provider():
    return _skill_file_provider


def register_skill_command_provider(provider: Callable[..., Any]) -> None:
    global _skill_command_provider
    _skill_command_provider = provider


def get_skill_command_provider():
    return _skill_command_provider


def register_file_access_provider(provider: Callable[..., Any]) -> None:
    global _file_access_provider
    _file_access_provider = provider


def current_file_access(runtime, operation, path):
    """Delegate host file access; native execution never falls back unchecked."""
    load_runtime_adapters()
    if _file_access_provider is not None:
        return _file_access_provider(runtime.context or {}, runtime.state or {}, operation, path)
    if (runtime.context or {}).get("agent_id") or (runtime.context or {}).get("tenant_id"):
        raise ExecutionTrustError("Current file authority unavailable")
    return None


def load_runtime_adapters() -> None:
    """Import the configured adapter module once.

    No module is imported when the setting is absent, keeping the harness
    usable as a standalone package.
    """
    global _loaded_adapter_module
    module_name = os.getenv("PRISMOS_RUNTIME_ADAPTER_MODULE", "").strip()
    if not module_name or module_name == _loaded_adapter_module:
        return
    module = importlib.import_module(module_name)
    register = getattr(module, "register_runtime_adapters", None)
    if callable(register):
        register()
    _loaded_adapter_module = module_name


def reset_runtime_adapters() -> None:
    """Reset registrations; intended for tests and process reinitialization."""
    global _agent_loader, _agent_lister, _agent_persister, _terminal_provider, _governed_action_provider, _execution_validator, _loaded_adapter_module
    global _skill_prompt_provider, _agent_identity_provider, _agent_context_provider, _skill_file_provider, _skill_command_provider, _file_access_provider
    _file_access_provider = None
    _skill_command_provider = None
    _skill_file_provider = None
    _agent_context_provider = None
    _agent_identity_provider = None
    _skill_prompt_provider = None
    _agent_loader = None
    _agent_lister = None
    _agent_persister = None
    _terminal_provider = None
    _governed_action_provider = None
    _execution_validator = None
    _loaded_adapter_module = None
