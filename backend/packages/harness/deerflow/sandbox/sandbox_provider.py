import os
from abc import ABC, abstractmethod

from deerflow.config import get_app_config
from deerflow.reflection import resolve_class
from deerflow.sandbox.sandbox import Sandbox


class SandboxProvider(ABC):
    """Abstract base class for sandbox providers"""

    @abstractmethod
    def acquire(
        self,
        thread_id: str | None = None,
        user_id: str | None = None,
        tenant_id: str | None = None,
    ) -> str:
        """Acquire a sandbox environment and return its ID.

        Args:
            thread_id: Optional thread identifier.
            user_id: Optional user identifier for tenant isolation.
            tenant_id: Optional tenant identifier for sandbox isolation.

        Returns:
            The ID of the acquired sandbox environment.
        """
        pass

    @abstractmethod
    def get(self, sandbox_id: str) -> Sandbox | None:
        """Get a sandbox environment by ID.

        Args:
            sandbox_id: The ID of the sandbox environment to retain.
        """
        pass

    def execute_scoped_command(self, command, skills_view, thread_data, *, env=None, validate=None):
        raise PermissionError("This provider has no verified scoped command lease")

    @abstractmethod
    def release(self, sandbox_id: str) -> None:
        """Release a sandbox environment.

        Args:
            sandbox_id: The ID of the sandbox environment to destroy.
        """
        pass


_default_sandbox_provider: SandboxProvider | None = None


def _is_production_env() -> bool:
    for var_name in ("DEERFLOW_ENV", "APP_ENV", "ENV", "NODE_ENV"):
        value = os.getenv(var_name, "").strip().lower()
        if value in {"prod", "production"}:
            return True
    return False


_SANDBOX_PROVIDER_ALIASES = {
    "LocalSandboxProvider": "deerflow.sandbox.local:LocalSandboxProvider",
    "AioSandboxProvider": "deerflow.community.aio_sandbox:AioSandboxProvider",
}


def _resolve_sandbox_provider_path(use: str) -> str:
    """Resolve sandbox provider path, supporting short names.

    Args:
        use: Provider path or short name (e.g., "LocalSandboxProvider").

    Returns:
        Full module path (e.g., "deerflow.sandbox.local:LocalSandboxProvider").
    """
    stripped = use.strip()
    if ":" in stripped:
        return stripped
    return _SANDBOX_PROVIDER_ALIASES.get(stripped, stripped)


def _is_local_sandbox_provider(class_path: str) -> bool:
    resolved = _resolve_sandbox_provider_path(class_path)
    return resolved in {
        "deerflow.sandbox.local:LocalSandboxProvider",
        "deerflow.sandbox.local.local_sandbox_provider:LocalSandboxProvider",
    }


def get_sandbox_provider(**kwargs) -> SandboxProvider:
    """Get the sandbox provider singleton.

    Returns a cached singleton instance. Use `reset_sandbox_provider()` to clear
    the cache, or `shutdown_sandbox_provider()` to properly shutdown and clear.

    Returns:
        A sandbox provider instance.
    """
    global _default_sandbox_provider
    if _default_sandbox_provider is None:
        config = get_app_config()
        provider_path = _resolve_sandbox_provider_path(config.sandbox.use)
        if (
            _is_production_env()
            and _is_local_sandbox_provider(provider_path)
            and os.getenv("DEERFLOW_ALLOW_LOCAL_SANDBOX_IN_PROD", "").strip().lower() not in {"1", "true", "yes"}
        ):
            raise RuntimeError(
                "LocalSandboxProvider is disabled in production. "
                "Set DEERFLOW_ALLOW_LOCAL_SANDBOX_IN_PROD=true only for emergency fallback."
            )
        cls = resolve_class(provider_path, SandboxProvider)
        _default_sandbox_provider = cls(**kwargs)
    return _default_sandbox_provider


def reset_sandbox_provider() -> None:
    """Reset the sandbox provider singleton.

    This clears the cached instance without calling shutdown.
    The next call to `get_sandbox_provider()` will create a new instance.
    Useful for testing or when switching configurations.

    Note: If the provider has active sandboxes, they will be orphaned.
    Use `shutdown_sandbox_provider()` for proper cleanup.
    """
    global _default_sandbox_provider
    _default_sandbox_provider = None


def shutdown_sandbox_provider() -> None:
    """Shutdown and reset the sandbox provider.

    This properly shuts down the provider (releasing all sandboxes)
    before clearing the singleton. Call this when the application
    is shutting down or when you need to completely reset the sandbox system.
    """
    global _default_sandbox_provider
    if _default_sandbox_provider is not None:
        if hasattr(_default_sandbox_provider, "shutdown"):
            _default_sandbox_provider.shutdown()
        _default_sandbox_provider = None


def set_sandbox_provider(provider: SandboxProvider) -> None:
    """Set a custom sandbox provider instance.

    This allows injecting a custom or mock provider for testing purposes.

    Args:
        provider: The SandboxProvider instance to use.
    """
    global _default_sandbox_provider
    _default_sandbox_provider = provider
