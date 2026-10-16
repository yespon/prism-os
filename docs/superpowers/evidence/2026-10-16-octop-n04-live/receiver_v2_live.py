import json
from live_common import HERE,expect,login,mode,policy,stats
receipt={'complete':False,'M1_exited':False,'facts':[]}
client=None
try:
 policy('deny');client=login('requester')
 before=stats();assert before['counter_version']==2
 for filename,wanted in [('allow-policy-synchronized.json','submitted'),('provider-failure-current.json','unknown'),('timeout-policy-synchronized.json','unknown')]:
  old=json.loads((HERE/filename).read_text());incident=old['incident_id']
  current=expect(client,'/api/incidents/'+incident+'/governed-ticket/resume',{})
  assert current['status']==wanted
  receipt['facts'].append({'incident_id':incident,'status':current['status'],'kind':'real authenticated settled fact read under current deny policy'})
 after=stats();assert after['request_count']==before['request_count']
 receipt.update({'counter_version':2,'requests_before':before['request_count'],'requests_after':after['request_count'],'historical_v1_receipts':after['historical_v1_receipts'],'complete':True})
finally:
 if client:client.close()
 mode('ok')
 try:policy('off');receipt['canary_restored_off']=True
 finally:(HERE/'receiver-v2-live.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
