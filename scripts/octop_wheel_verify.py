#!/usr/bin/env python3
"""Check a built wheel against its pinned provenance, then import its installed files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    with zipfile.ZipFile(args.wheel) as wheel:
        provenance = json.loads(wheel.read("prismos_octop/data/provenance.json"))
        for entry in provenance["imports"]:
            actual = hashlib.sha256(
                wheel.read("prismos_octop/" + entry["target"])
            ).hexdigest()
            if actual != entry["sha256"]:
                raise ValueError("Wheel source integrity failure: " + entry["target"])
        with tempfile.TemporaryDirectory(prefix="prismos-octop-wheel-") as folder:
            installed = Path(folder)
            for name in wheel.namelist():
                path = installed / name
                if not path.resolve().is_relative_to(installed.resolve()):
                    raise ValueError("Invalid wheel member")
            wheel.extractall(installed)
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(installed)
            check = """
import json
from pathlib import Path
import prismos_octop.catalog as catalog
assert Path(catalog.__file__).is_relative_to(Path.cwd())
origin = catalog.provenance()
print(json.dumps({"revision": origin["revision"], "verified_files": len(origin["imports"]), "zh_templates": len(catalog.list_templates("zh")), "en_templates": len(catalog.list_templates("en")), "personas": len(catalog.list_personas()), "installed_wheel": True}))
"""
            subprocess.run(
                [sys.executable, "-c", check],
                cwd=installed,
                env=environment,
                check=True,
            )


if __name__ == "__main__":
    main()
