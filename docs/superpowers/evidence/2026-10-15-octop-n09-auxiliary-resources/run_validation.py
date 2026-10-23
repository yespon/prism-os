"""Retain real subprocess results without Windows/WSL shell interpolation."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("name")
parser.add_argument("--cwd", choices=("root", "backend", "frontend"), default="root")
parser.add_argument("command", nargs=argparse.REMAINDER)
args = parser.parse_args()
if not args.name.replace("-", "").isalnum():
    parser.error("name must be alphanumeric or hyphenated")
command = args.command[1:] if args.command[:1] == ["--"] else args.command
if not command:
    parser.error("command required")
cwd = ROOT if args.cwd == "root" else ROOT / args.cwd
receipt_path = HERE / (args.name + "-result.json")
log_path = HERE / "logs" / (args.name + ".log")
if receipt_path.exists() or log_path.exists():
    parser.error("retain previous results: use a new validation name")
receipt = {"command": command, "cwd": str(cwd), "started_at": datetime.now(timezone.utc).isoformat(), "complete": False}
receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
with log_path.open("w") as stream:
    result = subprocess.run(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
receipt.update(complete=True, returncode=result.returncode, finished_at=datetime.now(timezone.utc).isoformat())
receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt))
sys.exit(result.returncode)
