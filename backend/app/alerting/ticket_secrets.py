"""Encrypted ticket credentials bound to a tenant, Source and immutable ref."""

import json
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import uuid4

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.alerting import AlertSource
from app.models.governance import PlatformTicketSecretRecord
from app.platform.contracts import SecretRef
from deerflow.database.secrets_crypto import decrypt_text_strict, encrypt_text_strict
from deerflow.database.session import get_session_factory


@dataclass(frozen=True)
class TicketSecretMaterial:
    webhook_url: str = field(repr=False)
    headers: dict[str, str] = field(repr=False)


def _validate_material(webhook_url: str, headers: dict[str, str]) -> None:
    try:
        parsed = urlsplit(webhook_url)
        valid = parsed.scheme == "https" and bool(parsed.hostname) and "@" not in parsed.netloc and not parsed.fragment
        _ = parsed.port
    except (ValueError, TypeError, AttributeError):
        valid = False
    if not valid or len(webhook_url) > 8192:
        raise ValueError("invalid secret webhook URL")
    if not isinstance(headers, dict) or len(headers) > 64:
        raise ValueError("invalid secret webhook headers")
    for name, value in headers.items():
        if (not isinstance(name, str) or name.lower() in {"host", "content-length", "transfer-encoding", "idempotency-key"} or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name)
                or not isinstance(value, str) or "\r" in value or "\n" in value or len(value) > 8192):
            raise ValueError("invalid secret webhook headers")


class TicketSecretRepository:
    """Caller controls transactions; create/disable never commit independently."""

    @staticmethod
    async def _source(session: AsyncSession, tenant_id: str, source_id: str) -> None:
        source = (await session.exec(select(AlertSource.id).where(
            AlertSource.tenant_id == tenant_id, AlertSource.id == source_id,
        ))).first()
        if source is None:
            raise PermissionError("ticket secret source unavailable")

    async def create(self, session: AsyncSession, tenant_id: str, source_id: str,
                     webhook_url: str, headers: dict[str, str]) -> SecretRef:
        await self._source(session, tenant_id, source_id)
        _validate_material(webhook_url, headers)
        ref = SecretRef(id=f"secret_{uuid4().hex}", tenant_id=tenant_id, source_id=source_id)
        payload = json.dumps({"reference": ref.model_dump(mode="json"), "webhook_url": webhook_url, "headers": headers},
                             sort_keys=True, separators=(",", ":"))
        ciphertext = encrypt_text_strict(payload, os.getenv("DEERFLOW_SECRETS_ENCRYPTION_KEY"))
        session.add(PlatformTicketSecretRecord(
            id=ref.id, tenant_id=tenant_id, source_id=source_id, purpose=ref.purpose,
            version=ref.version, encrypted_payload=ciphertext, active=True, created_at=datetime.now(UTC),
        ))
        await session.flush()
        return ref

    @staticmethod
    def _decode(row: PlatformTicketSecretRecord, ref: SecretRef, raw_key: str | None) -> TicketSecretMaterial:
        plaintext = decrypt_text_strict(row.encrypted_payload, raw_key)
        try:
            payload = json.loads(plaintext)
            if payload["reference"] != ref.model_dump(mode="json"):
                raise PermissionError("ticket secret binding mismatch")
            _validate_material(payload["webhook_url"], payload["headers"])
            return TicketSecretMaterial(webhook_url=payload["webhook_url"], headers=payload["headers"])
        except (ValueError, TypeError, KeyError):
            raise ValueError("invalid ticket secret payload") from None

    async def read(self, session: AsyncSession, tenant_id: str, source_id: str, ref: SecretRef) -> TicketSecretMaterial:
        if ref.tenant_id != tenant_id or ref.source_id != source_id:
            raise PermissionError("ticket secret unavailable")
        await self._source(session, tenant_id, source_id)
        row = (await session.exec(select(PlatformTicketSecretRecord).where(
            PlatformTicketSecretRecord.id == ref.id, PlatformTicketSecretRecord.tenant_id == tenant_id,
            PlatformTicketSecretRecord.source_id == source_id, PlatformTicketSecretRecord.active.is_(True),
            PlatformTicketSecretRecord.version == ref.version, PlatformTicketSecretRecord.purpose == ref.purpose,
        ))).first()
        if row is None:
            raise PermissionError("ticket secret unavailable")
        return self._decode(row, ref, os.getenv("DEERFLOW_SECRETS_ENCRYPTION_KEY"))

    async def disable(self, session: AsyncSession, tenant_id: str, source_id: str, ref: SecretRef) -> None:
        if ref.tenant_id != tenant_id or ref.source_id != source_id:
            raise PermissionError("ticket secret unavailable")
        row = (await session.exec(select(PlatformTicketSecretRecord).where(
            PlatformTicketSecretRecord.id == ref.id, PlatformTicketSecretRecord.tenant_id == tenant_id,
            PlatformTicketSecretRecord.source_id == source_id, PlatformTicketSecretRecord.version == ref.version,
            PlatformTicketSecretRecord.purpose == ref.purpose,
        ))).first()
        if row is None:
            raise PermissionError("ticket secret unavailable")
        row.active = False
        session.add(row)
        await session.flush()

    async def rotate_storage_key(self, session: AsyncSession, old_key: str, new_key: str, *, dry_run: bool) -> int:
        rows = (await session.exec(select(PlatformTicketSecretRecord))).all()
        for row in rows:
            ref = SecretRef(id=row.id, tenant_id=row.tenant_id, source_id=row.source_id,
                            purpose=row.purpose, version=row.version)
            self._decode(row, ref, old_key)
            plaintext = decrypt_text_strict(row.encrypted_payload, old_key)
            ciphertext = encrypt_text_strict(plaintext, new_key)
            if not dry_run:
                row.encrypted_payload = ciphertext
                session.add(row)
        return len(rows)


def ticket_secret_ref(config: dict, tenant_id: str, source_id: str | None) -> SecretRef | None:
    """Validate an opaque reference against trusted context without echoing input."""
    if "secret_ref" not in config:
        return None
    try:
        ref = SecretRef.model_validate(config["secret_ref"])
    except (ValueError, TypeError):
        raise ValueError("invalid ticket secret reference") from None
    if not source_id or ref.tenant_id != tenant_id or ref.source_id != source_id:
        raise PermissionError("ticket secret unavailable")
    if "webhook_url" in config or "headers" in config:
        raise ValueError("referenced ticket configuration cannot contain inline credentials")
    return ref


async def resolve_ticket_material(tenant_id: str, source_id: str | None, config: dict) -> TicketSecretMaterial | None:
    """Read current Source binding and decrypt locally; never change the config."""
    ref = ticket_secret_ref(config, tenant_id, source_id)
    if ref is None:
        return None
    async with get_session_factory()() as session:
        source = (await session.exec(select(AlertSource).where(
            AlertSource.tenant_id == tenant_id, AlertSource.id == source_id,
            AlertSource.status == "active",
        ))).first()
        if source is None or (source.config_json or {}).get("ticket") != config:
            raise PermissionError("ticket secret binding changed or unavailable")
        return await TicketSecretRepository().read(session, tenant_id, source_id, ref)


async def check_ticket_material(tenant_id: str, source_id: str | None, config: dict) -> None:
    """Preflight before consuming approval/reserving submission; retain no material."""
    await resolve_ticket_material(tenant_id, source_id, config)
