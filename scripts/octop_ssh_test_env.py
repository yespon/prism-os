"""Start a loopback-only OpenSSH target and register its encrypted native asset."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

import httpx

from octop_wsl_native_env import NATIVE, ROOT


def prepare(output):
    assert not output.exists()
    state = NATIVE / "ssh-service"
    fixture = json.loads((state / "fixture.json").read_text())
    name = fixture["container"]
    assert (
        subprocess.run(["docker", "inspect", name], capture_output=True).returncode != 0
    ), "Do not replace an existing target"
    image = subprocess.check_output(
        [
            "docker",
            "image",
            "inspect",
            "prismos-ssh-target:test",
            "--format",
            "{{.Id}}",
        ],
        text=True,
    ).strip()
    command = [
        "docker",
        "run",
        "-d",
        "--name",
        name,
        "--label",
        "prismos.test.kind=ssh-target",
        "--label",
        "prismos.test.nonce=" + fixture["nonce"],
        "--security-opt",
        "no-new-privileges:true",
        "--read-only",
        "--tmpfs",
        "/run:rw,noexec,nosuid,nodev,size=16m",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=64m",
        "--pids-limit",
        "64",
        "--memory",
        "192m",
        "--cpus",
        "0.5",
        "-p",
        "127.0.0.1:18042:2222",
        "--mount",
        "type=bind,source="
        + str(state / "id_ed25519.pub")
        + ",target=/run/fixture-public-key.pub,readonly",
        image,
    ]
    container = subprocess.check_output(command, text=True).strip()
    fixture.update(container_id=container, image=image)
    (state / "fixture.json").write_text(json.dumps(fixture))
    info = json.loads(subprocess.check_output(["docker", "inspect", name]))[0]
    assert (
        info["Id"] == container
        and info["Config"]["Labels"]["prismos.test.nonce"] == fixture["nonce"]
    )
    assert not info["HostConfig"]["Privileged"] and info["HostConfig"]["ReadonlyRootfs"]
    assert (
        info["HostConfig"]["SecurityOpt"] == ["no-new-privileges:true"]
        and not info["HostConfig"]["CapAdd"]
    )
    assert info["HostConfig"]["PortBindings"]["2222/tcp"] == [
        {"HostIp": "127.0.0.1", "HostPort": "18042"}
    ]
    assert (
        len(info["Mounts"]) == 1
        and not info["Mounts"][0]["RW"]
        and info["Mounts"][0]["Destination"] == "/run/fixture-public-key.pub"
    )
    ssh = [
        "ssh",
        "-F",
        "/dev/null",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=2",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "IdentityAgent=none",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "UserKnownHostsFile=" + str(state / "known_hosts"),
        "-i",
        str(state / "id_ed25519"),
        "-p",
        "18042",
        "target@127.0.0.1",
        "cat /home/target/fixture.txt; uname -s",
    ]
    for _ in range(40):
        result = subprocess.run(ssh, capture_output=True, text=True)
        if result.returncode == 0:
            break
        time.sleep(0.25)
    else:
        raise RuntimeError("Owned SSH target not ready; inspect owned container logs")
    assert fixture["marker"] in result.stdout and "Linux" in result.stdout
    (state / "direct-ssh.txt").write_text(result.stdout)
    (state / "direct-ssh.txt").chmod(0o600)
    (state / "known_hosts").chmod(0o600)
    users = json.loads((NATIVE / "live-fixture.json").read_text())
    account = users["users"]["requester"]
    with httpx.Client(
        base_url="http://127.0.0.1:18036",
        headers={"X-Tenant-Id": users["tenant_id"]},
        trust_env=False,
        timeout=30,
    ) as c:
        login = c.post(
            "/api/auth/login",
            json={"email": account["email"], "password": account["password"]},
        )
        assert login.status_code == 200
        c.headers["Authorization"] = "Bearer " + login.json()["session"]["token"]
        key = c.post(
            "/api/v1/assets/keychains",
            json={
                "name": "Owned SSH test key",
                "type": "ssh_key",
                "value": (state / "id_ed25519").read_text(),
            },
        )
        assert key.status_code == 200, ("key registration", key.status_code)
        assert "value" not in key.json()
        asset = c.post(
            "/api/v1/assets/local",
            json={
                "name": "Owned SSH target " + fixture["nonce"][:8],
                "ip": "127.0.0.1",
                "port": 18042,
                "username": "target",
                "keychain_id": key.json()["id"],
                "comment": "Owned isolated read-only acceptance target",
            },
        )
        assert asset.status_code == 200, ("asset registration", asset.status_code)
        fixture.update(asset=asset.json(), keychain_id=key.json()["id"])
    (state / "fixture.json").write_text(json.dumps(fixture))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "complete": True,
                "container": name,
                "container_id": container,
                "image": image,
                "asset_id": fixture["asset"]["id"],
                "keychain_id": fixture["keychain_id"],
                "expected_marker": fixture["marker"],
                "direct_ssh_marker_and_kernel_verified": True,
                "loopback_only": True,
                "rootfs_read_only": True,
                "default_caps_no_extra_privileges_or_socket": True,
                "private_key_exported": False,
                "model_tasks_submitted": 0,
                "source_sha256": {
                    str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (ROOT / "docker/ssh-test").iterdir()
                    if p.is_file()
                },
            },
            indent=2,
        )
        + "\n"
    )
    print(
        "Real isolated OpenSSH target ready; encrypted asset registered; private key retained privately"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    prepare(parser.parse_args().output)
