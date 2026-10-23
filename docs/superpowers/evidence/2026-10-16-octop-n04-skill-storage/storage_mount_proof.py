from pathlib import Path
import hashlib,json,subprocess,yaml
from live_common import FIXTURE,HERE,ROOT,STATE
case=json.loads((HERE/'live-skill-read.json').read_text());image=json.loads((HERE/'runtime-image.json').read_text())['image'];proof={'services':{},'source_checkout_unmodified':True}
source=(ROOT/'skills').resolve();custom=(STATE/'skills-custom').resolve()
assert not (ROOT/'skills/custom'/FIXTURE['tenant_id']/case['skill_name']).exists()
file=custom/FIXTURE['tenant_id']/case['skill_name']/'SKILL.md';assert hashlib.sha256(file.read_bytes()).hexdigest()==case['owned_storage_sha256']
for service in ['gateway','langgraph']:
 data=json.loads(subprocess.check_output(['docker','inspect','prismos-n04-wsl-'+service+'-1'],text=True))[0]
 assert data['Config']['Labels']['com.docker.compose.project']=='prismos-n04-wsl' and data['Image']==image
 mounts={m['Destination']:m for m in data['Mounts']}
 assert mounts['/app/skills']['Source']==str(source) and mounts['/app/skills']['RW'] is False
 assert mounts['/app/skills/custom']['Source']==str(custom) and mounts['/app/skills/custom']['RW'] is True
 actual=subprocess.check_output(['docker','exec','prismos-n04-wsl-'+service+'-1','sha256sum','/app/skills/custom/'+FIXTURE['tenant_id']+'/'+case['skill_name']+'/SKILL.md'],text=True).split()[0]
 assert actual==case['owned_storage_sha256']
 proof['services'][service]={'source_readonly':True,'custom_owned_writable':True,'file_sha256':actual,'image':image}
config=yaml.safe_load((STATE/'compose.yaml').read_text());assert config['name']=='prismos-n04-wsl'
for name in ['db-init','gateway','langgraph']:assert str(custom)+':/app/skills/custom' in config['services'][name]['volumes']
assert (custom.stat().st_mode & 0o777)==0o700
remaining=subprocess.check_output(['docker','exec','prismos-n04-wsl-postgres-1','psql','-X','-qAt','-U','prismos','-d','prismos','-c',"SELECT count(*) FROM pg_namespace WHERE nspname IN ('n04_owned_read_fault','n04_owned_write_fault')"],text=True).strip();assert remaining=='0'
proof['temporary_fault_schemas_removed']=True
(HERE/'storage-mounts.json').write_text(json.dumps(proof,indent=2)+'\n')
print('Both real services use owned persistent custom storage, readonly sources, matching current file/image bytes, and no temporary fault schema')
