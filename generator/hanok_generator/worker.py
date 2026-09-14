"""Internal subprocess entry point. Never publishes a partial package."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .package import environment, export_source, seal, write_json


def fault_at(injection, stage):
    # Used only by internal regression tests, not accepted by the public request schema.
    if injection==f"terminate:{stage}":
        os._exit(97)
    if injection==stage:
        raise OSError(f"Injected failure at {stage}")


def generate(payload, output, injection=None):
    from .engine import builder
    params=payload["parameters"]
    write_json(output/"design_request.json",payload["input_request"])
    write_json(output/"design_parameters.json",params)
    write_json(output/"resolved_parameters.json",payload)
    env=environment()
    builder.configure(params,output)
    # CSV failures occur after successful CAD validation and file replacement.
    if injection=="csv":
        original=builder.write_manifests
        def write_then_fail(doc):
            original(doc)
            fault_at(injection,"csv")
        builder.write_manifests=write_then_fail
    fault_at(injection,"cad")
    doc,report,positions=builder.build()
    fault_at(injection,"render")
    builder.render_nesting(doc,report)
    builder.render_details(doc,positions)
    builder.render_assembly(doc)
    builder.render_opening(doc)
    builder.render_closeup(doc,report)
    builder.write_readme(report)
    report["window"]=params["window"]
    report["render_environment"]={k:env[k] for k in ("fonts","libraries")}
    report["visual_inspection_status"]="AUTOMATED_CONTENT_CHECKS_ONLY"
    write_json(output/"validation_report.json",report)
    write_json(output/"environment.json",env)
    export_source(output,env)
    fault_at(injection,"manifest")
    manifest=seal(output)
    return dict(status="PASS",package_id=manifest["package_id"],checks=report["checks_passed"],
                parts=report["parts_total"],pockets=report["nominal_pockets_total"],
                dogbones=report["dogbone_reliefs_total"],manufacturing_status="PENDING")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("payload",type=Path)
    parser.add_argument("output",type=Path)
    parser.add_argument("result",type=Path)
    parser.add_argument("--fault")
    args=parser.parse_args()
    try:
        if os.environ.get("PYTHONHASHSEED")!="0":
            raise RuntimeError("Worker must start with PYTHONHASHSEED=0")
        result=generate(json.loads(args.payload.read_text(encoding="utf-8")),args.output,args.fault)
        write_json(args.result,result)
        return 0
    except Exception as exc:
        result=dict(status="FAIL",rule_id=getattr(exc,"rule_id","build.failed"),
                    message=str(exc),details=getattr(exc,"details",{}))
        if hasattr(exc,"report"):
            result.update(rule_id="geometry.validation",validation=exc.report)
        write_json(args.result,result)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
