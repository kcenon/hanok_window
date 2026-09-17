"""Complete, reproducible package manifests and read-only integrity checks."""
from __future__ import annotations

import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import shutil
import sys

from .model import canonical
from .engine import output_formats

PNG_FILES = ["01_one_board_nesting.png", "02_joinery_details.png", "03_assembly_reference.png",
             "04_opening_reference.png", "05_all_pockets_closeup.png"]
CSV_FILES = ["parts_manifest.csv", "pocket_manifest.csv", "dogbone_manifest.csv", "hardware_reference_manifest.csv"]
BASE_REQUIRED = {"window.dxf", "README.txt", "design_request.json", "design_parameters.json", "design_spec.json",
            "resolved_parameters.json", "validation_report.json", "environment.json", "source/requirements.txt",
            "source/hanok_generator/__main__.py", *PNG_FILES, *CSV_FILES}
DEPENDENCIES = ("ezdxf", "shapely", "Pillow", "numpy", "fonttools", "pyparsing", "typing_extensions")


def required_files():
    return BASE_REQUIRED | set(output_formats.filenames())


class PackageError(ValueError):
    pass


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_bytes((json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)+"\n").encode("utf-8"))


def package_files(root):
    for p in sorted(Path(root).rglob("*")):
        relative=p.relative_to(root)
        if "__pycache__" in relative.parts or p.name==".DS_Store":
            continue
        if p.is_symlink():
            raise PackageError(f"Symbolic links are not package files: {relative}")
        if p.is_file() and relative.as_posix()!="package_manifest.json":
            yield relative.as_posix(),p


def source_files():
    root=Path(__file__).parent
    # Outputs may be placed below the package directory by a CLI caller. Never
    # capture a generated package (and its embedded source) recursively as code.
    paths=[*root.glob("*.py"), *root.joinpath("engine").glob("*.py"),
           *root.joinpath("presets").glob("*.json"), root/"request.schema.json"]
    return [(p.relative_to(root).as_posix(),p) for p in sorted(paths) if p.is_file()]


def environment():
    from .engine import cad_helpers
    fonts={}
    for role,opts in [("regular",{}),("bold",{"bold":True}),("mono",{"mono":True})]:
        face=cad_helpers.font(12,**opts)
        path=Path(face.path) if getattr(face,"path",None) else None
        fonts[role]=dict(path=str(path) if path else "Pillow default",
                         sha256=digest(path) if path and path.is_file() else None)
    return dict(python=platform.python_version(),platform=sys.platform,machine=platform.machine(),
                libraries={name:metadata.version(name) for name in DEPENDENCIES},fonts=fonts,
                python_hash_seed="0",source_sha256={name:digest(path) for name,path in source_files()})


def export_source(root, env):
    for name,path in source_files():
        dest=root/"source/hanok_generator"/name
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,dest)
    (root/"source/requirements.txt").write_bytes(("\n".join(f"{k}=={v}" for k,v in sorted(env["libraries"].items()))+"\n").encode("utf-8"))


def seal(root):
    from PIL import Image
    root=Path(root)
    found={name for name,_ in package_files(root)}
    missing=required_files()-found
    if missing:
        raise PackageError(f"Missing required artifacts: {sorted(missing)}")
    for name in PNG_FILES:
        with Image.open(root/name) as im:
            im.verify()
    report=json.loads((root/"validation_report.json").read_text(encoding="utf-8"))
    if report.get("status")!="PASS_NOMINAL_DXF_GEOMETRY" or not report.get("saved_dxf_reread"):
        raise PackageError("A saved-DXF PASS is required before publication")
    if report.get("sha256")!=digest(root/"window.dxf"):
        raise PackageError("DXF differs from the validated file")
    rows=[dict(path=name,bytes=p.stat().st_size,sha256=digest(p)) for name,p in package_files(root)]
    package_id=hashlib.sha256(canonical(rows).encode()).hexdigest()
    manifest=dict(schema_version=1,package_id=package_id,status="COMPLETE_NOMINAL_CAD",
                  manufacturing_status="PENDING",files=rows)
    write_json(root/"package_manifest.json",manifest)
    verify(root)
    return manifest


def verify(root):
    root=Path(root)
    try:
        manifest=json.loads((root/"package_manifest.json").read_text(encoding="utf-8"))
        rows=manifest["files"]
        names=[row["path"] for row in rows]
        if len(names)!=len(set(names)) or any(Path(n).is_absolute() or ".." in Path(n).parts for n in names):
            raise PackageError("Invalid or duplicate manifest paths")
        found={name:p for name,p in package_files(root)}
        if set(names)!=set(found) or not required_files().issubset(found):
            raise PackageError("Package contents differ from manifest or required artifacts")
        bad=[row["path"] for row in rows if digest(found[row["path"]])!=row["sha256"] or found[row["path"]].stat().st_size!=row["bytes"]]
        if bad:
            raise PackageError("Changed files: "+", ".join(bad))
        if hashlib.sha256(canonical(rows).encode()).hexdigest()!=manifest["package_id"]:
            raise PackageError("Manifest content identity mismatch")
        return dict(status="PASS",package_id=manifest["package_id"],files=len(rows))
    except (OSError,KeyError,TypeError,json.JSONDecodeError) as exc:
        raise PackageError(f"Invalid package: {exc}") from exc
