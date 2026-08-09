"""The single runtime boundary for PrismOS environment compatibility."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

BRIDGE_MINOR = "0.2.x"
REMOVE_IN_VERSION = "0.3.0"
logger = logging.getLogger(__name__)

LEGACY_ENV_ALIASES: dict[str, tuple[str, ...]] = {
    "PRISMOS_HOME": ("OPSINTECH_HOME",),
    "PRISMOS_CONFIG_PATH": ("OPSINTECH_CONFIG_PATH",),
    "PRISMOS_EXTENSIONS_CONFIG_PATH": ("OPSINTECH_EXTENSIONS_CONFIG_PATH",),
    "PRISMOS_HOST_BASE_DIR": ("OPSINTECH_HOST_BASE_DIR",),
    "PRISMOS_HOST_SKILLS_PATH": ("OPSINTECH_HOST_SKILLS_PATH",),
    "PRISMOS_SANDBOX_HOST": ("OPSINTECH_SANDBOX_HOST",),
    "PRISMOS_STORAGE_BACKEND": ("OPSINTECH_STORAGE_BACKEND",),
    "PRISMOS_STORAGE_LOCAL_ROOT": ("OPSINTECH_STORAGE_LOCAL_ROOT",),
    "PRISMOS_STORAGE_S3_ENDPOINT": ("OPSINTECH_STORAGE_S3_ENDPOINT",),
    "PRISMOS_STORAGE_S3_ACCESS_KEY": ("OPSINTECH_STORAGE_S3_ACCESS_KEY",),
    "PRISMOS_STORAGE_S3_SECRET_KEY": ("OPSINTECH_STORAGE_S3_SECRET_KEY",),
    "PRISMOS_STORAGE_S3_BUCKET": ("OPSINTECH_STORAGE_S3_BUCKET",),
    "PRISMOS_STORAGE_S3_REGION": ("OPSINTECH_STORAGE_S3_REGION",),
    "PRISMOS_STORAGE_S3_USE_SSL": ("OPSINTECH_STORAGE_S3_USE_SSL",),
    "PRISMOS_STORAGE_JUICEFS_MOUNT": ("OPSINTECH_STORAGE_JUICEFS_MOUNT",),
    "PRISMOS_STORAGE_JUICEFS_SUBDIR": ("OPSINTECH_STORAGE_JUICEFS_SUBDIR",),
}


class ConfigSource(StrEnum):
    PRISMOS = "PrismOS"
    LEGACY = "Legacy"
    DEFAULT = "Default"


@dataclass(frozen=True)
class ResolvedSetting:
    name: str
    value: str | None
    source: ConfigSource
    source_name: str


def resolve_setting(
    name: str,
    *,
    default: str | None = None,
    environ: Mapping[str, str] | None = None,
    validator: Callable[[str], str] | None = None,
) -> ResolvedSetting:
    values = os.environ if environ is None else environ
    legacy_names = LEGACY_ENV_ALIASES.get(name, ())

    if name in values:
        value = values[name]
        if validator:
            value = validator(value)
        conflicts = [legacy for legacy in legacy_names if legacy in values]
        if conflicts:
            logger.warning(
                "%s overrides conflicting legacy input(s): %s",
                name,
                ", ".join(conflicts),
            )
        return ResolvedSetting(name, value, ConfigSource.PRISMOS, name)

    for legacy in legacy_names:
        if legacy in values:
            value = values[legacy]
            if validator:
                value = validator(value)
            logger.warning(
                "%s is deprecated; use %s before removal in %s",
                legacy,
                name,
                REMOVE_IN_VERSION,
            )
            return ResolvedSetting(name, value, ConfigSource.LEGACY, legacy)

    value = validator(default) if validator and default is not None else default
    return ResolvedSetting(name, value, ConfigSource.DEFAULT, "default")


def legacy_usage_report(settings: Sequence[ResolvedSetting]) -> list[dict[str, str]]:
    return [
        {
            "name": item.name,
            "source": item.source.value,
            "source_name": item.source_name,
            "remove_in": REMOVE_IN_VERSION,
        }
        for item in settings
        if item.source is ConfigSource.LEGACY
    ]


def discover_legacy_home(canonical_home: Path) -> Path | None:
    """Report a sibling legacy home without selecting or mutating it."""
    legacy_home = canonical_home.with_name(".opsintech")
    if canonical_home.exists() or not legacy_home.is_dir():
        return None
    logger.warning(
        "Legacy PrismOS data detected at %s; run migrate_prismos_home.py before "
        "0.3.0. The directory was not selected or modified.",
        legacy_home,
    )
    return legacy_home
