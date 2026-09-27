"""Public command line: build a package, inspect resolved inputs, or verify files."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from importlib.resources import files
import json
from pathlib import Path
import sys

from .jobs import JobError, run_job
from .model import InputError, PRESETS, resolve
from .package import PackageError, verify


def dimension_pair(text, integer=False):
    try:
        values=text.lower().replace("×","x").split("x")
        if len(values)!=2:
            raise ValueError
        return [int(q) if integer else float(q) for q in values]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("463x586 또는 2x4 형태로 입력하세요.") from exc


def read_request(args):
    flags=("type","size","size_basis","lattice","hinge_side","preset","picture","picture_margin")
    if args.input:
        if any(getattr(args,k,None) is not None for k in flags):
            raise InputError("input.conflicting_sources","--input과 설계 입력 옵션을 함께 사용하지 마세요.")
        if args.input.stat().st_size>65536:
            raise InputError("input.too_large","입력 JSON은 64 KiB 이하로 제한합니다.")
        def invalid_constant(value):
            raise InputError("input.number","NaN과 Infinity는 사용할 수 없습니다.")
        return json.loads(args.input.read_text(encoding="utf-8"),parse_constant=invalid_constant)
    request=dict(type=args.type,lattice_per_leaf=args.lattice)
    request["inner_mm" if args.size_basis=="inner" else "outer_mm"]=args.size
    if args.hinge_side is not None:request["hinge_side"]=args.hinge_side
    if args.preset is not None:request["preset"]=args.preset
    if args.picture is not None:
        request["picture"]=dict(size_mm=args.picture,margin_mm=args.picture_margin if args.picture_margin is not None else 10)
    elif args.picture_margin is not None:
        raise InputError("input.picture_margin","--picture-margin에는 --picture가 필요합니다.")
    return request


def parser():
    result=argparse.ArgumentParser(prog="hanok-window",description="창 외경 또는 내경·창살 수·창 형식으로 한옥 창호 CAD 패키지를 만듭니다.")
    sub=result.add_subparsers(dest="command",required=True)
    for name,help in [("build","검증한 패키지 생성"),("resolve","입력·프리셋 해석 및 기하 사전 검사")]:
        p=sub.add_parser(name,help=help)
        p.add_argument("--input",type=Path,help="JSON 입력 파일")
        p.add_argument("--type",choices=("single","double"))
        p.add_argument("--hinge-side",choices=("left","right"))
        p.add_argument("--size",type=dimension_pair,help="창 크기 W x H mm, 예: 463x586. 기준은 --size-basis")
        p.add_argument("--size-basis",choices=("outer","inner"),help="outer=외경(완성 외곽, 기본), inner=내경(고정틀 안목)")
        p.add_argument("--lattice",type=lambda s:dimension_pair(s,True),help="창짝당 세로 x 가로 창살 수, 예: 2x4")
        p.add_argument("--preset",choices=PRESETS)
        p.add_argument("--picture",type=dimension_pair,help="선택 그림 크기 mm")
        p.add_argument("--picture-margin",type=float)
        if name=="build":p.add_argument("--output",type=Path,default=Path("output"))
    p=sub.add_parser("verify",help="패키지 무결성 읽기 전용 대조")
    p.add_argument("package",type=Path)
    sub.add_parser("schema",help="JSON 입력 스키마 출력")
    sub.add_parser("presets",help="지원 프리셋 목록")
    return result


def main(argv=None):
    # Pipes default to the locale encoding (cp949 on Korean Windows); callers read this JSON as UTF-8.
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,"reconfigure"):stream.reconfigure(encoding="utf-8")
    args=parser().parse_args(argv)
    try:
        if args.command=="build":result=run_job(read_request(args),args.output)
        elif args.command=="resolve":
            from .engine.generate_spec import build
            design=resolve(read_request(args));spec=build(design.parameters)
            result=dict(status="RESOLVED_NOT_DXF_VALIDATED",**asdict(design),derived=spec["derived"])
        elif args.command=="verify":result=verify(args.package)
        elif args.command=="schema":result=json.loads(files("hanok_generator").joinpath("request.schema.json").read_text(encoding="utf-8"))
        else:result=dict(presets=list(PRESETS),default="standard_v1")
        print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
        return 0
    except JobError as exc:
        print(json.dumps(exc.result,ensure_ascii=False,indent=2),file=sys.stderr)
        return 1
    except Exception as exc:
        result=dict(status="FAIL",rule_id=getattr(exc,"rule_id","input.invalid"),message=str(exc),details=getattr(exc,"details",{}))
        print(json.dumps(result,ensure_ascii=False,indent=2),file=sys.stderr)
        return 2
