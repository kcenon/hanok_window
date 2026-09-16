"""API work that does not depend on HTTP: meta, in-process preview, package index and files."""
from __future__ import annotations

from collections import OrderedDict
import copy
from datetime import datetime, timezone
import hashlib
from importlib import metadata
from importlib.resources import files
import io
import json
import os
from pathlib import Path
import re
import threading
import time
import zipfile

from .. import __version__ as ENGINE_VERSION
from .. import formats
from ..engine import generate_spec
from ..engine.generate_spec import ParameterError
from ..model import InputError, PRESETS, canonical, resolve
from ..package import PNG_FILES, PackageError, verify as verify_package
from .suggest import suggest

PACKAGE_ID = re.compile(r"[0-9a-f]{64}")
# The request the page opens with; identical to examples/double_r3.json.
EXAMPLE = {"type": "double", "outer_mm": [463, 586], "lattice_per_leaf": [2, 4], "preset": "hanok_A3_portrait_R3"}
# Shortcuts for common rear-picture sheets; any size the schema allows is accepted.
PICTURE_SIZES = {"A4": [210, 297], "A3": [297, 420], "A2": [420, 594]}
CHECK_FIELDS = ("rule_id", "name", "message", "status", "expected", "actual", "tolerance", "targets")
ZIP_EPOCH = 315532800  # 1980-01-01, the earliest date a ZIP entry can hold
# Drawings are 3600-4400 px wide; the package screen shows them through small copies.
THUMB_SIZE = (480, 1920)
THUMB_CACHE = 120
# Input group that shows an error: first by the request field it names, then by rule.
FIELD_GROUPS = {"type": "type", "hinge_side": "type", "outer_mm": "size", "inner_mm": "size",
                "artwork": "artwork", "lattice_per_leaf": "lattice", "preset": "preset",
                "picture": "picture", "stock_mm": "stock"}
RULE_GROUPS = {"input.type": "type", "input.hinge_side": "type", "input.size_basis": "size",
               "input.preset": "preset", "input.preset_type": "preset", "input.picture": "picture",
               "input.stock_thickness": "stock", "opening.positive_size": "size",
               "picture.fits_width": "picture", "picture.fits_height": "picture",
               "lattice.positive_gap": "lattice", "leaf.aspect_ratio": "size",
               "hardware.reference_spacing": "size", "nesting.part_fits_stock": "stock",
               "nesting.board_width": "stock",
               # A frame-type design: the panel group holds the size, the thickness, the cover,
               # the fit and the spacer, so every rule about them points there. The two conflicts
               # point at the field that has to go instead.
               "input.artwork": "artwork", "input.preset_artwork": "preset",
               "input.artwork_picture": "picture", "artwork.covers_inner": "artwork",
               "artwork.cover_hides_edge": "artwork", "artwork.back_member_width": "artwork",
               "artwork.depth_within_stock": "artwork"}


def where(rule_id, details):
    field = details.get("field") if isinstance(details, dict) else None
    if isinstance(field, str):
        group = FIELD_GROUPS.get(re.split(r"[.\[]", field, maxsplit=1)[0])
        if group:
            return group
    return RULE_GROUPS.get(rule_id, "request")


def failure(rule_id, message, details=None, **extra):
    """The CLI error shape plus the input group the page should mark."""
    details = details if details is not None else {}
    return dict(status="FAIL", rule_id=rule_id, message=message, details=details,
                where=where(rule_id, details), **extra)


def app_version():
    try:
        return metadata.version("hanok-window-generator")
    except metadata.PackageNotFoundError:
        return None


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def size_of(params):
    """Both size bases of a resolved design; the inner opening is outer - 2 x frame member."""
    frame = params["frame"]
    member, outer = frame["member_width"], [frame["outer_width"], frame["outer_height"]]
    size = params.get("size") or dict(basis="outer", requested_mm=outer)  # 0.1.0 packages
    inner = list(size["requested_mm"]) if size["basis"] == "inner" else [v - 2 * member for v in outer]
    return dict(basis=size["basis"], requested_mm=list(size["requested_mm"]), outer_mm=outer,
                inner_mm=inner, frame_member_mm=member)


