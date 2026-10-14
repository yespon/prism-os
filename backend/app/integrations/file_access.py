"""Current access using original membership, thread and Native Agent facts."""

from sqlalchemy import select

from app.models.governance import PlatformThreadBindingRecord
from deerflow.database.models import Tenant, TenantMembership
from deerflow.runtime import ExecutionTrustError
from deerflow.sandbox.file_access import owned_path, read_owned_file


async def verify_member(session, tenant, actor):
    if not tenant or not actor:
        raise ExecutionTrustError("Current member unavailable")
    current = await session.get(Tenant, tenant, populate_existing=True)
    member = (
        (
            await session.exec(
                select(TenantMembership)
                .where(
                    TenantMembership.tenant_id == tenant,
                    TenantMembership.user_id == actor,
                    TenantMembership.status == "active",
                )
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .first()
    )
    if current is None or current.status != "active" or member is None:
        raise ExecutionTrustError("Current member unavailable")


async def verify_thread(session, tenant, actor, thread):
    await verify_member(session, tenant, actor)
    binding = await session.get(PlatformThreadBindingRecord, thread, populate_existing=True)
    if binding is None or (binding.tenant_id, binding.user_id) != (tenant, actor):
        raise ExecutionTrustError("Current thread unavailable")
    return binding


def thread_roots(paths, tenant, actor, thread):
    return {key: getattr(paths, "sandbox_" + ("work" if key == "workspace" else key) + "_dir")(actor, thread, tenant_id=tenant) for key in ("workspace", "uploads", "outputs")}


async def runtime_file_access(context, state, operation, path, factory):
    # A standalone harness has no tenant facts. A host identity must never
    # fall back on forged runtime directories or a global sandbox.
    if not context.get("tenant_id") and not context.get("agent_id"):
        return None
    from app import runtime_adapters
    from deerflow.config.paths import get_paths

    action = operation[0] if isinstance(operation, tuple) else operation
    tenant, actor, thread = (context.get(key) for key in ("tenant_id", "user_id", "thread_id"))

    async def verify(session):
        binding = await verify_thread(session, tenant, actor, thread)
        await runtime_adapters.verify_runtime_selection(session, runtime_adapters._scoped_context(context))
        if binding.agent_name is not None and binding.agent_name != (context.get("agent_name") or "__default__"):
            raise ExecutionTrustError("Current thread Agent unavailable")

    try:
        async with factory() as session:
            await verify(session)
        if path.startswith("/mnt/skills/"):
            if action not in {"read", "read_bytes", "ls"}:
                raise ExecutionTrustError("Skill sources are read-only")
            result = runtime_adapters._current_skill_member(context, operation, path, "/mnt/skills")
            if result is None:
                raise ExecutionTrustError("Selected Skill authority unavailable")
        else:
            roots = thread_roots(get_paths(), tenant, actor, thread)
            expected = {key + "_path": str(value) for key, value in roots.items()}
            if state.get("thread_data") != expected:
                raise ExecutionTrustError("Runtime directories differ from the current owner")
            actual, virtual = owned_path(path, roots)
            if operation == "present" and not virtual.startswith("/mnt/user-data/outputs/"):
                raise ExecutionTrustError("Only owned outputs can be presented")
            if action in {"write", "replace"}:
                from deerflow.sandbox.file_access import mutate_owned_file

                result = mutate_owned_file(actual, operation)
            elif action == "ls":
                # List through held directories; never expose symlink targets.
                import os

                from deerflow.skills.resource_deletion_files import OwnedRemoval

                directory = OwnedRemoval(actual)
                try:
                    import stat

                    from deerflow.sandbox.local.list_dir import _should_ignore

                    result = []
                    for name in sorted(os.listdir(directory.fd)):
                        info = os.stat(name, dir_fd=directory.fd, follow_symlinks=False)
                        if _should_ignore(name) or stat.S_ISLNK(info.st_mode):
                            continue
                        shown = virtual.rstrip("/") + "/" + name
                        result.append(shown + ("/" if stat.S_ISDIR(info.st_mode) else ""))
                        if stat.S_ISDIR(info.st_mode):
                            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory.fd)
                            try:
                                held = os.fstat(child)
                                if (held.st_dev, held.st_ino) != (info.st_dev, info.st_ino):
                                    raise ExecutionTrustError("Directory changed during listing")
                                for nested in sorted(os.listdir(child)):
                                    part = os.stat(nested, dir_fd=child, follow_symlinks=False)
                                    if not _should_ignore(nested) and not stat.S_ISLNK(part.st_mode):
                                        result.append(shown + "/" + nested + ("/" if stat.S_ISDIR(part.st_mode) else ""))
                                current = os.stat(name, dir_fd=directory.fd, follow_symlinks=False)
                                if (held.st_dev, held.st_ino) != (current.st_dev, current.st_ino):
                                    raise ExecutionTrustError("Directory replaced during listing")
                            finally:
                                os.close(child)
                    directory.check_parent()
                finally:
                    directory.close()
            else:
                data = read_owned_file(actual)
                result = virtual if operation == "present" else data.decode("utf-8") if operation == "read" else data
        async with factory() as session:
            await verify(session)
        return result
    except Exception:
        raise ExecutionTrustError("Current file or resource access unavailable") from None
