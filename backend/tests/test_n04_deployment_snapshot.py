"""Backup failures must restore service availability and cannot escape owned paths."""
import importlib.util
import json
import stat
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    spec = importlib.util.spec_from_file_location('n04_snapshot_test', ROOT / 'scripts/octop_wsl_test_snapshot.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    (tmp_path / 'backend/tmp').mkdir(parents=True)
    return module


def test_private_snapshot_file_cannot_overwrite_original(snapshot, tmp_path):
    file = tmp_path / 'private-file'
    snapshot.private_write(file, b'original private bytes')
    assert stat.S_IMODE(file.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        snapshot.private_write(file, b'overwrite')
    assert file.read_bytes() == b'original private bytes'


def test_snapshot_rejects_alias_and_foreign_runtime(snapshot, tmp_path):
    other = tmp_path / 'other-project'
    other.mkdir()
    alias = tmp_path / 'backend/tmp/alias'
    alias.symlink_to(other, target_is_directory=True)
    for path in [other, alias, tmp_path / 'backend/tmp']:
        with pytest.raises(ValueError, match='owned non-aliased'):
            snapshot.safe_directory(path)
    target = tmp_path / 'backend/tmp/foreign'
    target.mkdir()
    (target / 'owner').write_text('another-runtime')
    with pytest.raises(ValueError, match='ownership'):
        snapshot.safe_directory(target, existing=True)


@pytest.mark.parametrize('member_name,link', [('../escape', False), ('/tmp/escape', False), ('config.yaml', True)])
def test_restore_rejects_escaping_or_link_members_before_database_calls(snapshot, tmp_path, monkeypatch, member_name, link):
    target = tmp_path / 'backend/tmp/snapshot'
    target.mkdir()
    (target / 'owner').write_text(snapshot.MARKER)
    with tarfile.open(target / 'runtime.tar', 'w') as archive:
        member = tarfile.TarInfo(member_name)
        if link:
            member.type = tarfile.SYMTYPE
            member.linkname = '../../escape'
        archive.addfile(member)
    databases = {}
    for database in snapshot.DATABASES:
        file = target / (database + '.dump')
        file.write_bytes(b'')
        databases[database] = {'dump_sha256': snapshot.digest(file)}
    manifest = {'schema': snapshot.MARKER, 'complete': True, 'archive_sha256': snapshot.digest(target / 'runtime.tar'), 'runtime_files': {member_name: {'type': 'file', 'mode': 0o600}}, 'databases': databases}
    (target / 'manifest.json').write_text(json.dumps(manifest))
    monkeypatch.setattr(snapshot, 'assert_owned_services', lambda: None)
    monkeypatch.setattr(snapshot, 'execute', lambda *_args, **_kwargs: pytest.fail('Rejected archives must not create/restore a database'))
    with pytest.raises(ValueError, match='escapes'):
        snapshot.verify_snapshot(target)
    assert not (tmp_path / 'backend/tmp/escape').exists()


def test_snapshot_restarts_writers_even_when_capture_and_manifest_both_fail(snapshot, tmp_path, monkeypatch):
    commands = []
    monkeypatch.setattr(snapshot, 'assert_owned_services', lambda: None)
    monkeypatch.setattr(snapshot, 'compose', lambda args: commands.append(args))

    def failed_tree(_root):
        raise OSError('capture unavailable')

    write = snapshot.private_write

    def failed_manifest(path, data):
        if path.name == 'manifest.json':
            raise OSError('snapshot disk full')
        write(path, data)

    monkeypatch.setattr(snapshot, 'tree_manifest', failed_tree)
    monkeypatch.setattr(snapshot, 'private_write', failed_manifest)
    with pytest.raises(OSError, match='disk full'):
        snapshot.create_snapshot(tmp_path / 'backend/tmp/snapshot')
    assert commands[0] == ['stop', 'gateway', 'langgraph', 'ticket-receiver']
    assert commands[-1][:3] == ['up', '-d', '--no-build']
    assert commands[-1][-3:] == ['gateway', 'langgraph', 'ticket-receiver']


@pytest.mark.parametrize('foreign', ['postgresql+asyncpg://prismos@other-project/prismos', 'postgresql+asyncpg://prismos@postgres/other_database'])
def test_model_restore_configuration_cannot_select_foreign_database(snapshot, foreign):
    config = {'database': {'url': foreign, 'auth': {'url': 'postgresql+asyncpg://prismos@postgres/prismos_auth_db'}}, 'checkpointer': {'connection_string': 'postgresql://prismos@postgres/prismos_checkpoints'}}
    with pytest.raises(ValueError, match='foreign database'):
        snapshot.validate_database_scope(config)
