import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.alerting.ticket_secrets import TicketSecretRepository
from app.models.alerting import AlertSource
from app.models.governance import PlatformTicketSecretRecord
from app.platform.contracts import SecretRef
from deerflow.database.secrets_crypto import decrypt_text_strict, encrypt_text_strict


@pytest.mark.parametrize("key", [None, "", "   "])
def test_strict_crypto_requires_key(key):
    with pytest.raises(ValueError, match="encryption key required"):
        encrypt_text_strict("private-secret", key)
    with pytest.raises(ValueError, match="encryption key required"):
        decrypt_text_strict("enc:v1:invalid", key)


def test_strict_crypto_never_passes_through_plaintext_or_bad_ciphertext():
    ciphertext = encrypt_text_strict("enc:v1:private-secret", "old-key")
    assert decrypt_text_strict(ciphertext, "old-key") == "enc:v1:private-secret"
    for value, key in [(ciphertext, "wrong-key"), ("private-secret", "old-key"), ("enc:v1:broken", "old-key")]:
        with pytest.raises(ValueError, match="secret decryption failed") as exc:
            decrypt_text_strict(value, key)
        assert "private-secret" not in str(exc.value)
    assert decrypt_text_strict(encrypt_text_strict(decrypt_text_strict(ciphertext, "old-key"), "new-key"), "new-key") == "enc:v1:private-secret"


@pytest.fixture
async def secret_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DEERFLOW_SECRETS_ENCRYPTION_KEY", "test-key")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'secrets.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add_all([AlertSource(id="source-a", tenant_id="tenant-a", name="monitor-a"),
                         AlertSource(id="source-b", tenant_id="tenant-b", name="monitor-b")])
        await session.commit()
    yield factory
    await engine.dispose()


@pytest.mark.anyio
async def test_secret_is_encrypted_scoped_and_disableable(secret_db):
    repository = TicketSecretRepository()
    async with secret_db() as session:
        ref = await repository.create(session, "tenant-a", "source-a", "https://tickets.example/private-secret", {"Authorization": "Bearer private-secret"})
        await session.commit()
        assert isinstance(ref, SecretRef) and "private-secret" not in ref.model_dump_json()
        row = await session.get(PlatformTicketSecretRecord, ref.id)
        assert "private-secret" not in row.encrypted_payload
        material = await repository.read(session, "tenant-a", "source-a", ref)
        assert material.headers["Authorization"] == "Bearer private-secret"
        assert "private-secret" not in repr(material)
        for tenant, source in [("tenant-b", "source-a"), ("tenant-a", "source-b")]:
            with pytest.raises(PermissionError, match="unavailable"):
                await repository.read(session, tenant, source, ref)
        await repository.disable(session, "tenant-a", "source-a", ref)
        await session.commit()
        with pytest.raises(PermissionError, match="unavailable"):
            await repository.read(session, "tenant-a", "source-a", ref)


@pytest.mark.anyio
async def test_record_binding_detects_ciphertext_swap(secret_db):
    repository = TicketSecretRepository()
    async with secret_db() as session:
        first = await repository.create(session, "tenant-a", "source-a", "https://tickets.example/one", {"Authorization": "secret-one"})
        second = await repository.create(session, "tenant-a", "source-a", "https://tickets.example/two", {"Authorization": "secret-two"})
        await session.commit()
        first_row = await session.get(PlatformTicketSecretRecord, first.id)
        second_row = await session.get(PlatformTicketSecretRecord, second.id)
        first_row.encrypted_payload = second_row.encrypted_payload
        await session.commit()
        with pytest.raises(PermissionError, match="binding"):
            await repository.read(session, "tenant-a", "source-a", first)


@pytest.mark.anyio
async def test_write_rolls_back_and_missing_key_never_writes_plaintext(secret_db, monkeypatch):
    repository = TicketSecretRepository()
    async with secret_db() as session:
        ref = await repository.create(session, "tenant-a", "source-a", "https://tickets.example", {})
        await session.rollback()
        assert await session.get(PlatformTicketSecretRecord, ref.id) is None
        monkeypatch.delenv("DEERFLOW_SECRETS_ENCRYPTION_KEY")
        with pytest.raises(ValueError, match="encryption key required"):
            await repository.create(session, "tenant-a", "source-a", "https://tickets.example", {})
        with pytest.raises(PermissionError, match="unavailable"):
            await repository.create(session, "tenant-a", "source-b", "https://tickets.example", {})


def test_reference_forbids_extra_fields_and_unknown_version():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SecretRef(id="secret-1", tenant_id="tenant-a", source_id="source-a", version=2)
    with pytest.raises(ValidationError):
        SecretRef(id="secret-1", tenant_id="tenant-a", source_id="source-a", headers={"Authorization": "secret"})


@pytest.mark.anyio
async def test_storage_key_rotation_preserves_ref_and_supports_dry_run(secret_db, monkeypatch):
    repository = TicketSecretRepository()
    async with secret_db() as session:
        ref = await repository.create(session, "tenant-a", "source-a", "https://tickets.example", {"Authorization": "private-secret"})
        await session.commit()
        row = await session.get(PlatformTicketSecretRecord, ref.id)
        ciphertext = row.encrypted_payload
        assert await repository.rotate_storage_key(session, "test-key", "new-key", dry_run=True) == 1
        assert row.encrypted_payload == ciphertext
        assert await repository.rotate_storage_key(session, "test-key", "new-key", dry_run=False) == 1
        await session.commit()
        monkeypatch.setenv("DEERFLOW_SECRETS_ENCRYPTION_KEY", "new-key")
        assert (await repository.read(session, "tenant-a", "source-a", ref)).headers["Authorization"] == "private-secret"
        with pytest.raises(ValueError, match="decryption failed"):
            await repository.rotate_storage_key(session, "wrong-key", "other-key", dry_run=False)
        await session.rollback()
        assert (await repository.read(session, "tenant-a", "source-a", ref)).headers["Authorization"] == "private-secret"


@pytest.mark.anyio
async def test_reader_rejects_missing_key_and_changed_credential_gets_new_ref(secret_db, monkeypatch):
    repository = TicketSecretRepository()
    async with secret_db() as session:
        first = await repository.create(session, "tenant-a", "source-a", "https://tickets.example", {"Authorization": "old"})
        second = await repository.create(session, "tenant-a", "source-a", "https://tickets.example", {"Authorization": "new"})
        await session.commit()
        assert first.id != second.id
        assert (await repository.read(session, "tenant-a", "source-a", first)).headers["Authorization"] == "old"
        monkeypatch.delenv("DEERFLOW_SECRETS_ENCRYPTION_KEY")
        with pytest.raises(ValueError, match="encryption key required"):
            await repository.read(session, "tenant-a", "source-a", second)


@pytest.mark.anyio
async def test_invalid_secret_input_error_does_not_echo_credentials(secret_db):
    repository = TicketSecretRepository()
    async with secret_db() as session:
        with pytest.raises(ValueError) as exc:
            await repository.create(session, "tenant-a", "source-a", "https://tickets.example", {"Authorization": "private-secret\r\ninjected"})
        assert "private-secret" not in str(exc.value)
