"""Actual loaded MCP tool against a real target after product-config disable."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import secrets
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
from octop_wsl_native_env import NATIVE, runtime_environment
os.environ.update(runtime_environment())
os.chdir(NATIVE)
sys.path.insert(0, str(ROOT / 'backend'))
from deerflow.runtime import load_runtime_adapters
load_runtime_adapters()
import httpx
from langgraph.graph import START, END, StateGraph
from deerflow.config.tenant_context import tenant_context
from deerflow.mcp.tools import get_mcp_tools

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', required=True, type=Path)
parser.add_argument('--expect-bypass', action='store_true')
args = parser.parse_args()
assert not args.output.exists()
fixture = json.loads((NATIVE / 'live-fixture.json').read_text())
binding = json.loads((NATIVE / 'analytics-service/binding.json').read_text())
accepted = json.loads((HERE / 'real-mcp-task.json').read_text())
assert accepted['complete']
context = {k: accepted[k] for k in ['thread_id', 'agent_name', 'agent_id']}
context.update(tenant_id=fixture['tenant_id'], user_id=fixture['users']['requester']['id'])
token = (NATIVE / 'analytics-service/token').read_text().strip()
client = httpx.Client(base_url='http://127.0.0.1:18036', headers={'X-Tenant-Id': context['tenant_id']}, trust_env=False, timeout=30)
a = fixture['users']['requester']
response = client.post('/api/auth/login', json={'email': a['email'], 'password': a['password']})
assert response.status_code == 200
client.headers['Authorization'] = 'Bearer ' + response.json()['session']['token']
original = client.get('/api/mcp/config').json()
receipt = {'complete': False, 'model_requests_sent': 0}


def stats():
    response = httpx.get('http://127.0.0.1:18041/stats', headers={'Authorization': 'Bearer ' + token}, trust_env=False)
    assert response.status_code == 200
    return response.json()['completed_tool_calls']


async def run():
    tools = await get_mcp_tools(user_id=context['user_id'], tenant_id=context['tenant_id'], server_names=frozenset({binding['server_name']}))
    assert len(tools) == 1
    disabled = json.loads(json.dumps(original))
    disabled['mcp_servers'][binding['server_name']]['enabled'] = False
    assert client.put('/api/mcp/config', json=disabled).status_code == 200
    before = stats()
    outcome = {'error_type': None}

    async def invoke(state):
        try:
            await tools[0].ainvoke({'csv_text': 'category,amount,marker\nW1,100,REVOKE_' + secrets.token_hex(6) + '\n'})
        except Exception as error:
            outcome['error_type'] = type(error).__name__
        return state

    graph = StateGraph(dict)
    graph.add_node('invoke_cached_tool', invoke)
    graph.add_edge(START, 'invoke_cached_tool')
    graph.add_edge('invoke_cached_tool', END)
    await graph.compile(checkpointer=False).ainvoke({}, context=context)
    after = stats()
    receipt.update(completed_calls_before=before, completed_calls_after=after, cached_tool_called_after_disable=after > before, error_type=outcome['error_type'])
    assert (after > before) == args.expect_bypass
    if not args.expect_bypass:
        assert after == before and outcome['error_type'] is not None
    receipt['complete'] = True


try:
    with tenant_context(user_id=context['user_id'], tenant_id=context['tenant_id']):
        asyncio.run(run())
finally:
    receipt['configuration_restored'] = client.put('/api/mcp/config', json=original).status_code == 200
    client.close()
    args.output.write_text(json.dumps(receipt, indent=2) + '\n')
print('Actual loaded-tool disable behavior recorded; config restored')
