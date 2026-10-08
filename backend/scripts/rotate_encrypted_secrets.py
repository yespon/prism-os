import argparse
import asyncio

from sqlmodel import select

from app.alerting.ticket_secrets import TicketSecretRepository
from deerflow.database.models import TenantMcpServer, TenantModelConfig, UserConfig
from deerflow.database.secrets_crypto import (
    decrypt_app_payload_with_key,
    decrypt_extensions_payload_with_key,
    decrypt_mcp_server_payload_with_key,
    decrypt_model_settings_with_key,
    encrypt_app_payload_with_key,
    encrypt_extensions_payload_with_key,
    encrypt_mcp_server_payload_with_key,
    encrypt_model_settings_with_key,
)
from deerflow.database.session import get_session_factory


async def _rotate(old_key: str, new_key: str, dry_run: bool) -> None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        user_configs = (await session.execute(select(UserConfig))).scalars().all()
        model_rows = (await session.execute(select(TenantModelConfig))).scalars().all()
        mcp_rows = (await session.execute(select(TenantMcpServer))).scalars().all()

        changed_user_configs = 0
        changed_models = 0
        changed_mcp = 0

        for row in user_configs:
            app_plain = decrypt_app_payload_with_key(row.app_config or {}, old_key)
            ext_plain = decrypt_extensions_payload_with_key(row.extensions_config or {}, old_key)
            app_new = encrypt_app_payload_with_key(app_plain, new_key)
            ext_new = encrypt_extensions_payload_with_key(ext_plain, new_key)
            if app_new != (row.app_config or {}) or ext_new != (row.extensions_config or {}):
                changed_user_configs += 1
                if not dry_run:
                    row.app_config = app_new
                    row.extensions_config = ext_new
                    session.add(row)

        for row in model_rows:
            plain = decrypt_model_settings_with_key(row.settings or {}, old_key)
            encrypted = encrypt_model_settings_with_key(plain, new_key)
            if encrypted != (row.settings or {}):
                changed_models += 1
                if not dry_run:
                    row.settings = encrypted
                    session.add(row)

        for row in mcp_rows:
            plain = decrypt_mcp_server_payload_with_key(
                {
                    "env": row.env or {},
                    "headers": row.headers or {},
                    "oauth": row.oauth,
                },
                old_key,
            )
            encrypted = encrypt_mcp_server_payload_with_key(plain, new_key)
            new_env = encrypted.get("env") or {}
            new_headers = encrypted.get("headers") or {}
            new_oauth = encrypted.get("oauth") if isinstance(encrypted.get("oauth"), dict) else None
            if new_env != (row.env or {}) or new_headers != (row.headers or {}) or new_oauth != row.oauth:
                changed_mcp += 1
                if not dry_run:
                    row.env = new_env
                    row.headers = new_headers
                    row.oauth = new_oauth
                    session.add(row)

        changed_ticket_secrets = await TicketSecretRepository().rotate_storage_key(
            session, old_key, new_key, dry_run=dry_run,
        )
        if not dry_run:
            await session.commit()

    mode = "dry-run" if dry_run else "apply"
    print(f"rotate-secrets {mode} done")
    print(f"user_configs_changed={changed_user_configs}")
    print(f"tenant_model_configs_changed={changed_models}")
    print(f"tenant_mcp_servers_changed={changed_mcp}")
    print(f"ticket_secrets_changed={changed_ticket_secrets}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rotate encrypted secret fields from old key to new key")
    parser.add_argument("--old-key", required=True, help="Current encryption key used by existing ciphertext")
    parser.add_argument("--new-key", required=True, help="Target encryption key for re-encryption")
    parser.add_argument("--dry-run", action="store_true", help="Show counts without writing changes")
    args = parser.parse_args()

    asyncio.run(_rotate(old_key=args.old_key, new_key=args.new_key, dry_run=args.dry_run))
