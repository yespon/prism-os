"""Remote lease protocol regression; fake Kubernetes is never real-cluster evidence."""

from copy import deepcopy
from types import SimpleNamespace as NS

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kubernetes.client.rest import ApiException
from test_provisioner_kubeconfig import _load_provisioner_module
from test_skill_member_tools import configured, scoped_client  # noqa: F401
from test_skill_member_tools import selected_runtime as member_runtime
from test_skill_reference_transactions import durable_sqlite  # noqa: F401
from test_skill_scoped_commands import command_runtime as native_command_runtime

from deerflow.community.aio_sandbox.remote_command import execute_remote_command

selected_runtime = member_runtime
command_runtime = native_command_runtime
TOKEN = "protocol-test-only-credential-123456789"
IMAGE = "registry.example/owned-image@sha256:" + "a" * 64


class FakeKubernetes:
    def __init__(self):
        self.pod = None
        self.receipt = None
        self.created = []
        self.deleted = []
        self.keep_deleting = False
        self.output = "PROTOCOL RESULT"
        self.after_log = None

    def create_namespaced_pod(self, namespace, pod, **kwargs):
        if self.pod is not None:
            raise ApiException(status=409)
        self.created.append(pod)
        self.pod = deepcopy(pod)
        self.pod.metadata.uid = "owned-instance"
        self.pod.metadata.resource_version = "1"
        self.pod.status = NS(phase="Running", container_statuses=[])

    def read_namespaced_pod(self, name, namespace, **kwargs):
        if self.pod is None:
            raise ApiException(status=404)
        return deepcopy(self.pod)

    def delete_namespaced_pod(self, name, namespace, body, **kwargs):
        self.deleted.append(body)
        if body.preconditions.uid != self.pod.metadata.uid:
            raise ApiException(status=409)
        if not self.keep_deleting:
            self.complete(137)

    def patch_namespaced_pod(self, name, namespace, body, **kwargs):
        assert body[0] == {"op": "test", "path": "/metadata/uid", "value": self.pod.metadata.uid}
        assert body[1]["value"] == self.pod.metadata.resource_version
        self.pod.metadata.finalizers = body[2]["value"]
        if not self.pod.metadata.finalizers:
            self.pod = None

    def read_namespaced_pod_log(self, *args, **kwargs):
        if self.after_log:
            self.after_log()
        return self.output

    def create_namespaced_config_map(self, namespace, value, **kwargs):
        if self.receipt is not None:
            raise ApiException(status=409)
        self.receipt = deepcopy(value)
        self.receipt.metadata.uid = "receipt-instance"
        self.receipt.metadata.resource_version = "1"

    def read_namespaced_config_map(self, name, namespace, **kwargs):
        if self.receipt is None:
            raise ApiException(status=404)
        return deepcopy(self.receipt)

    def replace_namespaced_config_map(self, name, namespace, value, **kwargs):
        if value.metadata.resource_version != self.receipt.metadata.resource_version:
            raise ApiException(status=409)
        self.receipt = deepcopy(value)
        self.receipt.metadata.resource_version = str(int(value.metadata.resource_version) + 1)
        return deepcopy(self.receipt)

    def complete(self, code=0):
        self.pod.status = NS(phase="Succeeded", container_statuses=[NS(name="command", state=NS(terminated=NS(exit_code=code)))])


@pytest.fixture
def protocol(tmp_path, monkeypatch):
    mod = _load_provisioner_module()
    import scoped_commands as commands

    root = tmp_path / "shared"
    root.mkdir()
    paths = {}
    for kind in commands.TARGETS:
        paths[kind] = root / kind
        paths[kind].mkdir()
    monkeypatch.setenv("PRISMOS_PROVISIONER_TOKEN", TOKEN)
    monkeypatch.setenv("PRISMOS_SCOPED_DATA_ROOT", str(root))
    monkeypatch.setenv("PRISMOS_SCOPED_NODE_ROOT", "/node/owned")
    monkeypatch.setenv("PRISMOS_SCOPED_NODE", "test-node")
    monkeypatch.setenv("PRISMOS_SCOPED_IMAGE", IMAGE)
    api = FakeKubernetes()
    monkeypatch.setattr(mod, "core_v1", api)
    app = FastAPI()
    app.include_router(commands.create_router(lambda: api, "test-namespace"))
    client = TestClient(app)
    body = {"lease_id": "a" * 32, "command": "printf protocol", "mounts": {k: k for k in paths}, "environment": {}, "timeout": 600, "uid": 1000, "gid": 1000}
    digest = commands.contract_digest(commands.CommandRequest(**body))
    headers = {"Authorization": "Bearer " + TOKEN, "X-Prismos-Contract": digest}
    return commands, api, client, body, headers, root, paths, mod


