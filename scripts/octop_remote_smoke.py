#!/usr/bin/env python3
"""Opt-in real cluster probe; no model, external delivery or ticket acceptance."""
import argparse
import hashlib
import json
import os
import shutil
import time
import uuid
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--shared-root", required=True, type=Path)
    parser.add_argument("--token-env", default="PRISMOS_PROVISIONER_TOKEN")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    from deerflow.community.aio_sandbox.remote_command import execute_remote_command

    root = args.shared_root
    if not root.is_absolute() or root == Path("/") or root.resolve() != root or not root.is_dir():
        parser.error("shared-root must be the existing non-aliased shared data directory")
    if args.output.exists():
        parser.error("retain previous evidence: output already exists")
    owned = root / (".prismos-remote-probe-" + uuid.uuid4().hex)
    owned.mkdir(mode=0o700)
    directories = {key: owned / key for key in ("skills", "workspace", "uploads", "outputs")}
    for path in directories.values():
        path.mkdir(mode=0o755)
    canary = "owned-source-" + uuid.uuid4().hex
    source = directories["skills"] / "source.txt"
    source.write_text(canary)
    source.chmod(0o444)
    thread = {key + "_path": str(directories[key]) for key in ("workspace", "uploads", "outputs")}
    record = {"real_cluster_passed": False, "real_model_tool_ticket": False, "owned_probe": str(owned), "cleanup_confirmed": False}
    safe_cleanup = False
    try:
        command = """python - <<'PY'
from pathlib import Path
p=Path('/mnt/skills/source.txt')
data=p.read_text()
try:
    p.write_text('forbidden')
except OSError:
    pass
else:
    raise SystemExit('source was writable')
assert not Path('/var/run/secrets/kubernetes.io/serviceaccount/token').exists()
Path('/mnt/user-data/outputs/result.txt').write_text(data)
print('OWNED REMOTE COMMAND COMPLETED')
PY"""
        result = execute_remote_command(args.url, args.token_env, str(root), command, directories["skills"], thread)
        assert "OWNED REMOTE COMMAND COMPLETED" in result and "Exit Code:" not in result
        assert (directories["outputs"] / "result.txt").read_text() == canary
        assert source.read_text() == canary
        started = time.monotonic()

        observed_start = None

        def validate():
            nonlocal observed_start
            if (directories["workspace"] / "started.txt").exists() and observed_start is None:
                observed_start = time.monotonic()
            if observed_start is not None and time.monotonic() - observed_start > 0.5:
                raise PermissionError("probe authority withdrawn")
            if time.monotonic() - started > 60:
                raise RuntimeError("Remote command did not start in the owned workspace")

        # Prove the command actually started before withdrawing authority.
        command = "printf STARTED > /mnt/user-data/workspace/started.txt; (sleep 3; printf LATE > /mnt/user-data/outputs/late.txt) & wait"
        try:
            execute_remote_command(args.url, args.token_env, str(root), command, directories["skills"], thread, validate=validate)
        except PermissionError as exc:
            assert str(exc) == "probe authority withdrawn", "Cancellation did not confirm the original withdrawal"
        else:
            raise AssertionError("Withdrawal did not interrupt the command")
        time.sleep(3)
        assert not (directories["outputs"] / "late.txt").exists()
        record.update(real_cluster_passed=True, selected_readonly=True, owned_output_sha256=hashlib.sha256(canary.encode()).hexdigest(), withdrawal_child_termination=True)
        safe_cleanup = True
    except Exception as exc:
        record["error_type"] = type(exc).__name__
        record["inspection_required"] = True
        raise
    finally:
        if safe_cleanup:
            if owned.resolve() != owned or owned.parent != root or owned.stat().st_uid != os.getuid():
                raise RuntimeError("Owned probe cleanup identity changed")
            shutil.rmtree(owned)
            record["cleanup_confirmed"] = True
        args.output.write_text(json.dumps(record, indent=2) + "\n")


if __name__ == "__main__":
    main()
