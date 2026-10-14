"""Default host execution through original AIO lease using final built image."""
from test_legacy_default_scope import use_default
from test_skill_scoped_commands import command_runtime, configured, scoped_client, selected_runtime, container_command_runtime, run  # noqa: F401
from test_skill_reference_transactions import durable_sqlite  # noqa: F401


def test_actual_default_uses_final_image_with_only_authorized_resources(container_command_runtime):
    _, runtime = use_default(container_command_runtime)
    result = run(runtime, "from pathlib import Path; print(Path('/mnt/skills/custom/tenant-a/user-a/collision/member.txt').read_text()); print(Path('/etc/prismos-private-config').exists()); Path('/mnt/user-data/outputs/aio-default.txt').write_text('default-image-usable')")
    assert 'AUTHORIZED PERSONAL MEMBER' in result and 'False' in result, result
    from pathlib import Path
    assert (Path(runtime.state['thread_data']['outputs_path'])/'aio-default.txt').read_text() == 'default-image-usable'
