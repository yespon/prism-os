"""CRUD API for Asset Management (Keychains, Hosts, Groups)."""

import asyncio
import logging
import os
import subprocess
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select as sa_select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.gateway.authorization import require_tenant_context
from app.gateway.routers.terminal import build_ssh_command
from app.models.assets import AssetGroup, Keychain, LocalAsset
from deerflow.database.session import get_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/assets", tags=["assets"])


# ---------------------------------------------------------------------------
# Keychain Models
# ---------------------------------------------------------------------------

class KeychainCreate(BaseModel):
    name: str
    type: str = Field(..., description="'password' or 'ssh_key'")
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
async def list_keychains(
    request: Request,
    db: AsyncSession = Depends(get_session),
    _ctx: Any = Depends(require_tenant_context)
):
    tenant_id = request.state.tenant_id
    user_id = request.state.user_id
    query = sa_select(Keychain).where(
        Keychain.tenant_id == tenant_id,
        Keychain.user_id == user_id
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/keychains", response_model=KeychainResponse)
async def create_keychain(
    req: KeychainCreate,
    request: Request,
    db: AsyncSession = Depends(get_session),
    _ctx: Any = Depends(require_tenant_context)
):
    tenant_id = request.state.tenant_id
    user_id = request.state.user_id
    
    kc = Keychain(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        user_id=user_id,
        name=req.name,
        type=req.type,
        value=req.value  # Should be encrypted in a real app
    )
    db.add(kc)
    await db.commit()
    await db.refresh(kc)
    return kc


@router.put("/keychains/{keychain_id}", response_model=KeychainResponse)
async def update_keychain(
    keychain_id: str,
    req: KeychainCreate,
    request: Request,
    db: AsyncSession = Depends(get_session),
    _ctx: Any = Depends(require_tenant_context)
):
    query = sa_select(Keychain).where(
        Keychain.id == keychain_id,
        Keychain.tenant_id == request.state.tenant_id,
        Keychain.user_id == request.state.user_id
    )
    result = await db.execute(query)
    kc = result.scalars().first()
    if not kc:
        raise HTTPException(status_code=404, detail="Keychain not found")
    
    kc.name = req.name
    kc.type = req.type
    kc.value = req.value
    await db.commit()
    await db.refresh(kc)
    return kc


@router.delete("/keychains/{keychain_id}")
async def delete_keychain(
    keychain_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
    _ctx: Any = Depends(require_tenant_context)
):
    query = sa_select(Keychain).where(
        Keychain.id == keychain_id,
        Keychain.tenant_id == request.state.tenant_id,
        Keychain.user_id == request.state.user_id
    )
    result = await db.execute(query)
    kc = result.scalars().first()
    if not kc:
        raise HTTPException(status_code=404, detail="Keychain not found")
    
    await db.delete(kc)
    await db.commit()
    return {"status": "ok"}

# ---------------------------------------------------------------------------
# Asset Groups
# ---------------------------------------------------------------------------

@router.get("/groups", response_model=list[AssetGroupResponse])
async def list_groups(
    request: Request,
    db: AsyncSession = Depends(get_session),
    _ctx: Any = Depends(require_tenant_context)
):
    tenant_id = request.state.tenant_id
    user_id = request.state.user_id
    query = sa_select(AssetGroup).where(
        AssetGroup.tenant_id == tenant_id,
        AssetGroup.user_id == user_id
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/groups", response_model=AssetGroupResponse)
async def create_group(
    req: AssetGroupCreate,
    request: Request,
    db: AsyncSession = Depends(get_session),
    _ctx: Any = Depends(require_tenant_context)
):
    tenant_id = request.state.tenant_id
    user_id = request.state.user_id
    
    ag = AssetGroup(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        user_id=user_id,
        name=req.name,
        description=req.description
    )
    db.add(ag)
    await db.commit()
    await db.refresh(ag)
    return ag


@router.put("/groups/{group_id}", response_model=AssetGroupResponse)
async def update_group(
    group_id: str,
    req: AssetGroupCreate,
    request: Request,
    db: AsyncSession = Depends(get_session),
    _ctx: Any = Depends(require_tenant_context)
):
    query = sa_select(AssetGroup).where(
        AssetGroup.id == group_id,
        AssetGroup.tenant_id == request.state.tenant_id,
        AssetGroup.user_id == request.state.user_id
    )
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
async def delete_group(
    group_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
    _ctx: Any = Depends(require_tenant_context)
):
    query = sa_select(AssetGroup).where(
        AssetGroup.id == group_id,
        AssetGroup.tenant_id == request.state.tenant_id,
        AssetGroup.user_id == request.state.user_id
    )
    result = await db.execute(query)
    ag = result.scalars().first()
    if not ag:
        raise HTTPException(status_code=404, detail="Group not found")
    
    await db.delete(ag)
    await db.commit()
    return {"status": "ok"}

# ---------------------------------------------------------------------------
# Local Assets
# ---------------------------------------------------------------------------

@router.get("/local", response_model=list[LocalAssetResponse])
async def list_local_assets(
    request: Request,
    db: AsyncSession = Depends(get_session),
    _ctx: Any = Depends(require_tenant_context)
):
    tenant_id = request.state.tenant_id
    user_id = request.state.user_id
    query = sa_select(LocalAsset).where(
        LocalAsset.tenant_id == tenant_id,
        LocalAsset.user_id == user_id
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/local", response_model=LocalAssetResponse)
async def create_local_asset(
    req: LocalAssetCreate,
    request: Request,
    db: AsyncSession = Depends(get_session),
    _ctx: Any = Depends(require_tenant_context)
):
    tenant_id = request.state.tenant_id
    user_id = request.state.user_id
    
    # Handle inline password
    final_keychain_id = req.keychain_id
    if req.password and not final_keychain_id:
        new_kc = Keychain(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            user_id=user_id,
            name=f"{req.name} - 密码",
            type="password",
            value=req.password
        )
        db.add(new_kc)
        await db.commit()
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
        comment=req.comment
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset


@router.put("/local/{asset_id}", response_model=LocalAssetResponse)
async def update_local_asset(
    asset_id: str,
    req: LocalAssetCreate,
    request: Request,
    db: AsyncSession = Depends(get_session),
    _ctx: Any = Depends(require_tenant_context)
):
    query = sa_select(LocalAsset).where(
        LocalAsset.id == asset_id,
        LocalAsset.tenant_id == request.state.tenant_id,
        LocalAsset.user_id == request.state.user_id
    )
    result = await db.execute(query)
    asset = result.scalars().first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    asset.name = req.name
    asset.ip = req.ip
    asset.port = req.port
    asset.username = req.username
    
    if req.password and not req.keychain_id:
        new_kc = Keychain(
            id=str(uuid.uuid4()),
            tenant_id=request.state.tenant_id,
            user_id=request.state.user_id,
            name=f"{req.name} - 密码",
            type="password",
            value=req.password
        )
        db.add(new_kc)
        await db.commit()
        asset.keychain_id = new_kc.id
    else:
        asset.keychain_id = req.keychain_id if req.keychain_id else None
        
    asset.group_id = req.group_id if req.group_id else None
    asset.comment = req.comment
    
    await db.commit()
    await db.refresh(asset)
    return asset


@router.delete("/local/{asset_id}")
async def delete_local_asset(
    asset_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
    _ctx: Any = Depends(require_tenant_context)
):
    query = sa_select(LocalAsset).where(
        LocalAsset.id == asset_id,
        LocalAsset.tenant_id == request.state.tenant_id,
        LocalAsset.user_id == request.state.user_id
    )
    result = await db.execute(query)
    asset = result.scalars().first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    await db.delete(asset)
    await db.commit()
    return {"status": "ok"}


@router.post("/test-connection")
async def test_connection(
    req: LocalAssetCreate,
    request: Request,
    db: AsyncSession = Depends(get_session),
    _ctx: Any = Depends(require_tenant_context)
):
    """Test SSH connection before saving."""
    keychain = None
    if req.keychain_id:
        query_kc = sa_select(Keychain).where(
            Keychain.id == req.keychain_id,
            Keychain.tenant_id == request.state.tenant_id,
            Keychain.user_id == request.state.user_id
        )
        res_kc = await db.execute(query_kc)
        keychain = res_kc.scalars().first()
    elif req.password:
        keychain = Keychain(
            id="temp-inline",
            tenant_id=request.state.tenant_id,
            user_id=request.state.user_id,
            name="Temp Inline Password",
            type="password",
            value=req.password
        )
    
    # Mock an asset object for the command builder
    mock_asset = LocalAsset(
        id="mock",
        tenant_id="mock",
        user_id="mock",
        name="mock",
        username=req.username,
        ip=req.ip,
        port=req.port,
        keychain_id=req.keychain_id if req.keychain_id else None
    )
    
    cmd, env_updates, temp_files = build_ssh_command(mock_asset, keychain)
    # Add a simple exit command so it doesn't hang
    cmd.extend(["echo", "SUCCESS"])
    
    env = os.environ.copy()
    env.update(env_updates)
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=20)
        
        if process.returncode == 0:
            return {"status": "ok", "message": "Connection successful"}
        else:
            return {"status": "error", "message": stderr.decode('utf-8') or stdout.decode('utf-8') or "Connection failed"}
    except TimeoutError:
        return {"status": "error", "message": "Connection timed out"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        for f in temp_files:
            try:
                os.remove(f)
            except OSError:
                pass

