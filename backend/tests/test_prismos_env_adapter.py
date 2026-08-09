import logging

import pytest

from deerflow.config.prismos_env import (
    ConfigSource,
    discover_legacy_home,
    legacy_usage_report,
    resolve_setting,
)


def non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


def test_prismos_value_wins_and_conflict_hides_values(caplog) -> None:
    caplog.set_level(logging.WARNING)
    result = resolve_setting(
        "PRISMOS_HOME",
        default="/default",
        environ={"PRISMOS_HOME": "/new", "OPSINTECH_HOME": "/secret-old"},
    )
    assert result.value == "/new"
    assert result.source is ConfigSource.PRISMOS
    assert "OPSINTECH_HOME" in caplog.text
    assert "/new" not in caplog.text
    assert "/secret-old" not in caplog.text


def test_legacy_value_is_read_with_removal_warning(caplog) -> None:
    caplog.set_level(logging.WARNING)
    result = resolve_setting(
        "PRISMOS_HOME",
        default="/default",
        environ={"OPSINTECH_HOME": "/legacy"},
    )
    assert result.value == "/legacy"
    assert result.source is ConfigSource.LEGACY
    assert result.source_name == "OPSINTECH_HOME"
    assert "0.3.0" in caplog.text


def test_invalid_new_value_never_falls_back_to_legacy() -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        resolve_setting(
            "PRISMOS_HOME",
            environ={"PRISMOS_HOME": " ", "OPSINTECH_HOME": "/legacy"},
            validator=non_blank,
        )


def test_default_and_usage_report_are_deterministic() -> None:
    result = resolve_setting("PRISMOS_HOME", default="/default", environ={})
    assert result.value == "/default"
    assert result.source is ConfigSource.DEFAULT
    assert legacy_usage_report([result]) == []


def test_legacy_home_is_discovered_without_becoming_active(tmp_path, caplog) -> None:
    canonical = tmp_path / ".prismos"
    legacy = tmp_path / ".opsintech"
    legacy.mkdir()
    caplog.set_level(logging.WARNING)
    assert discover_legacy_home(canonical) == legacy
    assert str(legacy) in caplog.text
    assert "migrate_prismos_home.py" in caplog.text
    assert not canonical.exists()
