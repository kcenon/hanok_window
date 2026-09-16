"""Compare one R3 manifest per CI operating system, with explicit byte exceptions."""
from __future__ import annotations

import argparse
import html
from itertools import combinations
import json
from pathlib import Path
import re


SYSTEMS = ("ubuntu-latest", "macos-latest", "windows-latest")
PAIRS = tuple(combinations(SYSTEMS, 2))
UBUNTU_PAIRS = tuple(pair for pair in PAIRS if "ubuntu-latest" in pair)
ARTIFACT_PREFIX = "r3-manifest-"

# Evidence: generator/docs/CHANGELOG.md, 0.5.0, the cross-OS comparison row.
# Each entry permits only these OS pairs to differ in hash or size. File presence
# is never exempt. Equality is always allowed, and unused exceptions are reported.
EXCEPTIONS = {
    "environment.json": (PAIRS,
        "Records OS, architecture, Python/library versions and font paths/hashes "
        "(hanok_generator/package.py: environment)."),
    "01_one_board_nesting.png": (PAIRS,
        "Nesting labels use OS-selected fonts (engine/cad_helpers.py: font; 0.5.0 OS comparison)."),
    "02_joinery_details.png": (PAIRS,
        "Joinery labels use OS-selected fonts (engine/cad_helpers.py: font; 0.5.0 OS comparison)."),
    "03_assembly_reference.png": (PAIRS,
        "Assembly labels use OS-selected fonts (engine/cad_helpers.py: font; 0.5.0 OS comparison)."),
    "04_opening_reference.png": (PAIRS,
        "Opening labels use OS-selected fonts (engine/cad_helpers.py: font; 0.5.0 OS comparison)."),
    "05_all_pockets_closeup.png": (PAIRS,
        "Pocket labels use OS-selected fonts (engine/cad_helpers.py: font; 0.5.0 OS comparison)."),
    "validation_report.json": (PAIRS,
        "Includes unrounded geometry measurements and the saved DXF hash "
        "(engine/builder.py: validate/build; 0.5.0 OS comparison)."),
    "window.dxf": (UBUNTU_PAIRS,
        "Linux libm changes the last bit of a reference arc coordinate; macOS and Windows "
        "must still match (CHANGELOG.md: 0.5.0 OS comparison and AI export #18)."),
}


class ComparisonError(ValueError):
    pass


def unique_object(pairs):
    """Reject duplicate JSON keys instead of silently keeping the last value."""
    value = {}
    for key, item in pairs:
        if key in value:
            raise ComparisonError(f"Duplicate JSON key: {key!r}")
        value[key] = item
    return value


def is_digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def file_entries(manifest):
    """Validate the supported manifest contract before comparing file identities."""
    fields = {"schema_version", "package_id", "status", "manufacturing_status", "files"}
    if not isinstance(manifest, dict) or set(manifest) != fields:
        raise ComparisonError("Invalid manifest fields")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ComparisonError("Unsupported schema_version")
    if manifest["status"] != "COMPLETE_NOMINAL_CAD" or manifest["manufacturing_status"] != "PENDING":
        raise ComparisonError("Invalid package status or manufacturing_status")
    if not is_digest(manifest["package_id"]):
        raise ComparisonError("Invalid package_id")
    rows = manifest["files"]
    if not isinstance(rows, list) or not rows:
        raise ComparisonError("files must be a nonempty list")
    entries = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "bytes", "sha256"}:
            raise ComparisonError("Invalid file entry fields")
        path = row["path"]
        if (not isinstance(path, str) or not path or "\\" in path or ":" in path
                or any(part in ("", ".", "..") for part in path.split("/"))
                or any(ord(char) < 32 or ord(char) == 127 for char in path)):
            raise ComparisonError(f"Invalid relative file path: {path!r}")
        if path in entries:
            raise ComparisonError(f"Duplicate file path: {path!r}")
        if type(row["bytes"]) is not int or row["bytes"] < 0 or not is_digest(row["sha256"]):
            raise ComparisonError(f"Invalid bytes or sha256: {path!r}")
        entries[path] = (row["bytes"], row["sha256"])
    return entries


