"""CRUD API for Asset Management (Keychains, Hosts, Groups)."""

import asyncio
import logging
import os
import signal
import subprocess
import time
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select as sa_select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.gateway.authorization import require_tenant_context
from app.gateway.resource_authorization import CurrentResourceRoute
from app.gateway.routers.terminal import build_ssh_command
from app.integrations.file_access import verify_member
from app.models.assets import AssetGroup, Keychain, LocalAsset
from app.services.terminal.credential_access import asset_session, require_owned_binding, seal_keychain, verify_asset_bindings
from deerflow.runtime import ExecutionTrustError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/assets", tags=["assets"], route_class=CurrentResourceRoute)


# ---------------------------------------------------------------------------
# Keychain Models
# ---------------------------------------------------------------------------


class KeychainCreate(BaseModel):
    name: str
    type: Literal["password", "key", "ssh_key"] = Field(..., description="SSH password or private key")
    value: str


class KeychainResponse(BaseModel):
    id: str
    name: str
    type: str


# ---------------------------------------------------------------------------
# Asset Group Models
# ---------------------------------------------------------------------------


class AssetGroupCreate(BaseModel):
    name: str
    description: str = ""


class AssetGroupResponse(BaseModel):
    id: str
    name: str
    description: str


# ---------------------------------------------------------------------------
# Local Asset Models
# ---------------------------------------------------------------------------


class LocalAssetCreate(BaseModel):
    name: str
    ip: str
    port: int = 22
    username: str = "root"
    keychain_id: str | None = None
    group_id: str | None = None
    comment: str = ""
    password: str | None = None


class LocalAssetResponse(BaseModel):
    id: str
    name: str
    ip: str
    port: int
    username: str
    keychain_id: str | None
    group_id: str | None
    is_favorite: bool
    comment: str


# ---------------------------------------------------------------------------
# Keychains
# ---------------------------------------------------------------------------


