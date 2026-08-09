from pathlib import Path

import pytest

import deerflow.config.home_migration as migration
from deerflow.config.home_migration import (
    apply_home_migration,
    plan_home_migration,
    verify_manifest,
)


def test_plan_is_non_mutating_and_counts_files(tmp_path: Path) -> None:
    source = tmp_path / ".opsintech"
    target = tmp_path / ".prismos"
    source.mkdir()
    (source / "tenant.db").write_bytes(b"db")

    plan = plan_home_migration(source, target)

    assert plan.file_count == 1
    assert plan.total_bytes == 2
    assert not target.exists()


def test_apply_copies_verifies_and_retains_source(tmp_path: Path) -> None:
    source = tmp_path / ".opsintech"
    target = tmp_path / ".prismos"
    source.mkdir()
    (source / "memory.json").write_text('{"ok": true}', encoding="utf-8")

    result = apply_home_migration(plan_home_migration(source, target))

    assert source.exists()
    assert (target / "memory.json").read_text(encoding="utf-8") == '{"ok": true}'
    assert verify_manifest(result.manifest_path).valid is True


def test_existing_nonempty_target_aborts_without_changes(tmp_path: Path) -> None:
    source = tmp_path / ".opsintech"
    target = tmp_path / ".prismos"
    source.mkdir()
    target.mkdir()
    (source / "source.db").write_bytes(b"source")
    (target / "keep.db").write_bytes(b"keep")

    with pytest.raises(FileExistsError):
        plan_home_migration(source, target)

    assert (target / "keep.db").read_bytes() == b"keep"


def test_symlink_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / ".opsintech"
    source.mkdir()
    (source / "external").symlink_to(tmp_path)

    with pytest.raises(ValueError, match="symbolic link"):
        plan_home_migration(source, tmp_path / ".prismos")


def test_insufficient_space_fails_before_target_creation(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / ".opsintech"
    target = tmp_path / ".prismos"
    source.mkdir()
    (source / "tenant.db").write_bytes(b"database")
    monkeypatch.setattr(migration, "_available_bytes", lambda _path: 0)

    with pytest.raises(OSError, match="Insufficient disk space"):
        plan_home_migration(source, target)

    assert not target.exists()


def test_open_file_risk_fails_preflight(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / ".opsintech"
    source.mkdir()
    (source / "tenant.db").write_bytes(b"database")
    monkeypatch.setattr(
        migration, "_open_files_under", lambda _source: (source / "tenant.db",)
    )

    with pytest.raises(RuntimeError, match="open file"):
        plan_home_migration(source, tmp_path / ".prismos")


def test_unreadable_source_fails_preflight(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / ".opsintech"
    source.mkdir()
    blocked = source / "config.yaml"
    blocked.write_text("x", encoding="utf-8")
    monkeypatch.setattr(migration, "_is_readable", lambda path: path != blocked)

    with pytest.raises(PermissionError, match="config.yaml"):
        plan_home_migration(source, tmp_path / ".prismos")


def test_checksum_mismatch_keeps_source_and_removes_temporary_target(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / ".opsintech"
    target = tmp_path / ".prismos"
    source.mkdir()
    (source / "memory.json").write_text("{}", encoding="utf-8")
    plan = plan_home_migration(source, target)
    monkeypatch.setattr(migration, "_hash_file", lambda _path: "bad-digest")

    with pytest.raises(ValueError, match="checksum"):
        apply_home_migration(plan)

    assert source.exists()
    assert not target.exists()
    assert not plan.temporary_target.exists()


def test_copy_failure_removes_only_this_run_temporary_target(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / ".opsintech"
    target = tmp_path / ".prismos"
    source.mkdir()
    (source / "tenant.db").write_bytes(b"db")
    unrelated = tmp_path / ".prismos.migrating-keep"
    unrelated.mkdir()
    plan = plan_home_migration(source, target)

    def fail_copy(*_args) -> None:
        raise OSError("copy interrupted")

    monkeypatch.setattr(migration, "_copy_record", fail_copy)

    with pytest.raises(OSError, match="copy interrupted"):
        apply_home_migration(plan)

    assert source.exists()
    assert unrelated.exists()
    assert not plan.temporary_target.exists()


def test_repeated_apply_is_stable_and_never_deletes_source(tmp_path: Path) -> None:
    source = tmp_path / ".opsintech"
    target = tmp_path / ".prismos"
    source.mkdir()
    (source / "tenant.db").write_bytes(b"db")
    plan = plan_home_migration(source, target)

    apply_home_migration(plan)

    with pytest.raises(FileExistsError):
        apply_home_migration(plan)

    assert source.exists()
    assert (target / "tenant.db").read_bytes() == b"db"


def test_manifest_rejects_path_escape(tmp_path: Path) -> None:
    target = tmp_path / ".prismos"
    target.mkdir()
    manifest = target / ".prismos-migration-manifest.json"
    manifest.write_text(
        '{"schema_version": 1, "status": "verified", "files": '
        '[{"relative_path": "../outside", "size": 0, "sha256": ""}]}',
        encoding="utf-8",
    )

    result = verify_manifest(manifest)

    assert result.valid is False
    assert any("escapes" in error for error in result.errors)