@pytest.mark.parametrize("authorization", [None, "Bearer wrong"])
def test_no_credentials_never_access_kubernetes(protocol, authorization):
    _, api, client, body, _, _, _, _ = protocol
    headers = {"Authorization": authorization} if authorization else {}
    assert client.post("/api/scoped-commands", json=body, headers=headers).status_code == 401
    assert api.created == []


def test_missing_service_config_and_legacy_routes_fail_closed(protocol, monkeypatch):
    _, api, client, body, headers, _, _, mod = protocol
    monkeypatch.delenv("PRISMOS_PROVISIONER_TOKEN")
    assert client.post("/api/scoped-commands", json=body, headers=headers).status_code == 503
    legacy = TestClient(mod.app)
    for method, path in [("post", "/api/sandboxes"), ("get", "/api/sandboxes/other"), ("delete", "/api/sandboxes/other"), ("get", "/api/sandboxes")]:
        assert getattr(legacy, method)(path).status_code == 503
    assert not api.created


def test_manifest_contains_only_exact_scope_and_no_ambient_authority(protocol):
    _, api, client, body, headers, _, _, _ = protocol
    result = client.post("/api/scoped-commands", json=body, headers=headers)
    assert result.status_code == 201, result.text
    pod = api.created[0]
    spec = pod.spec
    container = spec.containers[0]
    assert spec.automount_service_account_token is False and spec.enable_service_links is False
    assert spec.restart_policy == "Never" and spec.active_deadline_seconds == 630
    assert spec.node_selector == {"kubernetes.io/hostname": "test-node"}
    assert container.image == IMAGE
    assert len(spec.volumes) == 6
    assert {v.host_path.path for v in spec.volumes if v.host_path} == {"/node/owned/" + k for k in body["mounts"]}
    assert all(v.host_path.type == "Directory" for v in spec.volumes if v.host_path)
    assert [(v.mount_path, v.read_only) for v in container.volume_mounts[:4]] == [("/mnt/skills", True), ("/mnt/user-data/workspace", False), ("/mnt/user-data/uploads", False), ("/mnt/user-data/outputs", False)]
    security = container.security_context
    assert not security.privileged and not security.allow_privilege_escalation and security.read_only_root_filesystem
    assert security.capabilities.drop == ["ALL"]
    assert {v.name for v in container.env} == {"HOME", "LANG"}
    assert TOKEN not in pod.to_str()


@pytest.mark.parametrize("target", ["../outside", "/absolute", "skills/../workspace", "skills//child", ".", "skills\\child"])
def test_forged_relative_paths_never_create_pod(protocol, target):
    _, api, client, body, headers, _, _, _ = protocol
    body["mounts"]["skills"] = target
    assert client.post("/api/scoped-commands", json=body, headers=headers).status_code in {409, 422}
    assert not api.created


@pytest.mark.parametrize("change", ["symlink", "overlap", "missing", "mutable-image", "unsafe-env"])
def test_invalid_mount_or_runtime_configuration_does_not_publish(protocol, change, monkeypatch):
    _, api, client, body, headers, root, paths, _ = protocol
    if change == "symlink":
        (root / "alias").symlink_to(paths["skills"], target_is_directory=True)
        body["mounts"]["skills"] = "alias"
    elif change == "overlap":
        body["mounts"]["skills"] = "workspace"
    elif change == "missing":
        body["mounts"].pop("skills")
    elif change == "mutable-image":
        monkeypatch.setenv("PRISMOS_SCOPED_IMAGE", "registry.example/image:latest")
    else:
        body["environment"] = {"BASH_ENV": "/mnt/user-data/uploads/start"}
    assert client.post("/api/scoped-commands", json=body, headers=headers).status_code in {409, 422, 503}
    assert not api.created


