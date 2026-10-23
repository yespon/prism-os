import json,subprocess
from live_common import HERE,expect,login
owner=login('approver')
proof={'approval_states':{},'timeline_successes':{},'scope':'real authenticated reads of durable approval and original timeline facts; no model or ticket send'}
try:
 for filename in ['approval-matrix.json','approval-remaining.json','approval-policy-synchronized.json']:
  data=json.loads((HERE/filename).read_text())
  for case in data['cases']:
   if not case['complete']:continue
   approval=case['waiting']['approval_id'];row=expect(owner,'/api/approvals/'+approval)
   scenario=case['scenario']
   if scenario in ['revoke_agent','withdraw_secret','rotate_secret']:assert row['status'] in ['approved','expired']
   if scenario in ['approve','restart']:
    assert row['status']=='consumed'
    ticket=case['resumed']['ticket_id']
    timeline=expect(owner,'/api/incidents/'+case['incident_id']+'/timeline')
    assert ticket in json.dumps(timeline)
    proof['timeline_successes'][approval]={'ticket_id':ticket,'original_timeline_contains_ticket':True}
   if scenario=='reject':assert row['status']=='rejected'
   proof['approval_states'][approval]={'scenario':scenario,'status':row['status']}
 negative=json.loads((HERE/'policy-change-synchronized.json').read_text())
 approval=negative['decision_before']['approval_id'];row=expect(owner,'/api/approvals/'+approval)
 assert row['status'] in ['approved','expired']
 proof['policy_changed_approval_not_consumed']={'approval_id':approval,'status':row['status']}
finally:owner.close()
(HERE/'durable-facts.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps({'approval_facts':len(proof['approval_states']),'original_timeline_facts':len(proof['timeline_successes']),'changed_policy_did_not_consume':True}))
