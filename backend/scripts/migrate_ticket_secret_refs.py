"""Migrate one bounded tenant batch; default is a read-only dry-run.

Run from backend: uv run --locked python -m scripts.migrate_ticket_secret_refs
  --config /path/to/deployment-config.yaml --tenant TENANT [--source-id SOURCE]
Add --apply only after backup and a successful dry-run against the same database.
Keys come from the deployment environment, never from command-line arguments.
"""

import argparse
import asyncio
import json
import os
from pathlib import Path

import yaml
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.alerting.ticket_secret_migration import TicketMigrationError, maintenance_privacy, migrate_ticket_secret_refs


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--tenant", required=True)
    result.add_argument("--config", help="Explicit deployment config; defaults to PRISMOS_CONFIG_PATH only")
    result.add_argument("--source-id", action="append", default=[])
    result.add_argument("--limit", type=int, default=100)
    result.add_argument("--apply", action="store_true")
    return result


def _database_url(config_path: str | None) -> str:
    try:
        if not config_path or not Path(config_path).is_file():
            raise ValueError
        config = yaml.safe_load(Path(config_path).read_text())
        value = config["database"]["url"]
        if not isinstance(value, str) or not value:
            raise ValueError
        # Match AppConfig's documented whole-value $VARIABLE expansion.
        if value.startswith("$"):
            value = os.environ[value[1:]]
        parsed = make_url(value)
        if parsed.drivername not in {"sqlite+aiosqlite", "postgresql+asyncpg", "postgresql+psycopg"}:
            raise ValueError
        if parsed.drivername == "sqlite+aiosqlite":
            if not parsed.database or not Path(parsed.database).is_file() or parsed.query:
                raise ValueError
        elif not parsed.database or not parsed.host:
            raise ValueError
        return value
    except Exception:
        raise TicketMigrationError("explicit_database_configuration_required") from None


async def run(args) -> dict:
    engine = None
    with maintenance_privacy():
        try:
            value = _database_url(args.config or os.getenv("PRISMOS_CONFIG_PATH"))
            options = {"statement_cache_size": 0} if make_url(value).drivername == "postgresql+asyncpg" else {}
            engine = create_async_engine(value, echo=False, hide_parameters=True, connect_args=options)
            factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            report = await migrate_ticket_secret_refs(factory, args.tenant, apply=args.apply, source_ids=tuple(args.source_id), limit=args.limit)
            return {"status": "succeeded", **report.as_dict()}
        except TicketMigrationError as error:
            unknown = str(error) == "commit_outcome_unknown"
            return {"status": "unknown" if unknown else "aborted", "mode": "apply" if args.apply else "dry-run", "migrated": None if unknown else 0, "reason": str(error)}
        except Exception:
            return {"status": "aborted", "mode": "apply" if args.apply else "dry-run", "migrated": 0, "reason": "storage_or_audit_unavailable"}
        finally:
            if engine is not None:
                try:
                    await engine.dispose()
                except Exception:
                    pass  # Preserve the already established transaction outcome.


def main() -> int:
    args = parser().parse_args()
    result = asyncio.run(run(args))
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "succeeded" else 2


if __name__ == "__main__":
    raise SystemExit(main())
