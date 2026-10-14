"""Original terminal member, chat, asset and credential purpose authorization."""

import asyncio
from copy import deepcopy

from app.integrations.file_access import verify_member, verify_thread
from app.models.assets import Keychain, LocalAsset
from app.models.terminal import ChatSession, TerminalSession
from deerflow.database.session import get_session_factory
from deerflow.runtime import ExecutionTrustError


async def verify_terminal_access(context, asset_id=None, *, factory=None):
    tenant, actor = context.get("tenant_id"), context.get("user_id")
    async with (factory or get_session_factory())() as db:
        await verify_member(db, tenant, actor)
        if context.get("thread_id"):
            binding = await verify_thread(db, tenant, actor, context["thread_id"])
            if binding.agent_name != "terminal-agent":
                raise ExecutionTrustError("Current terminal thread unavailable")
        if context.get("chat_session_id"):
            chat = await db.get(ChatSession, context["chat_session_id"], populate_existing=True)
            if chat is None or (chat.tenant_id, chat.user_id) != (tenant, actor):
                raise ExecutionTrustError("Current terminal history unavailable")
        if context.get("terminal_session_id"):
            current = await db.get(TerminalSession, context["terminal_session_id"], populate_existing=True)
            if current is not None and ((current.tenant_id, current.user_id) != (tenant, actor) or not current.is_active):
                raise ExecutionTrustError("Current terminal session unavailable")
        if asset_id is None:
            return None, None
        asset = await db.get(LocalAsset, asset_id, populate_existing=True)
        if asset is None or (asset.tenant_id, asset.user_id) != (tenant, actor):
            raise ExecutionTrustError("Current terminal asset unavailable")
        keychain = None
        if asset.keychain_id:
            keychain = await db.get(Keychain, asset.keychain_id, populate_existing=True)
            if keychain is None or (keychain.tenant_id, keychain.user_id) != (tenant, actor):
                raise ExecutionTrustError("Current terminal credential purpose unavailable")
        return asset, keychain


def asset_fingerprint(asset, keychain):
    # Kept inside the lease only, never emitted in errors, audit or outputs.
    return asset.model_dump(), keychain.model_dump() if keychain is not None else None


async def terminal_lease_validator(context, asset_id):
    initial = asset_fingerprint(*await verify_terminal_access(context, asset_id))
    async def validate():
        if asset_fingerprint(*await verify_terminal_access(context, asset_id)) != initial:
            raise ExecutionTrustError("Current terminal asset or credential changed; external effects unknown")
    return validate


async def current_terminal_stream(iterator, context, asset_ids=()):
    """Guard waits and every delivery; close local work without claiming remote undo."""
    context = deepcopy(context)
    await verify_terminal_access(context)
    validators = [await terminal_lease_validator(context, asset) for asset in dict.fromkeys(asset_ids) if asset]
    pending = None
    try:
        while True:
            await verify_terminal_access(context)
            for validate in validators:
                await validate()
            pending = asyncio.create_task(anext(iterator))
            while not pending.done():
                await asyncio.wait({pending}, timeout=.25)
                await verify_terminal_access(context)
                for validate in validators:
                    await validate()
            try:
                value = pending.result()
            except StopAsyncIteration:
                break
            await verify_terminal_access(context)
            for validate in validators:
                await validate()
            yield value
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        await iterator.aclose()


async def record_terminal_unknown(context, asset_id, command, audit_id, reason):
    """Original audit fact for an already-owned lease; withdrawal cannot erase it."""
    from app.models.terminal import CommandAuditLog

    async with get_session_factory()() as db:
        existing = await db.get(CommandAuditLog, audit_id)
        if existing is not None:
            return
        db.add(CommandAuditLog(
            id=audit_id, tenant_id=context["tenant_id"], user_id=context["user_id"],
            terminal_session_id=context.get("terminal_session_id", ""), asset_id=asset_id,
            command=command, mode=context.get("mode", "agent"), security_action="unknown",
            stdout=None, stderr=reason + "; local transport closed or interrupted; remote external effects unknown",
            return_code=None,
        ))
        await db.commit()
