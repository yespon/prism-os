import importlib.util
import sys
from pathlib import Path


def _load_validator():
    project_root = Path(__file__).resolve().parents[2]
    module_path = project_root / "scripts" / "validate_runtime.py"
    spec = importlib.util.spec_from_file_location("prismos_runtime_validator", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


validator = _load_validator()


def test_available_config_passes_runtime_validation():
    project_root = Path(__file__).resolve().parents[2]
    local_config = project_root / "config.yaml"
    config = local_config if local_config.exists() else project_root / "config.example.yaml"

    result = validator.validate_config(config)

    assert result.errors == []


def test_sqlite_checkpointer_requires_a_connection_string(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(
        """
database:
  type: sqlite
  url: sqlite+aiosqlite:///.prismos/tenant.db
sandbox:
  use: LocalSandboxProvider
checkpointer:
  type: sqlite
""",
        encoding="utf-8",
    )

    result = validator.validate_config(config)

    assert "checkpointer.connection_string is required for sqlite" in result.errors


def test_invalid_sandbox_provider_is_rejected(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(
        """
database:
  type: sqlite
  url: sqlite+aiosqlite:///.prismos/tenant.db
sandbox:
  use: UnknownSandboxProvider
""",
        encoding="utf-8",
    )

    result = validator.validate_config(config)

    assert "sandbox.use must identify LocalSandboxProvider or AioSandboxProvider" in result.errors


def test_port_availability_detects_a_listener(monkeypatch):
    class BusySocket:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def setsockopt(self, *_):
            pass

        def bind(self, *_):
            raise OSError("address already in use")

    monkeypatch.setattr(validator.socket, "socket", lambda *_: BusySocket())

    assert validator.is_port_available(2026) is False


def test_invalid_yaml_is_reported_as_validation_error(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("database: [", encoding="utf-8")

    result = validator.validate_config(config)

    assert result.errors
    assert "could not parse" in result.errors[0]


def test_port_can_be_explicitly_allowed_for_existing_service(monkeypatch):
    monkeypatch.setattr(validator, "is_port_available", lambda _: False)
    result = validator.ValidationResult()

    validator.validate_port(2026, result, allow_in_use=True)

    assert result.errors == []