@router.get("/keychains", response_model=list[KeychainResponse])
async def list_keychains(request: Request, db: AsyncSession = Depends(asset_session), _ctx: Any = Depends(require_tenant_context)):
    tenant_id = request.state.tenant_id
    user_id = request.state.user_id
    query = sa_select(Keychain).where(Keychain.tenant_id == tenant_id, Keychain.user_id == user_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/keychains", response_model=KeychainResponse)
async def create_keychain(req: KeychainCreate, request: Request, db: AsyncSession = Depends(asset_session), _ctx: Any = Depends(require_tenant_context)):
    tenant_id = request.state.tenant_id
    user_id = request.state.user_id

    kc = Keychain(id=str(uuid.uuid4()), tenant_id=tenant_id, user_id=user_id, name=req.name, type=req.type, value=seal_keychain(req.value))
    db.add(kc)
    await db.commit()
    await db.refresh(kc)
    return kc


@router.put("/keychains/{keychain_id}", response_model=KeychainResponse)
async def update_keychain(keychain_id: str, req: KeychainCreate, request: Request, db: AsyncSession = Depends(asset_session), _ctx: Any = Depends(require_tenant_context)):
    query = sa_select(Keychain).where(Keychain.id == keychain_id, Keychain.tenant_id == request.state.tenant_id, Keychain.user_id == request.state.user_id)
    result = await db.execute(query)
    kc = result.scalars().first()
    if not kc:
        raise HTTPException(status_code=404, detail="Keychain not found")

    kc.name = req.name
    kc.type = req.type
    kc.value = seal_keychain(req.value)
    await db.commit()
    await db.refresh(kc)
    return kc


@router.delete("/keychains/{keychain_id}")
async def delete_keychain(keychain_id: str, request: Request, db: AsyncSession = Depends(asset_session), _ctx: Any = Depends(require_tenant_context)):
    query = sa_select(Keychain).where(Keychain.id == keychain_id, Keychain.tenant_id == request.state.tenant_id, Keychain.user_id == request.state.user_id)
    result = await db.execute(query)
    kc = result.scalars().first()
    if not kc:
        raise HTTPException(status_code=404, detail="Keychain not found")

    referenced = (await db.execute(sa_select(LocalAsset.id).where(LocalAsset.tenant_id == request.state.tenant_id, LocalAsset.user_id == request.state.user_id, LocalAsset.keychain_id == kc.id))).first()
    if referenced:
        raise HTTPException(409, "Credential is referenced by an asset; detach it first")
    await db.delete(kc)
    await db.commit()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Asset Groups
# ---------------------------------------------------------------------------


@router.get("/groups", response_model=list[AssetGroupResponse])
async def list_groups(request: Request, db: AsyncSession = Depends(asset_session), _ctx: Any = Depends(require_tenant_context)):
    tenant_id = request.state.tenant_id
    user_id = request.state.user_id
    query = sa_select(AssetGroup).where(AssetGroup.tenant_id == tenant_id, AssetGroup.user_id == user_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/groups", response_model=AssetGroupResponse)
async def create_group(req: AssetGroupCreate, request: Request, db: AsyncSession = Depends(asset_session), _ctx: Any = Depends(require_tenant_context)):
    tenant_id = request.state.tenant_id
    user_id = request.state.user_id

    ag = AssetGroup(id=str(uuid.uuid4()), tenant_id=tenant_id, user_id=user_id, name=req.name, description=req.description)
    db.add(ag)
    await db.commit()
    await db.refresh(ag)
    return ag


@router.put("/groups/{group_id}", response_model=AssetGroupResponse)
async def update_group(group_id: str, req: AssetGroupCreate, request: Request, db: AsyncSession = Depends(asset_session), _ctx: Any = Depends(require_tenant_context)):
    query = sa_select(AssetGroup).where(AssetGroup.id == group_id, AssetGroup.tenant_id == request.state.tenant_id, AssetGroup.user_id == request.state.user_id)
    result = await db.execute(query)
    ag = result.scalars().first()
    if not ag:
        raise HTTPException(status_code=404, detail="Group not found")

    ag.name = req.name
    ag.description = req.description
    await db.commit()
    await db.refresh(ag)
    return ag


@router.delete("/groups/{group_id}")
async def delete_group(group_id: str, request: Request, db: AsyncSession = Depends(asset_session), _ctx: Any = Depends(require_tenant_context)):
    query = sa_select(AssetGroup).where(AssetGroup.id == group_id, AssetGroup.tenant_id == request.state.tenant_id, AssetGroup.user_id == request.state.user_id)
    result = await db.execute(query)
    ag = result.scalars().first()
    if not ag:
        raise HTTPException(status_code=404, detail="Group not found")

    referenced = (await db.execute(sa_select(LocalAsset.id).where(LocalAsset.tenant_id == request.state.tenant_id, LocalAsset.user_id == request.state.user_id, LocalAsset.group_id == ag.id))).first()
    if referenced:
        raise HTTPException(409, "Group is referenced by an asset; detach it first")
    await db.delete(ag)
    await db.commit()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Local Assets
# ---------------------------------------------------------------------------


@router.get("/local", response_model=list[LocalAssetResponse])
async def list_local_assets(request: Request, db: AsyncSession = Depends(asset_session), _ctx: Any = Depends(require_tenant_context)):
    tenant_id = request.state.tenant_id
    user_id = request.state.user_id
    query = sa_select(LocalAsset).where(LocalAsset.tenant_id == tenant_id, LocalAsset.user_id == user_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/local", response_model=LocalAssetResponse)
async def create_local_asset(req: LocalAssetCreate, request: Request, db: AsyncSession = Depends(asset_session), _ctx: Any = Depends(require_tenant_context)):
    tenant_id = request.state.tenant_id
    user_id = request.state.user_id

    await verify_asset_bindings(db, req, tenant_id, user_id)

    # Handle inline password
    final_keychain_id = req.keychain_id
    if req.password and not final_keychain_id:
        new_kc = Keychain(id=str(uuid.uuid4()), tenant_id=tenant_id, user_id=user_id, name=f"{req.name} - 密码", type="password", value=seal_keychain(req.password))
        db.add(new_kc)
        await db.flush()
        final_keychain_id = new_kc.id

    asset = LocalAsset(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        user_id=user_id,
        name=req.name,
        ip=req.ip,
        port=req.port,
        username=req.username,
        keychain_id=final_keychain_id if final_keychain_id else None,
        group_id=req.group_id if req.group_id else None,
        comment=req.comment,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset


@router.put("/local/{asset_id}", response_model=LocalAssetResponse)
async def update_local_asset(asset_id: str, req: LocalAssetCreate, request: Request, db: AsyncSession = Depends(asset_session), _ctx: Any = Depends(require_tenant_context)):
    query = sa_select(LocalAsset).where(LocalAsset.id == asset_id, LocalAsset.tenant_id == request.state.tenant_id, LocalAsset.user_id == request.state.user_id)
    result = await db.execute(query)
    asset = result.scalars().first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    await verify_asset_bindings(db, req, request.state.tenant_id, request.state.user_id)

    asset.name = req.name
    asset.ip = req.ip
    asset.port = req.port
    asset.username = req.username

    if req.password and not req.keychain_id:
        new_kc = Keychain(id=str(uuid.uuid4()), tenant_id=request.state.tenant_id, user_id=request.state.user_id, name=f"{req.name} - 密码", type="password", value=seal_keychain(req.password))
        db.add(new_kc)
        await db.flush()
        asset.keychain_id = new_kc.id
    else:
        asset.keychain_id = req.keychain_id if req.keychain_id else None

    asset.group_id = req.group_id if req.group_id else None
    asset.comment = req.comment

    await db.commit()
    await db.refresh(asset)
    return asset


@router.delete("/local/{asset_id}")
async def delete_local_asset(asset_id: str, request: Request, db: AsyncSession = Depends(asset_session), _ctx: Any = Depends(require_tenant_context)):
    query = sa_select(LocalAsset).where(LocalAsset.id == asset_id, LocalAsset.tenant_id == request.state.tenant_id, LocalAsset.user_id == request.state.user_id)
    result = await db.execute(query)
    asset = result.scalars().first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    await db.delete(asset)
    await db.commit()
    return {"status": "ok"}


@router.post("/test-connection")
async def test_connection(req: LocalAssetCreate, request: Request, db: AsyncSession = Depends(asset_session), _ctx: Any = Depends(require_tenant_context)):
    """Test an owned draft target with live membership and credential authority."""
    tenant, actor = request.state.tenant_id, request.state.user_id
    await verify_asset_bindings(db, req, tenant, actor)
    current = await require_owned_binding(db, Keychain, req.keychain_id, tenant, actor)
    snapshot = current.model_dump() if current is not None else None
    keychain = current.model_copy(deep=True) if current is not None else None
    if keychain is None and req.password:
        keychain = Keychain(id="temp-inline", tenant_id=tenant, user_id=actor, name="Inline", type="password", value=req.password)
    target = LocalAsset(id="draft", tenant_id=tenant, user_id=actor, name=req.name, username=req.username, ip=req.ip, port=req.port, keychain_id=req.keychain_id)
    # Release the initial read transaction; polling uses fresh original DB facts.
    await db.rollback()

    async def validate():
        async with AsyncSession(bind=db.bind, expire_on_commit=False) as fresh:
            await verify_member(fresh, tenant, actor)
            if req.keychain_id:
                try:
                    row = await require_owned_binding(fresh, Keychain, req.keychain_id, tenant, actor)
                except HTTPException:
                    raise ExecutionTrustError("Current connection credential unavailable") from None
                if row.model_dump() != snapshot:
                    raise ExecutionTrustError("Current connection credential changed")

    process = None
    pending = None
    temp_files = []
    try:
        await validate()
        options = {"plaintext_value": req.password} if keychain is not None and keychain.id == "temp-inline" else {}
        cmd, env_updates, temp_files = build_ssh_command(target, keychain, **options)
        cmd.extend(["echo", "SUCCESS"])
        env = {"PATH": os.defpath, "LANG": "C.UTF-8"}
        env.update(env_updates)
        await validate()
        process = await asyncio.create_subprocess_exec(*cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)

        async def drain(stream):
            size = 0
            while chunk := await stream.read(8192):
                size += len(chunk)
                if size > 65536:
                    raise PermissionError("Connection output limit exceeded")

        async def collect():
            readers = [asyncio.create_task(drain(stream)) for stream in (process.stdout, process.stderr)]
            try:
                await asyncio.gather(*readers)
                await process.wait()
            finally:
                for reader in readers:
                    if not reader.done():
                        reader.cancel()
                await asyncio.gather(*readers, return_exceptions=True)

        pending = asyncio.create_task(collect())
        deadline = time.monotonic() + 20
        while not pending.done():
            await asyncio.wait({pending}, timeout=0.25)
            await validate()
            if time.monotonic() >= deadline:
                raise TimeoutError
        pending.result()
        await validate()
        if process.returncode == 0:
            return {"status": "ok", "message": "Connection successful"}
        return {"status": "error", "message": "Connection failed", "return_code": process.returncode}
    except (ExecutionTrustError, PermissionError):
        raise HTTPException(503, {"message": "Connection authority changed or is unavailable; external effects unknown", "inspection_required": True}) from None
    except TimeoutError:
        raise HTTPException(504, {"message": "Connection timed out; external effects unknown", "inspection_required": True}) from None
    finally:
        if process is not None and (process.returncode is None or (pending is not None and not pending.done())):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except TimeoutError:
                raise HTTPException(503, {"message": "Local connection termination is unconfirmed", "inspection_required": True}) from None
        if pending is not None:
            await asyncio.gather(pending, return_exceptions=True)
        for path in temp_files:
            try:
                os.remove(path)
            except OSError:
                pass
