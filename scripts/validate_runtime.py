#!/usr/bin/env python3
"""Validate the host-side configuration needed to start PrismOS.

This deliberately validates only deployment prerequisites. Model credentials are
managed by the platform database and are therefore reported as a warning when
no model has been provisioned, rather than blocking a clean service bootstrap.
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _resolve_environment_references(value: Any, result: ValidationResult, path: str = "config") -> None:
    if isinstance(value, str) and value.startswith("$"):
        variable = value[1:]
        if not os.getenv(variable):
            result.errors.append(f"{path} references unset environment variable {variable}")
    elif isinstance(value, dict):
        for key, child in value.items():
            _resolve_environment_references(child, result, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _resolve_environment_references(child, result, f"{path}[{index}]")


def validate_config(config_path: Path) -> ValidationResult:
    result = ValidationResult()
    try:
        with config_path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except FileNotFoundError:
        result.errors.append(f"config file not found: {config_path}")
        return result
    except yaml.YAMLError as exc:
        result.errors.append(f"could not parse config YAML: {exc}")
        return result
    except OSError as exc:
        result.errors.append(f"could not read config file: {exc}")
        return result

    if not isinstance(data, dict):
        result.errors.append("config YAML root must be a mapping")
        return result

    _resolve_environment_references(data, result)

    database = data.get("database")
    if not isinstance(database, dict):
        result.errors.append("database must be a mapping")
    else:
        database_type = database.get("type")
        if database_type not in {"sqlite", "postgres"}:
            result.errors.append("database.type must be sqlite or postgres")
        if not database.get("url"):
            result.errors.append("database.url is required")

    sandbox = data.get("sandbox")
    if not isinstance(sandbox, dict):
        result.errors.append("sandbox must be a mapping")
    else:
        sandbox_use = str(sandbox.get("use", ""))
        if not (sandbox_use.endswith("LocalSandboxProvider") or sandbox_use.endswith("AioSandboxProvider")):
            result.errors.append("sandbox.use must identify LocalSandboxProvider or AioSandboxProvider")
        if sandbox_use.endswith("AioSandboxProvider") and sandbox.get("provisioner_url"):
            result.warnings.append("AioSandboxProvider uses an external provisioner; validate that service separately")

    checkpointer = data.get("checkpointer")
    if checkpointer is not None:
        if not isinstance(checkpointer, dict):
            result.errors.append("checkpointer must be a mapping")
        else:
            checkpointer_type = checkpointer.get("type")
            if checkpointer_type not in {"memory", "sqlite", "postgres"}:
                result.errors.append("checkpointer.type must be memory, sqlite, or postgres")
            elif checkpointer_type in {"sqlite", "postgres"} and not checkpointer.get("connection_string"):
                result.errors.append(f"checkpointer.connection_string is required for {checkpointer_type}")

    models = data.get("models")
    if not models:
        result.warnings.append("no models are defined in config.yaml; provision a model in the admin UI before making AI calls")

    return result


def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """Return whether a TCP port can be bound on the requested host."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def validate_port(port: int, result: ValidationResult, *, allow_in_use: bool = False) -> None:
    if not 1 <= port <= 65535:
        result.errors.append(f"PORT must be between 1 and 65535 (got {port})")
    elif not allow_in_use and not is_port_available(port):
        result.errors.append(
            f"PORT {port} is already in use; stop the owning service or start PrismOS with PORT=<free-port>"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--port", type=int)
    parser.add_argument(
        "--allow-port-in-use",
        action="store_true",
        help="Allow a port already owned by the caller's existing service",
    )
    args = parser.parse_args(argv)

    result = validate_config(args.config)
    if args.port is not None:
        validate_port(args.port, result, allow_in_use=args.allow_port_in_use)

    for warning in result.warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    for error in result.errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