def test_ownership_is_checked_for_adoption_observation_and_deletion(protocol):
    _, api, client, body, headers, _, _, _ = protocol
    endpoint = "/api/scoped-commands/" + body["lease_id"]
    assert client.post("/api/scoped-commands", json=body, headers=headers).status_code == 201
    api.pod.metadata.annotations["prismos.command-contract"] = "b" * 64
    assert client.post("/api/scoped-commands", json=body, headers=headers).status_code == 409
    assert client.get(endpoint, headers=headers).status_code == 409
    assert client.delete(endpoint, headers=headers).status_code == 409
    assert not api.deleted


def test_result_and_actual_deletion_confirmation(protocol):
    _, api, client, body, headers, _, _, _ = protocol
    endpoint = "/api/scoped-commands/" + body["lease_id"]
    assert client.post("/api/scoped-commands", json=body, headers=headers).status_code == 201
    api.complete(7)
    result = client.get(endpoint, headers=headers).json()
    assert result["output"] == api.output and result["returncode"] == 7

    assert client.delete(endpoint, headers=headers).json()["terminated"] is True
    assert client.delete(endpoint, headers=headers).json()["terminated"] is True


def test_replaced_pod_cannot_deliver_foreign_logs(protocol):
    _, api, client, body, headers, _, _, _ = protocol
    assert client.post("/api/scoped-commands", json=body, headers=headers).status_code == 201
    api.complete()
    api.after_log = lambda: setattr(api.pod.metadata, "uid", "replacement-instance")
    response = client.get("/api/scoped-commands/" + body["lease_id"], headers=headers)
    assert response.status_code == 409 and api.output not in response.text


class ClientSession:
    def __init__(self, client, api, *, lost_post=False, complete=True):
        self.client, self.api = client, api
        self.lost_post, self.complete = lost_post, complete
        self.calls = []

    def request(self, method, url, **kwargs):
        from urllib.parse import urlsplit

        kwargs.pop("timeout")
        assert kwargs.pop("allow_redirects") is False
        self.calls.append(method)
        response = self.client.request(method, urlsplit(url).path, **kwargs)
        if method == "POST" and response.status_code == 201:
            if self.complete:
                self.api.complete()
            if self.lost_post:
                import requests

                raise requests.ConnectionError("private-network-detail")
        return response

    def close(self):
        pass


@pytest.mark.parametrize("scenario", ["complete", "revoked", "lost-post"])
def test_client_protocol_preserves_original_guard_and_never_replays(protocol, monkeypatch, scenario):
    _, api, client, _, _, root, paths, _ = protocol
    session = ClientSession(client, api, lost_post=scenario == "lost-post", complete=scenario != "revoked")
    monkeypatch.setattr("deerflow.community.aio_sandbox.remote_command.requests.Session", lambda: session)
    state = {"validations": 0}

    def validate():
        state["validations"] += 1
        if scenario == "revoked" and api.created:
            raise PermissionError("Current member withdrawn")

    args = ("http://127.0.0.1", "PRISMOS_PROVISIONER_TOKEN", str(root), "printf protocol", paths["skills"], {k + "_path": str(paths[k]) for k in ("workspace", "uploads", "outputs")})
    if scenario == "complete":
        assert execute_remote_command(*args, validate=validate) == "PROTOCOL RESULT"
        assert state["validations"] >= 3
    else:
        with pytest.raises(PermissionError) as error:
            execute_remote_command(*args, validate=validate)
        assert "private-network-detail" not in str(error.value)
    assert session.calls.count("POST") == 1
    assert session.calls[-1] == "DELETE" and api.pod is None


