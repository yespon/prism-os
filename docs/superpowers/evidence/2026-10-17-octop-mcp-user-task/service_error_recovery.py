"""Real MCP input error and successful recovery through a guarded native tool."""
import asyncio
import json
import os
from pathlib import Path
import secrets
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
from octop_wsl_native_env import NATIVE,runtime_environment
os.environ.update(runtime_environment())
os.chdir(NATIVE)
sys.path.insert(0,str(ROOT/'backend'))
import httpx
from langgraph.graph import START,END,StateGraph
from deerflow.runtime import load_runtime_adapters
from deerflow.config.tenant_context import tenant_context
from deerflow.mcp.tools import get_mcp_tools
load_runtime_adapters()
case=json.loads((HERE/'real-mcp-current-recovered.json').read_text());assert case['complete']
fixture=json.loads((NATIVE/'live-fixture.json').read_text());binding=json.loads((NATIVE/'analytics-service/binding.json').read_text())
context={k:case[k] for k in ['thread_id','agent_id','agent_name']};context.update(tenant_id=binding['tenant_id'],user_id=binding['user_id'])
output=HERE/'service-error-recovery.json';assert not output.exists()
receipt={'complete':False,'new_model_task_submissions':0,'scope':'real guarded MCP RPC; success counter excludes rejected/failed invocations'}
token=(NATIVE/'analytics-service/token').read_text().strip()


def stats():
 response=httpx.get('http://127.0.0.1:18041/stats',headers={'Authorization':'Bearer '+token},trust_env=False);assert response.status_code==200
 return response.json()['completed_tool_calls']


async def main():
 tools=await get_mcp_tools(user_id=binding['user_id'],tenant_id=binding['tenant_id'],server_names=frozenset({binding['server_name']}));assert len(tools)==1
 before=stats();errors=[]
 async def node(state):
  try:await tools[0].ainvoke({'csv_text':'category,amount,marker\nW1,not-a-number,INVALID_RPC\n'})
  except Exception as error:errors.append(type(error).__name__)
  assert errors and stats()==before
  marker='RECOVERY_'+secrets.token_hex(8)
  answer=await tools[0].ainvoke({'csv_text':'category,amount,marker\nW1,100,'+marker+'\n'})
  assert marker in str(answer) and '100' in str(answer)
  return state
 graph=StateGraph(dict);graph.add_node('actual_rpc',node);graph.add_edge(START,'actual_rpc');graph.add_edge('actual_rpc',END)
 await graph.compile(checkpointer=False).ainvoke({},context=context)
 after=stats();assert after==before+1
 receipt.update(complete=True,invalid_rpc_outbound=True,invalid_input_rejected_error_type=errors[0],successful_calls_before=before,successful_calls_after=after,valid_followup_completed=True)


try:
 with tenant_context(user_id=binding['user_id'],tenant_id=binding['tenant_id']):asyncio.run(main())
finally:output.write_text(json.dumps(receipt,indent=2)+'\n')
print('Actual MCP input error and valid follow-up verified')
