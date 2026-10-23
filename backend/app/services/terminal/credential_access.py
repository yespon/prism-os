"""Current asset references and purpose-bound use of original Keychain values."""

import os

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.integrations.file_access import verify_member
from app.integrations.skill_reference_transactions import begin_reference_transaction
from app.models.assets import AssetGroup, Keychain
from deerflow.database import secrets_crypto
from deerflow.database.models import Tenant, TenantMembership
from deerflow.database.session import get_session
from deerflow.runtime import ExecutionTrustError


async def asset_session(request: Request, db: AsyncSession = Depends(get_session)):
    # Import after Terminal classes are initialized; importing the Gateway package
    # at module load recursively registers its Terminal/asset plugin routers.
    from app.gateway.authorization import require_tenant_context

    tenant = require_tenant_context(request)
    actor = getattr(request.state, "user_id", None)
    if request.method not in {"GET", "HEAD", "OPTIONS"} and not request.url.path.endswith("/test-connection"):
        await begin_reference_transaction(db, tenant)
        await db.exec(select(Tenant).where(Tenant.id == tenant).with_for_update())
        await db.exec(select(TenantMembership).where(TenantMembership.tenant_id == tenant, TenantMembership.user_id == actor).with_for_update())
    try:
        await verify_member(db, tenant, actor)
    except ExecutionTrustError:
        raise HTTPException(403, "Current asset membership unavailable") from None
    try:
        yield db
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Asset configuration conflicts with current references") from None


async def require_owned_binding(db, model, resource_id, tenant, actor):
    if not resource_id:
        return None
    row = await db.get(model, resource_id, populate_existing=True)
    if row is None or (row.tenant_id, row.user_id) != (tenant, actor):
        raise HTTPException(404, "Current asset reference unavailable")
    if model is Keychain and row.type not in {"password", "key", "ssh_key"}:
        raise HTTPException(409, "Selected credential has no SSH purpose")
    return row


async def verify_asset_bindings(db, body, tenant, actor):
    await require_owned_binding(db, Keychain, body.keychain_id, tenant, actor)
    await require_owned_binding(db, AssetGroup, body.group_id, tenant, actor)


def seal_keychain(value: str) -> str:
    if not value:
        raise HTTPException(422, "Credential input is empty")
    try:
        return secrets_crypto.encrypt_text_strict(value, os.getenv("DEERFLOW_SECRETS_ENCRYPTION_KEY"))
    except ValueError:
        raise HTTPException(503, "Credential encryption is not configured") from None


def ssh_credential_value(keychain: Keychain) -> str:
    if keychain.type not in {"password", "key", "ssh_key"}:
        raise PermissionError("Selected credential has no SSH purpose")
    value = keychain.value
    if value.startswith("enc:"):
        try:
            value = secrets_crypto.decrypt_text_strict(value, os.getenv("DEERFLOW_SECRETS_ENCRYPTION_KEY"))
        except ValueError:
            raise PermissionError("Selected credential cannot be decrypted") from None
    # Existing plaintext rows still require the current owner, asset and purpose.
    # New or updated persisted rows are always encrypted.
    if not value:
        raise PermissionError("Selected credential is empty")
    return value


async def rotate_keychain_storage(session, old_key: str, new_key: str, *, dry_run: bool):
    """Original maintenance transaction owns commit; strict failure rolls it back."""
    secrets_crypto.encrypt_text_strict("", new_key)  # Require the new key before mutation.
    rows = (await session.exec(select(Keychain).with_for_update())).scalars().all()
    for row in rows:
        plain = secrets_crypto.decrypt_text_strict(row.value, old_key) if row.value.startswith("enc:") else row.value
        encrypted = secrets_crypto.encrypt_text_strict(plain, new_key)
        if not dry_run:
            row.value = encrypted
            session.add(row)
    return len(rows)
