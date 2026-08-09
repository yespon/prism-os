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
from typing import Any

AgentLoader = Callable[[str, str | None, str | None], Any]
AgentLister = Callable[[str | None, str | None], list[Any]]
AgentPersister = Callable[..., None]

_agent_loader: AgentLoader | None = None
_agent_lister: AgentLister | None = None
_agent_persister: AgentPersister | None = None
_terminal_provider: dict[str, Any] | None = None
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


def load_runtime_adapters() -> None:
    """Import the configured adapter module once.

    No module is imported when the setting is absent, keeping the harness
    usable as a standalone package.
    """
    global _loaded_adapter_module
    module_name = os.getenv("PRISMOS_RUNTIME_ADAPTER_MODULE", "").strip()
    if not module_name or module_name == _loaded_adapter_module:
        return
    importlib.import_module(module_name)
    _loaded_adapter_module = module_name


def reset_runtime_adapters() -> None:
    """Reset registrations; intended for tests and process reinitialization."""
    global _agent_loader, _agent_lister, _agent_persister, _terminal_provider, _loaded_adapter_module
    _agent_loader = None
    _agent_lister = None
    _agent_persister = None
    _terminal_provider = None
    _loaded_adapter_module = None
