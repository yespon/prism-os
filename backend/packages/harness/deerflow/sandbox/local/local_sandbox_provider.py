import hashlib

from deerflow.sandbox.local.local_sandbox import LocalSandbox
from deerflow.sandbox.sandbox import Sandbox
from deerflow.sandbox.sandbox_provider import SandboxProvider

_shared_sandbox: LocalSandbox | None = None
_thread_sandboxes: dict[str, LocalSandbox] = {}


def _thread_bound_sandbox_id(user_id: str, thread_id: str, tenant_id: str | None = None) -> str:
    seed = f"{tenant_id or 'default'}:{user_id}:{thread_id}"
    digest = hashlib.sha1(seed.encode(), usedforsecurity=False).hexdigest()[:12]
    return f"local-{digest}"


class LocalSandboxProvider(SandboxProvider):
    def acquire(
        self,
        thread_id: str | None = None,
        user_id: str | None = None,
        tenant_id: str | None = None,
    ) -> str:
        global _shared_sandbox

        if thread_id is not None:
            if not user_id:
                raise ValueError("user_id is required when acquiring thread-bound sandbox")
            sandbox_id = _thread_bound_sandbox_id(user_id, thread_id, tenant_id=tenant_id)
            if sandbox_id not in _thread_sandboxes:
                _thread_sandboxes[sandbox_id] = LocalSandbox(sandbox_id)
            return sandbox_id

        if _shared_sandbox is None:
            _shared_sandbox = LocalSandbox("local")
        return _shared_sandbox.id

    def get(self, sandbox_id: str) -> Sandbox | None:
        if sandbox_id == "local":
            if _shared_sandbox is None:
                self.acquire()
            return _shared_sandbox
        if sandbox_id.startswith("local-"):
            return _thread_sandboxes.get(sandbox_id)
        return None

    def execute_scoped_command(self, command, skills_view, thread_data, *, env=None, validate=None):
        from deerflow.sandbox.local.scoped_command import execute_scoped_command

        return execute_scoped_command(command, skills_view, thread_data, env=env, validate=validate)

    def release(self, sandbox_id: str) -> None:
        # LocalSandbox instances are intentionally retained for reuse in local mode.
        # Note: This method is intentionally not called by SandboxMiddleware
        # to allow sandbox reuse across multiple turns in a thread.
        # For Docker-based providers (e.g., AioSandboxProvider), cleanup
        # happens at application shutdown via the shutdown() method.
        pass
