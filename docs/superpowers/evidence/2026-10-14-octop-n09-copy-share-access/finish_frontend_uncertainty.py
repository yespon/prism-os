"""Apply reviewed copy uncertainty fixes only after the in-flight upgrade is terminal."""
from pathlib import Path
import json, os, subprocess, sys, time
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
while True:
    p = HERE / "upgrade.json"
    d = json.loads(p.read_text()) if p.exists() else {}
    if any(v["returncode"] != 0 for v in d.get("versions", [])) or d.get("host_changed"):
        raise RuntimeError("Existing upgrade failed or inputs changed; inspect first")
    if d.get("complete"): break
    time.sleep(5)
path = ROOT / "frontend/src/core/agents/api.ts"
s = path.read_text()
old = '  return saveAgent(`/api/agents/${encodeURIComponent(name)}/copy`, "POST", request, options);'
new = '  try {\n    return await saveAgent(`/api/agents/${encodeURIComponent(name)}/copy`, "POST", request, options);\n  } catch (error) {\n    if (error instanceof AgentMutationError) throw error;\n    throw new AgentMutationError(503, true, "复制结果未确认，请先检查目标 Agent");\n  }'
assert s.count(old) == 1
path.write_text(s.replace(old, new))
path = ROOT / "frontend/src/components/workspace/agents/copy-agent-dialog.tsx"
s = path.read_text()
assert s.count("const existing = await getAgent(name);") == 1
s = s.replace("  const [shared, setShared] = useState(false);", "  const [attemptedName, setAttemptedName] = useState(name);\n  const [shared, setShared] = useState(false);")
s = s.replace("    if (!source.revision || pending || inspect || !isCurrent()) return;\n    setPending(true);", "    if (!source.revision || pending || inspect || !isCurrent()) return;\n    setAttemptedName(name);\n    setPending(true);")
s = s.replace("const existing = await getAgent(name);", "const existing = await getAgent(attemptedName);")
path.write_text(s)
(HERE / "frontend-uncertainty-fix-applied.json").write_text(json.dumps({"applied": True, "prior_upgrade_complete": d["complete"], "prior_host_changed": d["host_changed"]}, indent=2) + "\n")
os.environ["PATH"] = "/root/.nvm/versions/node/v24.11.1/bin:/root/.local/bin:/usr/local/bin:/usr/bin:/bin"
runner = str(HERE / "run_validation.py")
def run(name, cwd, command):
    subprocess.run([sys.executable, runner, "--cwd", cwd, name, "--", *command], cwd=ROOT, check=True)
run("frontend-uncertainty-related", "frontend", ["pnpm","test:unit","src/core/agents/api.test.ts","src/components/workspace/agents/copy-agent-dialog.test.tsx","--maxWorkers=2"])
run("frontend-lint-accepted", "frontend", ["pnpm","exec","eslint","src/components/workspace/agents/agent-card.tsx","src/components/workspace/agents/agent-gallery.tsx","src/components/workspace/agents/copy-agent-dialog.tsx","src/components/workspace/agents/copy-agent-dialog.test.tsx","src/core/agents/api.ts","src/core/agents/api.test.ts","src/core/agents/types.ts"])
run("frontend-full-accepted","frontend",["pnpm","test:unit","--maxWorkers=2"])
run("frontend-production-accepted","frontend",["pnpm","build"])
run("upgrade-accepted","root",[sys.executable,str(ROOT/"scripts/octop_upgrade_probe.py"),"--previous-archive","/tmp/prismos-copy-share-upgrade/previous/upstream.tar.gz","--previous-receipt","/tmp/prismos-copy-share-upgrade/previous/manifest.json","--previous-revision","e473dd3c4a4741618ffde1a42a3492341a189e8e","--previous-release","0.3.0b5","--output",str(HERE/"upgrade-accepted.json"),"--test-file","tests/test_agent_copy_share_boundaries.py"])
print("Final frontend uncertainty fixes and validations completed",flush=True)
