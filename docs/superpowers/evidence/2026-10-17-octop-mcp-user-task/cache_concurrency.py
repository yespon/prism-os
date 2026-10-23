"""Bounded parallel real discovery under a controlled overlap, no model/tool execution."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import queue
import sys
import threading

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
from octop_wsl_native_env import NATIVE, runtime_environment
os.environ.update(runtime_environment())
os.chdir(NATIVE)
sys.path.insert(0, str(ROOT / 'backend'))
from deerflow.mcp import cache, tools

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', required=True, type=Path)
parser.add_argument('--expect-failure', action='store_true')
args = parser.parse_args()
assert not args.output.exists()
binding = json.loads((NATIVE / 'analytics-service/binding.json').read_text())
original = tools.get_mcp_tools


async def overlapped(**kwargs):
    await asyncio.sleep(0.15)
    return await original(**kwargs)


tools.get_mcp_tools = overlapped
barrier = threading.Barrier(3)
results = queue.Queue()


def worker(index):
    barrier.wait(timeout=5)
    async def load():
        return await cache.initialize_mcp_tools(binding['tenant_id'], binding['user_id'], frozenset({binding['server_name'], 'overlap-' + str(index)}))
    try:
        found = asyncio.run(asyncio.wait_for(load(), timeout=3))
        results.put({'index': index, 'loaded_tools': len(found), 'success': len(found) == 1})
    except Exception as error:
        results.put({'index': index, 'error_type': type(error).__name__, 'success': False})


threads = [threading.Thread(target=worker, args=(index,), daemon=True) for index in range(3)]
for thread in threads:
    thread.start()
for thread in threads:
    thread.join(timeout=6)
records = [results.get_nowait() for _ in range(results.qsize())]
receipt = {'complete': False, 'scope': 'three real independent-loop MCP discoveries with controlled overlap; no tool or model execution', 'results': records, 'live_threads': sum(thread.is_alive() for thread in threads)}
args.output.write_text(json.dumps(receipt, indent=2) + '\n')
assert len(records) == 3 and not receipt['live_threads']
success = all(record['success'] for record in records)
assert (not success) == args.expect_failure
receipt.update(complete=True, all_discoveries_succeeded=success)
args.output.write_text(json.dumps(receipt, indent=2) + '\n')
print('Real parallel MCP discovery overlap recorded')
