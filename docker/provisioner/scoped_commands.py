"""Authenticated, finite Kubernetes command leases with exact shared-directory mounts.

This protocol is separate from legacy AIO Pods: it exposes no sandbox HTTP port,
service account, global skills directory or provisioner environment to commands.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, Depends, Header, HTTPException
from kubernetes import client as kube
from kubernetes.client.rest import ApiException
from pydantic import BaseModel, ConfigDict, Field

MAX_OUTPUT = 1024 * 1024
TARGETS = {"skills": "/mnt/skills", "workspace": "/mnt/user-data/workspace", "uploads": "/mnt/user-data/uploads", "outputs": "/mnt/user-data/outputs"}
DENIED_ENV = {"LD_PRELOAD", "LD_LIBRARY_PATH", "BASH_ENV", "ENV", "PATH", "PYTHONPATH", "PYTHONHOME", "HOME"}


def require_service_token(authorization: str | None = Header(default=None)):
    token = os.environ.get("PRISMOS_PROVISIONER_TOKEN", "")
    if len(token) < 32:
        raise HTTPException(503, "Scoped provisioner credentials are not configured")
    if not authorization or not hmac.compare_digest(authorization, "Bearer " + token):
        raise HTTPException(401, "Provisioner authorization required")


class CommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    lease_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    command: str = Field(min_length=1, max_length=131072)
    mounts: dict[str, str]
    environment: dict[str, str] = Field(default_factory=dict)
    timeout: int = Field(default=600, ge=1, le=600)
    uid: int = Field(ge=0, le=2147483647)
    gid: int = Field(ge=0, le=2147483647)


def contract_digest(req: CommandRequest) -> str:
    return hashlib.sha256(json.dumps(req.model_dump(), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def checked_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or str(path) != value or any(p in {".", ".."} for p in path.parts) or "\\" in value or "\x00" in value:
        raise HTTPException(422, "Scoped directory path is invalid")
    return path


def build_pod(req: CommandRequest, namespace: str):
    if set(req.mounts) != set(TARGETS):
        raise HTTPException(422, "Exactly one resource view and three thread directories are required")
    data_root = Path(os.environ.get("PRISMOS_SCOPED_DATA_ROOT", ""))
    node_root = PurePosixPath(os.environ.get("PRISMOS_SCOPED_NODE_ROOT", ""))
    node = os.environ.get("PRISMOS_SCOPED_NODE", "")
    image = os.environ.get("PRISMOS_SCOPED_IMAGE", "")
    if not data_root.is_absolute() or data_root == Path("/") or data_root.resolve() != data_root or not data_root.is_dir():
        raise HTTPException(503, "Scoped shared data root is not configured")
    if not node_root.is_absolute() or node_root == PurePosixPath("/") or ".." in node_root.parts or not node or not re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", image):
        raise HTTPException(503, "Scoped node, data mapping and immutable image must be configured")
    volumes, mounts = [], []
    paths = []
    for kind, target in TARGETS.items():
        relative = checked_relative(req.mounts[kind])
        path = data_root.joinpath(*relative.parts)
        if path.resolve() != path or not path.is_dir():
            raise HTTPException(409, "Scoped directory is unavailable or aliased")
        paths.append(path)
        volumes.append(kube.V1Volume(name=kind, host_path=kube.V1HostPathVolumeSource(path=str(node_root / relative), type="Directory")))
        mounts.append(kube.V1VolumeMount(name=kind, mount_path=target, read_only=kind == "skills"))
    if any(a == b or a in b.parents or b in a.parents for i, a in enumerate(paths) for b in paths[i + 1 :]):
        raise HTTPException(422, "Scoped directories must be distinct and non-overlapping")
    env = [kube.V1EnvVar(name="HOME", value="/home/agent"), kube.V1EnvVar(name="LANG", value="C.UTF-8")]
    for key, value in req.environment.items():
        if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", key) or key in DENIED_ENV or "\x00" in value or len(value) > 65536:
            raise HTTPException(422, "Scoped command environment is invalid")
        env.append(kube.V1EnvVar(name=key, value=value))
    for name, target in [("scratch", "/tmp"), ("home", "/home/agent")]:
        volumes.append(kube.V1Volume(name=name, empty_dir=kube.V1EmptyDirVolumeSource(size_limit="128Mi")))
        mounts.append(kube.V1VolumeMount(name=name, mount_path=target))
    digest = contract_digest(req)
    return kube.V1Pod(
        metadata=kube.V1ObjectMeta(
            name="prismos-command-" + req.lease_id, namespace=namespace, labels={"prismos.command-lease": req.lease_id}, finalizers=["prismos.io/command-termination"], annotations={"prismos.command-contract": digest}
        ),
        spec=kube.V1PodSpec(
            restart_policy="Never",
            active_deadline_seconds=req.timeout + 30,
            automount_service_account_token=False,
            node_selector={"kubernetes.io/hostname": node},
            enable_service_links=False,
            volumes=volumes,
            containers=[
                kube.V1Container(
                    name="command",
                    image=image,
                    image_pull_policy="IfNotPresent",
                    command=["/bin/bash", "--noprofile", "--norc", "-c", req.command],
                    env=env,
                    working_dir="/mnt/user-data/workspace",
                    volume_mounts=mounts,
                    resources=kube.V1ResourceRequirements(limits={"cpu": "2", "memory": "1Gi", "ephemeral-storage": "512Mi"}, requests={"cpu": "100m", "memory": "128Mi"}),
                    security_context=kube.V1SecurityContext(
                        run_as_user=req.uid,
                        run_as_group=req.gid,
                        privileged=False,
                        allow_privilege_escalation=False,
                        read_only_root_filesystem=True,
                        capabilities=kube.V1Capabilities(drop=["ALL"]),
                        seccomp_profile=kube.V1SeccompProfile(type="RuntimeDefault"),
                    ),
                )
            ],
        ),
    )


def create_router(api, namespace: str) -> APIRouter:
    router = APIRouter(prefix="/api/scoped-commands", dependencies=[Depends(require_service_token)])

    def owned(lease_id: str, digest: str):
        if not re.fullmatch(r"[0-9a-f]{32}", lease_id) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise HTTPException(422, "Command identity is invalid")
        try:
            pod = api().read_namespaced_pod("prismos-command-" + lease_id, namespace, _request_timeout=(3, 10))
        except ApiException as exc:
            raise HTTPException(404 if exc.status == 404 else 503, "Command lease is unavailable") from None
        meta = pod.metadata
        if (meta.labels or {}).get("prismos.command-lease") != lease_id or (meta.annotations or {}).get("prismos.command-contract") != digest or not meta.uid:
            raise HTTPException(409, "Command ownership is unconfirmed")
        receipt, _ = record(lease_id, digest)
        if receipt.data.get("pod_uid") and receipt.data["pod_uid"] != str(meta.uid):
            raise HTTPException(409, "Command instance differs from its publication receipt")
        return pod

    def record(lease_id, digest, *, create_phase=None):
        name = "prismos-command-" + lease_id
        if not re.fullmatch(r"[0-9a-f]{32}", lease_id) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise HTTPException(422, "Command identity is invalid")
        if create_phase:
            try:
                api().create_namespaced_config_map(
                    namespace,
                    kube.V1ConfigMap(
                        metadata=kube.V1ObjectMeta(name=name, labels={"prismos.command-lease": lease_id}), data={"contract": digest, "phase": create_phase, "cancel_requested": "true" if create_phase == "cancelled" else "false"}
                    ),
                    _request_timeout=(3, 10),
                )
                created = True
            except ApiException as exc:
                if exc.status != 409:
                    raise HTTPException(503, "Command lease registration is unconfirmed") from None
                created = False
        else:
            created = False
        try:
            value = api().read_namespaced_config_map(name, namespace, _request_timeout=(3, 10))
        except ApiException as exc:
            raise HTTPException(404 if exc.status == 404 else 503, "Command receipt is unavailable") from None
        if not value.metadata.uid or (value.metadata.labels or {}).get("prismos.command-lease") != lease_id or (value.data or {}).get("contract") != digest:
            raise HTTPException(409, "Command receipt ownership is unconfirmed")
        return value, created

    def update_record(lease_id, digest, **fields):
        # Kubernetes resourceVersion compare-and-swap preserves concurrent cancellation.
        for _ in range(3):
            value, _ = record(lease_id, digest)
            if value.data.get("phase") in {"terminated", "cancelled"} and fields.get("phase") in {"published", "unknown"}:
                fields = {key: val for key, val in fields.items() if key != "phase"}
            value.data.update(fields)
            try:
                return api().replace_namespaced_config_map(value.metadata.name, namespace, value, _request_timeout=(3, 10))
            except ApiException as exc:
                if exc.status != 409:
                    break
        raise HTTPException(503, "Command receipt transition is unconfirmed")

    @router.post("", status_code=201)
    def start(req: CommandRequest):
        pod = build_pod(req, namespace)
        digest = contract_digest(req)
        receipt, created = record(req.lease_id, digest, create_phase="publishing")
        if not created:
            # Never resubmit an unknown dispatch, including after process restart.
            if receipt.data.get("phase") != "published" or receipt.data.get("cancel_requested") == "true":
                raise HTTPException(409, "Command was already submitted or cancelled; inspect its receipt")
            owned(req.lease_id, digest)
            return {"lease_id": req.lease_id, "contract": digest}
        try:
            api().create_namespaced_pod(namespace, pod, _request_timeout=(3, 10))
        except ApiException as exc:
            if exc.status != 409:
                update_record(req.lease_id, digest, phase="unknown")
                raise HTTPException(503, "Command submission is unconfirmed; inspect the existing lease") from None
        # Includes AlreadyExists: never adopt a same-name Pod on name alone.
        current = owned(req.lease_id, digest)
        receipt = update_record(req.lease_id, digest, phase="published", pod_uid=str(current.metadata.uid))
        if receipt.data.get("cancel_requested") == "true":
            raise HTTPException(409, "Command cancellation was requested; inspect its receipt")
        return {"lease_id": req.lease_id, "contract": digest}

    @router.get("/{lease_id}")
    def observe(lease_id: str, x_prismos_contract: str = Header()):
        receipt, _ = record(lease_id, x_prismos_contract)
        if receipt.data.get("cancel_requested") == "true":
            raise HTTPException(409, "Command cancellation was requested")
        pod = owned(lease_id, x_prismos_contract)
        status = pod.status
        states = status.container_statuses or [] if status else []
        terminated = next((s.state.terminated for s in states if s.name == "command" and s.state and s.state.terminated), None)
        result = {"lease_id": lease_id, "contract": x_prismos_contract, "status": "running"}
        if terminated is not None:
            output = api().read_namespaced_pod_log(pod.metadata.name, namespace, container="command", limit_bytes=MAX_OUTPUT + 1, _request_timeout=(3, 10))
            current = owned(lease_id, x_prismos_contract)
            receipt, _ = record(lease_id, x_prismos_contract)
            if receipt.data.get("cancel_requested") == "true":
                raise HTTPException(409, "Command cancellation was requested during delivery")
            if current.metadata.uid != pod.metadata.uid:
                raise HTTPException(409, "Command instance changed during delivery")
            if len(output.encode()) > MAX_OUTPUT:
                raise HTTPException(409, "Command output exceeded the delivery limit; inspect owned outputs")
            result.update(status="completed", output=output, returncode=terminated.exit_code)
        elif status and status.phase in {"Failed", "Succeeded"}:
            raise HTTPException(409, "Command termination result is unconfirmed; inspect owned outputs")
        return result

    @router.delete("/{lease_id}")
    def cancel(lease_id: str, x_prismos_contract: str = Header()):
        receipt, _ = record(lease_id, x_prismos_contract, create_phase="cancelled")
        receipt = update_record(lease_id, x_prismos_contract, cancel_requested="true")
        response = {"lease_id": lease_id, "contract": x_prismos_contract, "terminated": False}
        try:
            pod = owned(lease_id, x_prismos_contract)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            # A missing object is insufficient without a terminal receipt or a
            # tombstone that was atomically registered before any dispatch.
            if receipt.data.get("phase") in {"terminated", "cancelled"}:
                update_record(lease_id, x_prismos_contract, phase="cancelled")
                response["terminated"] = True
            return response
        try:
            # Normal deletion asks the kubelet to stop processes. Never force
            # object removal: an unreachable node could continue executing.
            api().delete_namespaced_pod(pod.metadata.name, namespace, body=kube.V1DeleteOptions(grace_period_seconds=1, preconditions=kube.V1Preconditions(uid=pod.metadata.uid)), _request_timeout=(3, 10))
            pod = owned(lease_id, x_prismos_contract)
            statuses = pod.status.container_statuses or [] if pod.status else []
            if not statuses or any(not item.state or not item.state.terminated for item in statuses):
                return response
            receipt = update_record(lease_id, x_prismos_contract, phase="terminated", pod_uid=str(pod.metadata.uid))
            # Hold the object until kubelet terminal status is durably recorded.
            finalizers = pod.metadata.finalizers or []
            if "prismos.io/command-termination" in finalizers:
                api().patch_namespaced_pod(
                    pod.metadata.name,
                    namespace,
                    [
                        {"op": "test", "path": "/metadata/uid", "value": str(pod.metadata.uid)},
                        {"op": "test", "path": "/metadata/resourceVersion", "value": pod.metadata.resource_version},
                        {"op": "replace", "path": "/metadata/finalizers", "value": [f for f in finalizers if f != "prismos.io/command-termination"]},
                    ],
                    _request_timeout=(3, 10),
                )
            owned(lease_id, x_prismos_contract)
        except HTTPException as exc:
            if exc.status_code == 404 and receipt.data.get("phase") in {"terminated", "cancelled"}:
                update_record(lease_id, x_prismos_contract, phase="cancelled")
                response["terminated"] = True
                return response
            raise
        except ApiException:
            raise HTTPException(503, "Command cancellation is unconfirmed") from None
        return response

    return router