def assembly(params, derived):
    """Front view rectangles in engine coordinates (mm, Y up), straight from build_parts."""
    parts = generate_spec.build_parts(derived)
    picture = None
    if params["picture"]["enabled"]:
        pic = params["picture"]
        w, h = pic["sheet_width"], pic["sheet_height"]
        x0, y0 = derived["picture_x0"], derived["picture_y0"]
        rw, rh = derived["picture_region_w"], derived["picture_region_h"]
        # Centred in the region exactly as builder.configure places PICX, PICY. The
        # builder only ever runs in a job's worker process (hash seed 0, time limit).
        sx, sy = x0 + (rw - w) / 2, y0 + (rh - h) / 2
        picture = dict(size_mm=[w, h], margin_mm=pic["region_margin"],
                       region=[x0, y0, x0 + rw, y0 + rh], sheet=[sx, sy, sx + w, sy + h])
    art, artwork = params.get("artwork"), None
    if art:
        # The panel sits behind the fixed frame, inside the back frame the parts list already
        # carries (B01, B02). Its rectangle is measured the way the builder draws it.
        x0, y0 = derived["artwork_x0"], derived["artwork_y0"]
        w, h = art["sheet_width"], art["sheet_height"]
        artwork = dict(size_mm=[w, h], sheet=[x0, y0, x0 + w, y0 + h],
                       cover_mm=art["cover"], fit_mm=art["fit"], spacer_mm=art["spacer"],
                       thickness_mm=art["thickness"], back_frame_member_mm=derived["back_member"],
                       back_frame_opening_mm=[derived["back_inner_w"], derived["back_inner_h"]])
    return dict(width=derived["board_w"], height=derived["board_h"],
                parts=[dict(id=q.part_id, kind=q.kind, family=q.family, group=q.group, axis=q.axis,
                            rect=[q.x0, q.y0, q.x1, q.y1]) for q in parts],
                leaves=[dict(group=leaf.group, side=leaf.side, hinge_stile=leaf.hinge_stile,
                             handle_stile=leaf.handle_stile) for leaf in formats.leaves(params)],
                picture=picture, artwork=artwork)


def nesting(params, spec):
    """Stock layout from the spec: each part as [x0, y0, x1, y1] on the board (Y up)."""
    stock, kinds = params["stock"], params["part_kinds"]
    margin = stock["edge_margin"]
    x0, y0, x1, y1 = spec["derived"]["nesting_bounds"]
    return dict(stock_mm=[stock["length"], stock["width"], stock["thickness"]], margin_mm=margin,
                parts=[dict(id=p["part_id"], kind=p["kind"], family=kinds[p["kind"]]["family"],
                            rect=[p["nest_x"], p["nest_y"], p["nest_x"] + p["length"], p["nest_y"] + p["width"]])
                       for p in spec["parts"]],
                bounds=[x0, y0, x1, y1], used_mm=[x1 - x0, y1 - y0],
                usable_mm=[stock["length"] - 2 * margin, stock["width"] - 2 * margin])