@pytest.mark.parametrize("url", ["http://remote.example", "https://user:secret@example.com", "https://example.com?token=secret"])
def test_client_refuses_unsafe_transport_before_any_request(protocol, url):
    _, api, _, _, _, root, paths, _ = protocol
    with pytest.raises(PermissionError):
        execute_remote_command(url, "PRISMOS_PROVISIONER_TOKEN", str(root), "true", paths["skills"], {})
    assert not api.created


def test_cancel_before_dispatch_persists_tombstone_and_prevents_late_start(protocol):
    _, api, client, body, headers, _, _, _ = protocol
    endpoint = "/api/scoped-commands/" + body["lease_id"]
    assert client.delete(endpoint, headers=headers).json()["terminated"] is True
    assert client.post("/api/scoped-commands", json=body, headers=headers).status_code == 409
    assert not api.created and api.receipt.data["phase"] == "cancelled"


def test_inflight_submission_absence_is_not_a_termination_fact(protocol):
    commands, api, client, body, headers, _, _, _ = protocol
    from kubernetes import client as kube

    api.create_namespaced_config_map(
        "test-namespace",
        kube.V1ConfigMap(
            metadata=kube.V1ObjectMeta(name="prismos-command-" + body["lease_id"], labels={"prismos.command-lease": body["lease_id"]}),
            data={"contract": commands.contract_digest(commands.CommandRequest(**body)), "phase": "publishing", "cancel_requested": "false"},
        ),
    )
    endpoint = "/api/scoped-commands/" + body["lease_id"]
    assert client.delete(endpoint, headers=headers).json()["terminated"] is False
    assert client.post("/api/scoped-commands", json=body, headers=headers).status_code == 409
    assert not api.created and api.receipt.data["cancel_requested"] == "true"


def test_real_loopback_http_client_completes_owned_lease(protocol):
    import socket
    import threading
    import time

    import uvicorn

    _, api, client, _, _, root, paths, _ = protocol
    original_create = api.create_namespaced_pod

    def complete_after_create(*args, **kwargs):
        original_create(*args, **kwargs)
        api.complete()

    api.create_namespaced_pod = complete_after_create
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(client.app, log_level="error", lifespan="off"))
    worker = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    worker.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        result = execute_remote_command(f"http://127.0.0.1:{port}", "PRISMOS_PROVISIONER_TOKEN", str(root), "printf protocol", paths["skills"], {k + "_path": str(paths[k]) for k in ("workspace", "uploads", "outputs")})
        assert result == "PROTOCOL RESULT" and api.pod is None
        assert api.receipt.data["phase"] == "cancelled"
    finally:
        server.should_exit = True
        worker.join(5)
        listener.close()
    assert not worker.is_alive()


@pytest.mark.parametrize("withdraw", [False, True])
def test_original_tool_and_database_authority_survive_remote_provider(protocol, command_runtime, monkeypatch, withdraw):
    import asyncio

    from sqlalchemy import select

    from deerflow.community.aio_sandbox.aio_sandbox_provider import AioSandboxProvider
    from deerflow.community.aio_sandbox.remote_backend import RemoteSandboxBackend
    from deerflow.config.paths import get_paths
    from deerflow.database.models import TenantMembership
    from deerflow.sandbox import tools

    factory, _, _, _, runtime, _ = command_runtime
    _, api, client, _, _, _, _, _ = protocol
    root = get_paths().base_dir
    monkeypatch.setenv("PRISMOS_SCOPED_DATA_ROOT", str(root))
    provider = AioSandboxProvider.__new__(AioSandboxProvider)
    provider._backend = RemoteSandboxBackend("http://127.0.0.1")
    provider._config = {"provisioner_token_env": "PRISMOS_PROVISIONER_TOKEN", "provisioner_shared_root": str(root)}
    monkeypatch.setattr(tools, "get_sandbox_provider", lambda: provider)
    session = ClientSession(client, api)
    original_request = session.request

    async def remove_member():
        async with factory() as db:
            row = (await db.exec(select(TenantMembership).where(TenantMembership.tenant_id == "tenant-a", TenantMembership.user_id == "user-a"))).scalars().one()
            row.status = "inactive"
            await db.commit()

    def request(method, url, **kwargs):
        response = original_request(method, url, **kwargs)
        if method == "POST" and response.status_code == 201 and withdraw:
            asyncio.run(remove_member())
        return response

    session.request = request
    monkeypatch.setattr("deerflow.community.aio_sandbox.remote_command.requests.Session", lambda: session)
    result = tools.bash_tool.func(runtime, "Exercise current remote authority", "printf protocol")
    if withdraw:
        assert "Error:" in result and "PROTOCOL RESULT" not in result
    else:
        assert result == "PROTOCOL RESULT", result
    assert len(api.created) == 1 and api.pod is None
    assert api.receipt.data["phase"] == "cancelled"


