#!/usr/bin/env python3
"""Check the packaged files against package_manifest.json, or rewrite it.

Verifying is the default and never touches anything on disk. Rewriting the
recorded hashes is a separate, explicit action, because a tool that silently
re-records whatever it finds cannot detect the corruption it exists to catch.
The build calls write_manifest() itself, so the manifest always describes the
files that build produced.

Run:
    python verify_package.py            # read-only; exit 1 on any difference
    python verify_package.py --write    # re-record hashes for the current files
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

# This script lives with the CNC sources but covers the whole package, so the
# plan documents are hashed too and the manifest sits at the package root.
CNC = Path(__file__).resolve().parent
ROOT = CNC.parent
MANIFEST = ROOT / 'package_manifest.json'
# Tooling and editor state is not part of the package. .venv in particular can be
# hundreds of megabytes and belongs to the machine, not to the design.
SKIP_DIRS = {'.venv', 'venv', '.claude', '.git', '__pycache__', '.idea', '.vscode',
             'node_modules', '.mypy_cache', '.pytest_cache'}
# Written by --validate-only on demand; recording it would make every recheck
# look like a package change.
SKIP_FILES = {MANIFEST.name, '.DS_Store', 'validation_report_recheck.json'}


def packaged_files():
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if rel.name in SKIP_FILES or any(part in SKIP_DIRS for part in rel.parts):
            continue
        yield rel, path


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def scan() -> dict:
    return {str(rel): dict(path=str(rel), bytes=p.stat().st_size, sha256=digest(p))
            for rel, p in packaged_files()}


def write_manifest() -> Path:
    """Record the current files. Called by the build; otherwise needs --write."""
    params = json.loads((CNC / 'design_parameters.json').read_text(encoding='utf-8'))
    report = json.loads((CNC / 'validation_report.json').read_text(encoding='utf-8'))
    rows = list(scan().values())
    manifest = dict(
        revision=params['revision'],
        build_date=params['build_date'],
        source_of_truth='design_parameters.json',
        overall_width_height_mm=report['overall_width_height_mm'],
        lattice_per_leaf=report['lattice_per_leaf'],
        validation=dict(status=report['status'], checks_passed=report['checks_passed'],
                        dxf_sha256=report['sha256']),
        reproducible_build=dict(
            dxf=('Byte-reproducible from the parameters alone: PYTHONHASHSEED=0 plus fixed '
                 'DXF metadata. Independent of the installed fonts.'),
            png=('Reproducible only where the same font files and the same Pillow version '
                 'resolve; the fonts actually used are recorded below.'),
            render_environment=report.get('render_environment', 'not recorded')),
        hash_algorithm='SHA-256',
        excluded=sorted(SKIP_FILES | {d + '/' for d in SKIP_DIRS}),
        file_count=len(rows), files=rows)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n',
                        encoding='utf-8')
    return MANIFEST


def verify() -> int:
    if not MANIFEST.is_file():
        print(f'FAIL: {MANIFEST.name} is missing; nothing to verify against')
        return 1
    recorded = {row['path']: row for row in
                json.loads(MANIFEST.read_text(encoding='utf-8'))['files']}
    found = scan()

    missing = sorted(set(recorded) - set(found))
    added = sorted(set(found) - set(recorded))
    changed = sorted(p for p in set(found) & set(recorded)
                     if found[p]['sha256'] != recorded[p]['sha256'])

    for label, rows in (('MISSING', missing), ('UNRECORDED', added), ('CHANGED', changed)):
        for path in rows:
            print(f'{label:11} {path}')
    total = len(missing) + len(added) + len(changed)
    if total:
        print(f'\nFAIL: {total} difference(s) against {MANIFEST.name} '
              f'({len(recorded)} files recorded, {len(found)} found).')
        print('Rebuild, or run --write only if you meant to re-record these files.')
        return 1
    print(f'OK: {len(found)} files match {MANIFEST.name}')
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--write', action='store_true',
                    help='overwrite package_manifest.json with the current files')
    args = ap.parse_args()
    if args.write:
        rows = len(scan())
        write_manifest()
        print(f'wrote {MANIFEST.name}: {rows} files')
        return 0
    return verify()


if __name__ == '__main__':
    raise SystemExit(main())
