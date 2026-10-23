from pathlib import Path
import hashlib,json
ROOT=Path('/root/.codex/worktrees/octop-integration/prism-os')
HERE=Path(__file__).resolve().parent
p=ROOT/'backend/app/gateway/routers/assets.py'
s=p.read_text()
(HERE/'application-inputs.json').write_text(json.dumps({'base_commit':'f7aac71','assets_before_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'session_before_sha256':hashlib.sha256((ROOT/'backend/app/services/terminal/session.py').read_bytes()).hexdigest()},indent=2)+'\n')
s=s.replace('from typing import Any','from typing import Any, Literal')
s=s.replace('from app.gateway.authorization import require_tenant_context','from app.gateway.authorization import require_tenant_context\nfrom app.gateway.resource_authorization import CurrentResourceRoute\nfrom app.services.terminal.credential_access import asset_session, seal_keychain, verify_asset_bindings, require_owned_binding')
s=s.replace('from deerflow.database.session import get_session\n','')
s=s.replace('router = APIRouter(prefix="/api/v1/assets", tags=["assets"])','router = APIRouter(prefix="/api/v1/assets", tags=["assets"], route_class=CurrentResourceRoute)')
s=s.replace('Depends(get_session)','Depends(asset_session)')
s=s.replace('    type: str = Field(..., description="\'password\' or \'ssh_key\'")','    type: Literal["password", "key", "ssh_key"] = Field(..., description="SSH password or private key")')
s=s.replace('value=req.value  # Should be encrypted in a real app','value=seal_keychain(req.value)')
s=s.replace('kc.value = req.value','kc.value = seal_keychain(req.value)')
s=s.replace('    # Handle inline password','    await verify_asset_bindings(db, req, tenant_id, user_id)\n\n    # Handle inline password',1)
marker='    asset.name = req.name'
assert marker in s
s=s.replace(marker,'    await verify_asset_bindings(db, req, request.state.tenant_id, request.state.user_id)\n\n'+marker,1)
# Persisted inline passwords are sealed and remain in the same asset transaction.
start=s.index('async def create_local_asset(')
end=s.index('@router.post("/test-connection")',start)
prefix,body,suffix=s[:start],s[start:end],s[end:]
body=body.replace('value=req.password','value=seal_keychain(req.password)').replace('db.add(new_kc)\n        await db.commit()','db.add(new_kc)\n        await db.flush()')
s=prefix+body+suffix
s=s.replace('    await db.delete(kc)','    referenced = (await db.execute(sa_select(LocalAsset.id).where(LocalAsset.tenant_id == request.state.tenant_id, LocalAsset.user_id == request.state.user_id, LocalAsset.keychain_id == kc.id))).first()\n    if referenced:\n        raise HTTPException(409, "Credential is referenced by an asset; detach it first")\n    await db.delete(kc)',1)
s=s.replace('    await db.delete(ag)','    referenced = (await db.execute(sa_select(LocalAsset.id).where(LocalAsset.tenant_id == request.state.tenant_id, LocalAsset.user_id == request.state.user_id, LocalAsset.group_id == ag.id))).first()\n    if referenced:\n        raise HTTPException(409, "Group is referenced by an asset; detach it first")\n    await db.delete(ag)',1)
# Draft connections use the same current owner and explicit credential purpose.
s=s.replace('        keychain = res_kc.scalars().first()','        keychain = res_kc.scalars().first()\n        if keychain is None:\n            raise HTTPException(404, "Current credential unavailable")',1)
s=s.replace('tenant_id="mock",\n        user_id="mock",','tenant_id=request.state.tenant_id,\n        user_id=request.state.user_id,')
p.write_text(s)
p=ROOT/'backend/app/services/terminal/session.py'
s=p.read_text().replace('from app.models.assets import Keychain, LocalAsset','from app.models.assets import Keychain, LocalAsset\nfrom app.services.terminal.credential_access import ssh_credential_value')
marker='    if keychain:\n        if keychain.type not in {"ssh_key", "key", "password"}:'
assert marker in s
s=s.replace(marker,'    if keychain:\n        if (keychain.tenant_id, keychain.user_id) != (asset.tenant_id, asset.user_id):\n            raise PermissionError("Selected credential does not belong to the current asset owner")\n        value = ssh_credential_value(keychain)\n        if keychain.type not in {"ssh_key", "key", "password"}:',1)
s=s.replace('keychain.value.encode(\'utf-8\')','value.encode(\'utf-8\')').replace('repr(keychain.value)','repr(value)')
p.write_text(s)
print('Applied credential authority, sealed persistence and original SSH consumer changes')