def load_manifests(root):
    """Accept only the expected three artifacts, each containing one manifest."""
    root = Path(root)
    expected = {ARTIFACT_PREFIX + system for system in SYSTEMS}
    found = {path.name for path in root.iterdir()}
    if found != expected:
        raise ComparisonError(f"Artifact set mismatch: missing={sorted(expected - found)!r}, "
                              f"extra={sorted(found - expected)!r}")
    manifests = {}
    for system in SYSTEMS:
        artifact = root / (ARTIFACT_PREFIX + system)
        paths = sorted(artifact.rglob("package_manifest.json"))
        if not artifact.is_dir() or artifact.is_symlink() or len(paths) != 1:
            raise ComparisonError(f"{system}: expected exactly one package_manifest.json, found {len(paths)}")
        path = paths[0]
        if not path.is_file() or path.is_symlink():
            raise ComparisonError(f"{system}: manifest must be a regular file")
        try:
            manifests[system] = file_entries(json.loads(path.read_text(encoding="utf-8"),
                                                       object_pairs_hook=unique_object))
        except (ComparisonError, OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ComparisonError(f"{system}: {exc}") from exc
    return manifests


def compare(manifests):
    """Return (success, diagnostic text); compare every OS pair, never just a baseline."""
    if set(manifests) != set(SYSTEMS):
        raise ComparisonError("Expected Ubuntu, macOS and Windows manifests")
    paths = sorted(set().union(*(set(rows) for rows in manifests.values())))
    counts = dict(equal=0, expected=0, unexpected=0)
    details = []
    used = set()
    for path in paths:
        missing = [system for system in SYSTEMS if path not in manifests[system]]
        allowed, reason = EXCEPTIONS.get(path, ((), "No exception for this path."))
        if missing:
            verdict = "unexpected"
            details.append(f"UNEXPECTED {path!r}: missing from {', '.join(missing)}")
        else:
            different = [pair for pair in PAIRS if manifests[pair[0]][path] != manifests[pair[1]][path]]
            if not different:
                counts["equal"] += 1
                continue
            unexpected = [pair for pair in different if pair not in allowed]
            verdict = "unexpected" if unexpected else "expected"
            if any(pair in allowed for pair in different):
                used.add(path)
            details.append(f"{verdict.upper()} {path!r}")
            for pair in different:
                label = "allowed" if pair in allowed else "unexpected"
                details.append(f"  {pair[0]} vs {pair[1]}: {label}")
            details.append(f"  Policy: {reason}")
        counts[verdict] += 1
        for system in SYSTEMS:
            if path in manifests[system]:
                size, digest = manifests[system][path]
                details.append(f"  {system}: bytes={size} sha256={digest}")
    success = counts["unexpected"] == 0
    lines = [f"{'PASS' if success else 'FAIL'}: {len(paths)} files; equal={counts['equal']}; "
             f"expected differences={counts['expected']}; unexpected differences={counts['unexpected']}"]
    lines.extend(details)
    unused = sorted(set(EXCEPTIONS) - used)
    if unused:
        lines.append("Unused exceptions (review for removal): " + ", ".join(unused))
    lines.append("Exceptions permit whole-file byte differences; they do not bound changes within those files.")
    return success, "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", type=Path, help="directory containing the three r3-manifest-* artifacts")
    parser.add_argument("--summary", type=Path, help="append the result to a GitHub Actions job summary")
    args = parser.parse_args(argv)
    try:
        success, report = compare(load_manifests(args.artifacts))
    except (ComparisonError, OSError) as exc:
        success, report = False, f"FAIL: {exc}"
    print(report)
    if args.summary:
        with args.summary.open("a", encoding="utf-8", newline="\n") as output:
            output.write("### R3 package comparison\n\n<pre>" + html.escape(report) + "</pre>\n")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
