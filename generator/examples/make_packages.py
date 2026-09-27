"""Publish complete example packages and their index together, or check them read-only."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile

from hanok_generator.jobs import run_job
from hanok_generator.package import digest, source_files, verify, write_json

HERE = Path(__file__).resolve().parent


def inputs():
    return {p.stem: json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(HERE.glob("*.json")) if p.name != "built_packages.json"}


def readme(results):
    lines = ["# 생성된 예제 패키지", "",
             "현재 생성 소스로 만든 패키지입니다. 각 폴더의 도면·표·검증 기록을 함께 사용합니다.",
             "제작 상태는 PENDING이며 실제 제작 승인을 뜻하지 않습니다.", "",
             "`../make_packages.py --check`가 입력·포함 소스·파일 무결성과 목록을 확인합니다.",
             "같은 패키지 ID를 재현하려면 환경 기록의 Python·라이브러리·폰트도 같아야 합니다.", "",
             "| 예제 | 패키지 ID | 검사 / 파일 | 산출물 |", "|---|---|---|---|"]
    for name, result in results.items():
        links = " · ".join(f"[{label}]({name}/{path})" for label, path in
                           [("안내", "README.txt"), ("조립도", "03_assembly_reference.png"),
                            ("원판", "01_one_board_nesting.png"), ("DXF", "window.dxf"),
                            ("AI", "window.ai"), ("검증", "validation_report.json")])
        lines.append(f"| {name} | `{result['package_id'][:12]}` | {result['checks']} / {result['files']} | {links} |")
    return "\n".join(lines) + "\n"


def check(target):
    requests = inputs()
    results = json.loads((target / "index.json").read_text(encoding="utf-8"))
    expected = {*requests, "index.json", "README.md"}
    if set(results) != set(requests) or {p.name for p in target.iterdir()} != expected:
        raise ValueError("Example input, package and index names differ")
    sources = {name: digest(path) for name, path in source_files()}
    for name, request in requests.items():
        folder = target / name
        verified = verify(folder)
        result = results[name]
        if any(result[k] != verified[k] for k in ("package_id", "files", "status")):
            raise ValueError(f"{name}: index differs from verified package")
        actual = json.loads((folder / "design_request.json").read_text(encoding="utf-8"))
        env = json.loads((folder / "environment.json").read_text(encoding="utf-8"))
        report = json.loads((folder / "validation_report.json").read_text(encoding="utf-8"))
        if actual != request or env["source_sha256"] != sources:
            raise ValueError(f"{name}: regenerate after changing its input or generator sources")
        for path, expected_hash in sources.items():
            if digest(folder / "source/hanok_generator" / path) != expected_hash:
                raise ValueError(f"{name}: included source differs: {path}")
        for key, report_key in (("checks", "checks_passed"), ("parts", "parts_total"),
                                ("pockets", "nominal_pockets_total"), ("dogbones", "dogbone_reliefs_total")):
            if result[key] != report[report_key]:
                raise ValueError(f"{name}: index {key} differs from saved report")
        if result["manufacturing_status"] != "PENDING":
            raise ValueError(f"{name}: unexpected manufacturing status")
    if (target / "README.md").read_text(encoding="utf-8") != readme(results):
        raise ValueError("Example README differs from its index")
    return results


def generate(target):
    target = target.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".hanok-examples-", dir=target.parent) as temporary:
        root = Path(temporary)
        staged = root / "packages"
        staged.mkdir()
        results = {}
        for name, request in inputs().items():
            result = run_job(request, root / "builds")
            folder = staged / name
            shutil.copytree(result["package"], folder)
            verified = verify(folder)
            results[name] = {k: result[k] for k in
                             ("package_id", "status", "checks", "parts", "pockets", "dogbones", "manufacturing_status")}
            results[name]["files"] = verified["files"]
        write_json(staged / "index.json", results)
        (staged / "README.md").write_bytes(readme(results).encode("utf-8"))
        check(staged)
        # Keep the previous examples until every replacement is built and checked.
        # Both renames stay on the same filesystem; restore on publication failure.
        backup = root / "previous"
        if target.exists():
            os.replace(target, backup)
        try:
            os.replace(staged, target)
        except BaseException:
            if backup.exists():
                os.replace(backup, target)
            raise
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "packages")
    parser.add_argument("--check", action="store_true", help="verify committed examples without changing them")
    args = parser.parse_args(argv)
    try:
        results = check(args.output) if args.check else generate(args.output)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"Examples failed: {exc}\n")
    print(f"PASS: {len(results)} example packages, inputs, sources and indexes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
