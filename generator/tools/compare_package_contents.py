"""Bound the contents of files that the cross-OS manifest comparison exempts."""
from __future__ import annotations

import argparse
import copy
import hashlib
from itertools import combinations
import json
import math
from pathlib import Path
import sys

from PIL import Image
from ezdxf.lldxf.tagger import ascii_tags_loader
from ezdxf.lldxf.types import TYPE_TABLE

from hanok_generator.package import PNG_FILES, PackageError, verify

# Support both direct script execution and importing from regression tests.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.compare_package_manifests import ARTIFACT_PREFIX, SYSTEMS, ComparisonError, compare, load_manifests

TOLERANCE = 1e-7
FONT = Path(__file__).resolve().parents[1] / "tests/fixtures/fonts/NotoSans.ttf"
PLATFORMS = dict(zip(SYSTEMS, ("linux", "darwin", "win32")))


def same_json(left, right, path="value"):
    """All structure and discrete values match; finite floats get an absolute bound."""
    if isinstance(left, float) and isinstance(right, (float, int)) and not isinstance(right, bool):
        if not (math.isfinite(left) and math.isfinite(right) and abs(left-right) <= TOLERANCE):
            raise ComparisonError(f"{path}: numbers differ beyond {TOLERANCE}")
    elif type(left) is not type(right):
        raise ComparisonError(f"{path}: value types differ")
    elif isinstance(left, dict):
        if left.keys() != right.keys():
            raise ComparisonError(f"{path}: keys differ")
        for key in left:
            same_json(left[key], right[key], f"{path}.{key}")
    elif isinstance(left, list):
        if len(left) != len(right):
            raise ComparisonError(f"{path}: lengths differ")
        for index, (a, b) in enumerate(zip(left, right)):
            same_json(a, b, f"{path}[{index}]")
    elif left != right:
        raise ComparisonError(f"{path}: values differ")


def environment(folder, system, font_hash):
    env = json.loads((folder / "environment.json").read_text(encoding="utf-8"))
    if env["platform"] != PLATFORMS[system]:
        raise ComparisonError(f"{system}: incorrect environment platform")
    if set(env["fonts"]) != {"regular", "bold", "mono"}:
        raise ComparisonError(f"{system}: font roles differ")
    for face in env["fonts"].values():
        if face["sha256"] != font_hash:
            raise ComparisonError(f"{system}: render did not use the pinned font")
    stable = copy.deepcopy(env)
    # Runner metadata may differ. Library pins, source hashes, format contract,
    # hash seed and font bytes must still agree across operating systems.
    del stable["platform"], stable["machine"]
    stable["python"] = ".".join(stable["python"].split(".")[:2])
    for face in stable["fonts"].values():
        face.pop("path")
    return env, stable


def validation(folder, env):
    report = json.loads((folder / "validation_report.json").read_text(encoding="utf-8"))
    if report.pop("sha256") != hashlib.sha256((folder / "window.dxf").read_bytes()).hexdigest():
        raise ComparisonError("validation_report.json: DXF hash does not match actual file")
    if report.pop("render_environment") != {key: env[key] for key in ("fonts", "libraries")}:
        raise ComparisonError("validation_report.json: render environment differs from environment.json")
    return report


def dxf_tags(path):
    with path.open(encoding="utf-8") as stream:
        return [(tag.code, float(tag.value) if TYPE_TABLE.get(tag.code) is float else tag.value)
                for tag in ascii_tags_loader(stream, skip_comments=False)]


def check(root, font=FONT):
    success, report = compare(load_manifests(root))
    if not success:
        raise ComparisonError(report)
    font_hash = hashlib.sha256(font.read_bytes()).hexdigest()
    packages, environments, reports, drawings = {}, {}, {}, {}
    for system in SYSTEMS:
        manifest, = (root / (ARTIFACT_PREFIX + system)).rglob("package_manifest.json")
        folder = manifest.parent
        verify(folder)  # every payload byte must match the downloaded inventory
        packages[system] = folder
        env, environments[system] = environment(folder, system, font_hash)
        reports[system] = validation(folder, env)
        drawings[system] = dxf_tags(folder / "window.dxf")
    for a, b in combinations(SYSTEMS, 2):
        same_json(environments[a], environments[b], f"{a}/{b} environment")
        same_json(reports[a], reports[b], f"{a}/{b} validation")
        left, right = drawings[a], drawings[b]
        if len(left) != len(right):
            raise ComparisonError(f"{a}/{b}: DXF tag counts differ")
        for index, ((code_a, value_a), (code_b, value_b)) in enumerate(zip(left, right)):
            if code_a != code_b:
                raise ComparisonError(f"{a}/{b}: DXF group code differs at tag {index}")
            same_json(value_a, value_b, f"{a}/{b} DXF tag {index} code {code_a}")
        for name in PNG_FILES:
            with Image.open(packages[a] / name) as x, Image.open(packages[b] / name) as y:
                if x.size != y.size or x.convert("RGBA").tobytes() != y.convert("RGBA").tobytes():
                    raise ComparisonError(f"{a}/{b}: {name} pixels differ")
    return ("PASS: all payload hashes; pinned-font PNG pixels; DXF tags and validation values "
            f"within absolute {TOLERANCE}; source, library and format records match")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", type=Path)
    parser.add_argument("--font", type=Path, default=FONT)
    args = parser.parse_args(argv)
    try:
        print(check(args.artifacts, args.font))
        return 0
    except (ComparisonError, PackageError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
