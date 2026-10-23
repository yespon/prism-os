"""Isolated original HTTP reproduction; only synthetic credentials and identities."""
import asyncio,json,sys,tempfile
from pathlib import Path
from types import SimpleNamespace
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'backend/tests'))
import conftest  # Original lightweight test import setup.
from fastapi import FastAPI,Request
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession
from app.gateway.routers import assets
from app.models.assets import Keychain,LocalAsset,AssetGroup
from deerflow.database.models import Tenant,TenantMembership
from deerflow.database.session import get_session

async def main():
    with tempfile.TemporaryDirectory(prefix='prismos-owned-credential-repro-') as temp:
        engine=create_async_engine('sqlite+aiosqlite:///'+str(Path(temp)/'owned.sqlite'))
        tables=[Tenant.__table__,TenantMembership.__table__,Keychain.__table__,AssetGroup.__table__,LocalAsset.__table__]
        async with engine.begin() as connection:
            for table in tables: await connection.run_sync(lambda conn,t=table:t.create(conn,checkfirst=True))
        factory=async_sessionmaker(engine,class_=AsyncSession,expire_on_commit=False)
        async with factory() as db:
            db.add_all([Tenant(id='probe-a',name='Probe A',slug='probe-a'),Tenant(id='probe-b',name='Probe B',slug='probe-b'),TenantMembership(tenant_id='probe-a',user_id='probe-user-a',status='inactive'),Keychain(id='foreign-probe-key',tenant_id='probe-b',user_id='probe-user-b',name='Foreign',type='password',value='synthetic-foreign-only'),AssetGroup(id='foreign-probe-group',tenant_id='probe-b',user_id='probe-user-b',name='Foreign')])
            await db.commit()
        app=FastAPI()
        @app.middleware('http')
        async def identity(request,call_next):
            request.state.tenant_id='probe-a';request.state.user_id='probe-user-a';request.state.tenant_role='member'
            return await call_next(request)
        async def session():
            async with factory() as db: yield db
        app.dependency_overrides[get_session]=session
        app.include_router(assets.router)
        def reproduce():
            with TestClient(app) as client:
                created=client.post('/api/v1/assets/keychains',json={'name':'Owned probe','type':'password','value':'synthetic-owned-only'})
                bound=client.post('/api/v1/assets/local',json={'name':'Owned host','ip':'127.0.0.1','username':'probe','keychain_id':'foreign-probe-key','group_id':'foreign-probe-group'})
                return created,bound
        created,bound=await asyncio.to_thread(reproduce)
        record={'synthetic_identity_scope':'authenticated identity with withdrawn database membership','keychain_status':created.status_code,'asset_status':bound.status_code,'real_ssh_or_external_call':False}
        if created.status_code==200:
            async with factory() as db:
                row=await db.get(Keychain,created.json()['id'])
                record['plaintext_stored']=row.value=='synthetic-owned-only'
        if bound.status_code==200:
            record['foreign_credential_reference_accepted']=bound.json()['keychain_id']=='foreign-probe-key'
            record['foreign_group_reference_accepted']=bound.json()['group_id']=='foreign-probe-group'
        (HERE/'reproduction.json').write_text(json.dumps(record,indent=2)+'\n')
        await engine.dispose()
        print(json.dumps(record))
asyncio.run(main())
