"""Smoke actual provisioner-image HTTP admission without a cluster or fake API."""
import json,subprocess,sys
image=sys.argv[1]
code='''
import json,os,socket,threading,time,urllib.request,urllib.error
import uvicorn
from app import app
os.environ['PRISMOS_PROVISIONER_TOKEN']='service-image-smoke-only-credential-123456789'
assert '/api/scoped-commands/{lease_id}' in app.openapi()['paths']
listener=socket.socket(); listener.bind(('127.0.0.1',0)); port=listener.getsockname()[1]
server=uvicorn.Server(uvicorn.Config(app,log_level='error',lifespan='off'))
worker=threading.Thread(target=server.run,kwargs={'sockets':[listener]},daemon=True); worker.start()
try:
    deadline=time.monotonic()+5
    while not server.started and time.monotonic()<deadline: time.sleep(.01)
    assert server.started
    statuses={}
    for path,expected in [('/health',200),('/api/sandboxes',503),('/api/scoped-commands/'+'a'*32,401)]:
        try:
            with urllib.request.urlopen('http://127.0.0.1:'+str(port)+path,timeout=3) as response: status=response.status
        except urllib.error.HTTPError as exc: status=exc.code
        assert status==expected,(path,status)
        statuses[path]=status
    print(json.dumps({'actual_image_http':statuses,'real_cluster_exercised':False}))
finally:
    server.should_exit=True; worker.join(5); listener.close()
assert not worker.is_alive()
'''
subprocess.run(['docker','run','--rm','--network','none',image,'python','-c',code],check=True)
