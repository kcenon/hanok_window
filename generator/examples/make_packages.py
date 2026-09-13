"""Rebuild examples/packages/ and built_packages.json from the example inputs.

Run from generator/: .venv/bin/python examples/make_packages.py
Every examples/*.json is built the way the CLI builds it, into a temporary output folder. Only
when all builds pass is packages/ replaced: each package is copied to packages/<example name>/
and verified there. Folder names differ from output/packages/<package id>/ on purpose; the
package id stays in package_manifest.json, and verification does not depend on the folder name.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile

from hanok_generator.jobs import run_job
from hanok_generator.package import verify

HERE = Path(__file__).resolve().parent
PACKAGES = HERE / "packages"
RESULTS = HERE / "built_packages.json"


def main():
    with tempfile.TemporaryDirectory(prefix="hanok-examples-") as tmp:
        built = {path.stem: run_job(json.loads(path.read_text(encoding="utf-8")), tmp)
                 for path in sorted(HERE.glob("*.json")) if path != RESULTS}
        shutil.rmtree(PACKAGES, ignore_errors=True)
        results = {}
        for name, result in built.items():
            target = PACKAGES / name
            shutil.copytree(result["package"], target)
            verify(target)
            # Paths relative to generator/, like the README commands.
            relative = target.relative_to(HERE.parent).as_posix()
            results[name] = dict(result, package=relative, manifest=f"{relative}/package_manifest.json")
            print(f"{name}: {result['package_id'][:12]} ({result['checks']} checks)")
    RESULTS.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