def test_legacy_remote_never_ignores_requested_mounts(monkeypatch):
    from deerflow.community.aio_sandbox.remote_backend import RemoteSandboxBackend

    backend = RemoteSandboxBackend("https://provisioner.example")
    monkeypatch.setattr(backend, "_provisioner_create", lambda *args: pytest.fail("Unscoped remote request must not be sent"))
    with pytest.raises(PermissionError, match="scoped mounts"):
        backend.create("thread", "sandbox", [("/owned", "/mnt/skills", True)])


def test_log_delivery_honors_cancellation_during_read(protocol):
    _, api, client, body, headers, _, _, _ = protocol
    assert client.post("/api/scoped-commands", json=body, headers=headers).status_code == 201
    api.complete()
    api.after_log = lambda: api.receipt.data.update(cancel_requested="true")
    result = client.get("/api/scoped-commands/" + body["lease_id"], headers=headers)
    assert result.status_code == 409 and api.output not in result.text


def test_conflicting_receipt_never_deletes_another_operation(protocol):
    _, api, client, body, headers, _, _, _ = protocol
    assert client.post("/api/scoped-commands", json=body, headers=headers).status_code == 201
    api.receipt.data["contract"] = "f" * 64
    response = client.delete("/api/scoped-commands/" + body["lease_id"], headers=headers)
    assert response.status_code == 409 and not api.deleted


def test_receipt_publication_prevents_restart_from_reexecuting(protocol):
    _, api, client, body, headers, _, _, _ = protocol
    assert client.post("/api/scoped-commands", json=body, headers=headers).status_code == 201
    api.pod = None  # Reclaimed or lost after completion; immutable operation still exists.
    assert client.post("/api/scoped-commands", json=body, headers=headers).status_code == 404
    assert len(api.created) == 1


def test_running_pod_keeps_finalizer_until_kubelet_terminal_fact(protocol):
    _, api, client, body, headers, _, _, _ = protocol
    endpoint = "/api/scoped-commands/" + body["lease_id"]
    assert client.post("/api/scoped-commands", json=body, headers=headers).status_code == 201
    api.keep_deleting = True
    assert client.delete(endpoint, headers=headers).json()["terminated"] is False
    assert api.deleted[-1].grace_period_seconds == 1
    assert api.deleted[-1].preconditions.uid == "owned-instance"
    assert "prismos.io/command-termination" in api.pod.metadata.finalizers
    api.complete(137)
    assert client.delete(endpoint, headers=headers).json()["terminated"] is True
    assert api.pod is None and api.receipt.data["phase"] == "cancelled"


def test_missing_object_without_terminal_fact_never_confirms_stop(protocol):
    _, api, client, body, headers, _, _, _ = protocol
    endpoint = "/api/scoped-commands/" + body["lease_id"]
    assert client.post("/api/scoped-commands", json=body, headers=headers).status_code == 201
    api.pod = None  # Simulate external force removal while the node is unreachable.
    assert client.delete(endpoint, headers=headers).json()["terminated"] is False
    assert api.receipt.data["phase"] == "published"


def test_replacement_with_matching_labels_still_cannot_be_cancelled(protocol):
    _, api, client, body, headers, _, _, _ = protocol
    endpoint = "/api/scoped-commands/" + body["lease_id"]
    assert client.post("/api/scoped-commands", json=body, headers=headers).status_code == 201
    api.pod.metadata.uid = "foreign-replacement"
    assert client.delete(endpoint, headers=headers).status_code == 409
    assert not api.deleted