def created_at(folder):
    # A package is sealed in its staging folder and published by one rename.
    return datetime.fromtimestamp(folder.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")


def read_summary(package_id, folder):
    params = read_json(folder / "design_parameters.json")
    report = read_json(folder / "validation_report.json")
    manifest = read_json(folder / "package_manifest.json")
    window, lattice, picture, stock = params["window"], params["lattice"], params["picture"], params["stock"]
    art = params.get("artwork")  # only a frame-type package has one
    return dict(package_id=package_id, created=created_at(folder), revision=params["revision"],
                type=window["type"], hinge_side=window.get("hinge_side"), preset=window.get("preset", "standard_v1"),
                size=size_of(params), lattice_per_leaf=[lattice["vertical_per_leaf"], lattice["horizontal_per_leaf"]],
                picture=dict(size_mm=[picture["sheet_width"], picture["sheet_height"]],
                             margin_mm=picture["region_margin"]) if picture["enabled"] else None,
                artwork=dict(size_mm=[art["sheet_width"], art["sheet_height"]], thickness_mm=art["thickness"],
                             cover_mm=art["cover"], fit_mm=art["fit"], spacer_mm=art["spacer"]) if art else None,
                stock_mm=[stock["length"], stock["width"], stock["thickness"]],
                parts=report["parts_total"], pockets=report["nominal_pockets_total"],
                dogbones=report["dogbone_reliefs_total"],
                checks=dict(passed=report["checks_passed"], total=len(report["checks"])),
                validation_status=report["status"], manufacturing_status=manifest["manufacturing_status"],
                file_count=len(manifest["files"]))


def format_mm(value):
    return str(int(value)) if float(value).is_integer() else repr(float(value))


def zip_name(summary, package_id):
    """Folder inside the ZIP, readable without the id: type, size basis and size, lattice."""
    try:
        kind = summary["type"] if summary["type"] == "double" else f"single-{summary['hinge_side']}"
        width, height = map(format_mm, summary["size"]["requested_mm"])
        bars = "x".join(map(str, summary["lattice_per_leaf"]))
        return f"hanok_{kind}_{summary['size']['basis']}_{width}x{height}_{bars}_{package_id[:8]}"
    except (KeyError, TypeError, ValueError):
        return f"hanok_{package_id[:8]}"


class Service:
    """Reads the output folder; only jobs.run_job ever writes to it."""

    def __init__(self, output):
        self.root = Path(output).resolve()
        self._summaries = {}
        self._lock = threading.Lock()
        self._meta = None
        self._thumbs = OrderedDict()
        self._thumb_lock = threading.Lock()

    def meta(self):
        if self._meta is None:
            self._meta = self._describe()
        return self._meta

    def _describe(self):
        root = files("hanok_generator")
        schema = json.loads(root.joinpath("request.schema.json").read_text(encoding="utf-8"))
        preset_file = json.loads(root.joinpath("presets/r3_parameters.json").read_text(encoding="utf-8"))
        # Each preset is described by asking the model, so the page never restates its rules.
        presets = []
        for name in PRESETS:
            accepted = []
            for kind, extra in (("double", {}), ("single", {"hinge_side": "left"})):
                try:
                    accepted.append((kind, resolve(dict(type=kind, outer_mm=[463, 586], lattice_per_leaf=[0, 0],
                                                        preset=name, **extra))))
                except InputError:
                    pass
            design = accepted[0][1]
            stock = design.parameters["stock"]
            presets.append(dict(id=name, types=[kind for kind, _ in accepted], picture=design.request["picture"],
                                min_leaf_ratio=design.parameters["leaf"]["min_height_to_width_ratio"],
                                stock_mm=design.request["stock_mm"], edge_margin_mm=stock["edge_margin"],
                                part_gap_mm=stock["part_gap"]))
        defaults = resolve(dict(type="double", outer_mm=[463, 586], lattice_per_leaf=[0, 0],
                                picture=dict(size_mm=PICTURE_SIZES["A3"]))).request
        props = schema["properties"]
        picture = props["picture"]["oneOf"][1]["properties"]
        artwork = props["artwork"]["properties"]

        def span(item):
            return [item["minimum"], item["maximum"]]

        return dict(engine_version=ENGINE_VERSION, app_version=app_version(), output=str(self.root),
                    example=copy.deepcopy(EXAMPLE), presets=presets, default_preset=defaults["preset"],
                    stock_mm=defaults["stock_mm"], picture_margin_mm=defaults["picture"]["margin_mm"],
                    picture_sizes=PICTURE_SIZES, frame_member_mm=preset_file["frame"]["member_width"],
                    # The panel defaults come from the schema, so the form and the tools show the
                    # values resolve() fills in when a request leaves them out.
                    artwork_defaults={key: artwork[key]["default"]
                                      for key in ("thickness_mm", "cover_mm", "fit_mm", "spacer_mm")},
                    relief_radius_mm=preset_file["machining"]["relief_radius"],
                    limits=dict(size_mm=span(props["outer_mm"]["items"]),
                                lattice=span(props["lattice_per_leaf"]["items"]),
                                picture_mm=span(picture["size_mm"]["items"]), margin_mm=span(picture["margin_mm"]),
                                stock_mm=[span(item) for item in props["stock_mm"]["prefixItems"]],
                                artwork_mm=span(artwork["size_mm"]["items"]),
                                artwork_fields={key: span(artwork[key])
                                                for key in ("thickness_mm", "cover_mm", "fit_mm", "spacer_mm")}),
                    schema=schema)

    def preview(self, data):
        """Resolve and lay out a request in this process. Only a build writes and re-reads the DXF."""
        try:
            design = resolve(data)
        except InputError as exc:
            return 422, failure(exc.rule_id, exc.message, exc.details, stage="input")
        params = design.parameters
        body = dict(revision=params["revision"], request=design.request, size=size_of(params))
        # The field the request gave its size in; suggestions come back in the same one.
        size_key = next((key for key in ("inner_mm", "artwork") if key in design.request), "outer_mm")
        try:
            derived = generate_spec.derive(params)
        except ParameterError as exc:
            return 422, {**failure(exc.rule_id, str(exc), exc.details, stage="geometry",
                                   suggestion=suggest(params, exc, size_key)), **body}
        body["assembly"] = assembly(params, derived)
        try:
            spec = generate_spec.build(params)
        except ParameterError as exc:
            # Layout limits leave the front view valid, so the page can still draw it.
            return 422, {**failure(exc.rule_id, str(exc), exc.details, stage="nesting",
                                   suggestion=suggest(params, exc, size_key)), **body}
        return 200, dict(status="RESOLVED_NOT_DXF_VALIDATED", **body, derived=spec["derived"],
                         nesting=nesting(params, spec), same_revision=self.same_revision(params["revision"]))

    def folder(self, package_id):
        """The published folder of a package id, or None. Only 64 lowercase hex digits are accepted."""
        if not isinstance(package_id, str) or not PACKAGE_ID.fullmatch(package_id):
            return None
        path = self.root / "packages" / package_id
        return path if path.is_dir() and not path.is_symlink() else None

    def latest(self):
        try:
            value = read_json(self.root / "latest.json")["package_id"]
        except (OSError, ValueError, KeyError, TypeError):
            return None
        return value if isinstance(value, str) and PACKAGE_ID.fullmatch(value) else None

    def summary(self, package_id):
        cached = self._summaries.get(package_id)
        if cached is not None:
            return cached
        folder = self.folder(package_id)
        if folder is None:
            return None
        try:
            value = read_summary(package_id, folder)
        except (OSError, ValueError, KeyError, TypeError):
            return dict(package_id=package_id, created=created_at(folder), error="패키지 파일을 읽을 수 없습니다.")
        # Content-addressed folders never change, so a summary stays valid.
        with self._lock:
            self._summaries[package_id] = value
        return value

    def packages(self):
        """Published packages, newest first, and the id that latest.json points to."""
        try:
            names = [e.name for e in os.scandir(self.root / "packages")
                     if PACKAGE_ID.fullmatch(e.name) and e.is_dir(follow_symlinks=False)]
        except FileNotFoundError:
            names = []
        items = [s for s in map(self.summary, names) if s]
        items.sort(key=lambda s: (s["created"], s["package_id"]), reverse=True)
        return dict(latest=self.latest(), packages=items)

    def same_revision(self, revision):
        return [s["package_id"] for s in self.packages()["packages"] if s.get("revision") == revision]

    def _manifest(self, package_id):
        """Folder and manifest of a published package whose file rows hash to its id."""
        folder = self.folder(package_id)
        if folder is None:
            return None
        try:
            manifest = read_json(folder / "package_manifest.json")
            identity = hashlib.sha256(canonical(manifest["files"]).encode()).hexdigest()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise PackageError(f"Invalid package: {exc}") from exc
        if identity != package_id:
            raise PackageError("The manifest does not hash to the package id")
        return folder, manifest

    @staticmethod
    def _checked(folder, row):
        """Bytes of one manifest row, refused unless its size and SHA-256 still match."""
        path = folder / row["path"]
        try:
            inside = path.resolve().is_relative_to(folder.resolve()) and not path.is_symlink()
            data = path.read_bytes() if inside else b""
        except OSError as exc:
            raise PackageError(f"Unreadable file: {row['path']}") from exc
        if not inside or len(data) != row["bytes"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise PackageError(f"Changed file: {row['path']}")
        return data

    def package(self, package_id):
        """Summary, file list, all checks, pending items and the submitted request of one package."""
        found = self._manifest(package_id)
        if found is None:
            return None
        folder, manifest = found
        try:
            report = read_json(folder / "validation_report.json")
            resolved = read_json(folder / "resolved_parameters.json")
            return dict(self.summary(package_id), latest=self.latest() == package_id,
                        files=[dict(path=r["path"], bytes=r["bytes"], sha256=r["sha256"]) for r in manifest["files"]],
                        manifest_bytes=(folder / "package_manifest.json").stat().st_size,
                        validation=dict(checks=[{k: c.get(k) for k in CHECK_FIELDS} for c in report["checks"]],
                                        pending=report.get("pending", [])),
                        request=read_json(folder / "design_request.json"),
                        normalized_request=resolved.get("request"), provenance=resolved.get("provenance"),
                        drawings=self._drawing_sizes(folder, manifest))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise PackageError(f"Invalid package: {exc}") from exc

    @staticmethod
    def _drawing_sizes(folder, manifest):
        from PIL import Image  # reads the PNG header only; no pixels are decoded
        listed = {row["path"] for row in manifest["files"]}
        sizes = {}
        for name in PNG_FILES:
            if name in listed:
                with Image.open(folder / name) as image:
                    sizes[name] = list(image.size)
        return sizes

    def thumbnail(self, package_id, name):
        """A small PNG of one of the five drawings, made in memory from the checked original."""
        if name not in PNG_FILES:
            return None
        cached = self._thumbs.get((package_id, name))
        if cached is not None:
            return cached
        found = self._manifest(package_id)
        if found is None:
            return None
        folder, manifest = found
        row = next((r for r in manifest["files"] if r["path"] == name), None)
        if row is None:
            return None
        from PIL import Image
        # One drawing at a time: a 4400 x 5540 original takes about 70 MB while it is open.
        with self._thumb_lock:
            with Image.open(io.BytesIO(self._checked(folder, row))) as original:
                image = original if original.mode in ("RGB", "RGBA", "L") else original.convert("RGB")
                image.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
                buffer = io.BytesIO()
                image.save(buffer, "PNG", optimize=True)
            self._thumbs[(package_id, name)] = data = buffer.getvalue()
            while len(self._thumbs) > THUMB_CACHE:
                self._thumbs.popitem(last=False)
        return data

    def package_file(self, package_id, name):
        """(bytes, file name) of one file the manifest lists, or None if it lists no such file."""
        found = self._manifest(package_id)
        if found is None:
            return None
        folder, manifest = found
        if name == "package_manifest.json":
            return (folder / name).read_bytes(), name
        row = next((r for r in manifest["files"] if r["path"] == name), None)
        return None if row is None else (self._checked(folder, row), name.rsplit("/", 1)[-1])

    def package_zip(self, package_id):
        """The whole package as one ZIP built in memory; every file is checked on the way in."""
        found = self._manifest(package_id)
        if found is None:
            return None
        folder, manifest = found
        top = zip_name(self.summary(package_id), package_id)
        stamp = time.localtime(max(folder.stat().st_mtime, ZIP_EPOCH + 86400))[:6]
        entries = [(row["path"], self._checked(folder, row)) for row in manifest["files"]]
        entries.append(("package_manifest.json", (folder / "package_manifest.json").read_bytes()))
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, data in entries:
                info = zipfile.ZipInfo(f"{top}/{name}", date_time=stamp)
                info.compress_type = zipfile.ZIP_STORED if name.endswith(".png") else zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, data)
        return buffer.getvalue(), top + ".zip"

    def verify(self, package_id):
        """package.verify, read-only, plus the check that the folder name is the package id."""
        folder = self.folder(package_id)
        if folder is None:
            return None
        try:
            result = verify_package(folder)
        except PackageError as exc:
            return dict(status="FAIL", rule_id="package.integrity", message=str(exc), package_id=package_id)
        if result["package_id"] != package_id:
            return dict(status="FAIL", rule_id="package.integrity", package_id=package_id,
                        message="폴더 이름과 매니페스트의 package_id가 다릅니다.")
        return result
