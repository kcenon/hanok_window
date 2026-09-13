"""Tools for LLM agents: the operations a model may call, their input schemas and English guidance.

Every tool runs the code the web page and the CLI run: model.resolve and the engine's pure
geometry for the pre-check, jobs.run_job in an isolated worker for builds, and the read-only
package index for results. A design built through a model therefore gets the same package_id as
the same design built from the page or the CLI, and the builder never loads in the calling process.
Definitions are exported for MCP, OpenAI (Chat Completions and Responses) and Anthropic tool use.
Text for the model is English; the documentation for people stays Korean.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
import struct

from ..jobs import JobError, run_job
from ..model import PRESETS, canonical
from ..package import PNG_FILES, PackageError
from ..web.builds import failed_build
from ..web.service import Service, format_mm

MAX_ARGUMENTS = 64 * 1024  # the request limit of the web API and of `hanok-window --input`
PACKAGE_REF = re.compile(r"[0-9a-f]{8,64}")
DRAWINGS = dict(zip(("nesting", "joinery", "assembly", "opening", "pockets"), PNG_FILES))
DESIGN_TOOLS = ("check_design", "build_package")
# Key order of examples/*.json and the web form. design_request.json sorts its keys, so the order
# is only for reading; the package_id depends on which keys appear and how numbers are written.
ORDER = ("type", "hinge_side", "outer_mm", "inner_mm", "lattice_per_leaf", "preset", "picture", "stock_mm")
EXAMPLES = {
    "double_r3": {"type": "double", "outer_mm": [463, 586], "lattice_per_leaf": [2, 4], "preset": "hanok_A3_portrait_R3"},
    "double_inner_r3": {"type": "double", "inner_mm": [383, 506], "lattice_per_leaf": [2, 4],
                        "preset": "hanok_A3_portrait_R3"},
    "single_right": {"type": "single", "hinge_side": "right", "outer_mm": [420, 900], "lattice_per_leaf": [2, 6]},
    "single_empty": {"type": "single", "hinge_side": "left", "outer_mm": [420, 900], "lattice_per_leaf": [0, 0]},
    "double_600_800": {"type": "double", "outer_mm": [600, 800], "lattice_per_leaf": [2, 4]},
}
# How to fix each rule, in words a model can act on. Numbers come from the result's `details`.
HINTS = {
    "input.object": "Send the design as a JSON object.",
    "input.too_large": "Keep the arguments under 64 KiB.",
    "input.unknown_fields": "Remove the fields listed in details.fields; only the fields of the input schema are accepted.",
    "input.schema_version": "Leave schema_version out or set it to 1.",
    "input.type": "Set type to \"single\" (one leaf) or \"double\" (two leaves).",
    "input.hinge_side": ("A single window needs hinge_side \"left\" or \"right\". A double window must not have "
                         "hinge_side: both of its leaves hinge on the outer frame."),
    "input.size_basis": "Give exactly one of outer_mm (finished outer frame) or inner_mm (clear opening inside the frame).",
    "input.vector": "details.field must be an array of details.required numbers.",
    "input.number": "Use finite numbers; lattice bar counts must be whole numbers.",
    "input.range": ("details.field is outside details.minimum to details.maximum. With inner_mm the derived outer "
                    "size (inner + 2 frame members) must stay within 3000 mm as well."),
    "input.preset": "Use one of details.supported, or leave preset out for standard_v1.",
    "input.preset_type": "hanok_A3_portrait_R3 is for double windows only; leave preset out for a single window.",
    "input.picture": "picture is left out (preset default), null (no picture) or {\"size_mm\": [w, h], \"margin_mm\": 10}.",
    "input.stock_thickness": "The thickness, the third value of stock_mm, must be 5 to 60 mm.",
    "opening.positive_size": ("The window is too small to leave an opening inside the frame and leaf members "
                              "(details.width, details.height in mm). Make the window larger."),
    "lattice.positive_gap": ("Too many bars: the gap between bars is zero or negative. details.horizontal is the gap "
                             "between vertical bars and details.vertical the gap between horizontal bars, in mm. "
                             "Use fewer bars (suggestion gives the largest count that fits) or a larger window."),
    "leaf.aspect_ratio": ("Under this preset each leaf must be at least details.minimum times taller than wide "
                          "(now details.measured). Make the window narrower or taller, or use standard_v1."),
    "hardware.reference_spacing": ("The leaf is too short for two reference hinges (details.leaf_height mm; it must "
                                   "be more than details.required_greater_than mm). Make the window taller."),
    "picture.fits_width": ("The picture plus both side margins (details.required mm) is wider than the picture "
                           "region (details.available mm). Use a smaller picture or margin, or a wider window."),
    "picture.fits_height": ("The picture plus top and bottom margins (details.required mm) is taller than the "
                            "picture region (details.available mm). Use a smaller picture or margin, or a taller window."),
    "nesting.part_fits_stock": ("Part details.part_id [length, width] is larger than the usable board (details.usable "
                                "mm). Use a longer or wider stock_mm, or a smaller window. Only one board is supported."),
    "nesting.board_width": ("The parts do not fit on one stock board: the layout reaches details.top mm and the limit "
                            "is details.limit mm. Use a wider stock_mm, fewer bars or a smaller window."),
    "geometry.validation": ("The saved DXF failed the checks in validation.failed. With "
                            "distinct_machining_regions_separated the bars are too close for the pocket reliefs: use "
                            "fewer bars or a larger window, and run check_design again."),
    "job.timeout": "The build did not finish in time. Try once more; if it happens again, report failure_report.",
    "job.failed": "The build stopped with an error. Try once more; if it happens again, report failure_report.",
    "worker.stopped": "The build worker stopped without a result. Try once more; if it happens again, report failure_report.",
    "package.integrity": "A file of this package changed after it was built. Build the design again for an intact package.",
    "package.not_found": "No package in the output folder has this id. Call list_packages to see the ids.",
    "package.ambiguous": "Several packages start with this prefix. Give more characters of the package_id.",
    "tool.arguments": "Fix the arguments to match the tool's input schema.",
    "tool.failed": "The tool hit an unexpected error. Report the message; retrying will not help.",
}

DESCRIBE = ("What this generator makes and how to call it: window types, the two size bases, presets and their "
            "rules, input limits, defaults, example requests and what each status means. Call it once before "
            "designing.")
CHECK = ("Pre-check a window design without writing any file. Validates the request, derives the frame, leaf and "
         "lattice geometry and lays every part out on the stock board. Returns the resolved sizes, leaf and lattice "
         "cell sizes and board usage, or the violated rule_id with its numbers, a fix hint and, for closed lattice "
         "gaps, the largest bar count that fits. Passing does not mean the saved DXF passed: build_package runs "
         "those checks.")
BUILD = ("Build the complete CNC package for a design: DXF, five PNG drawings, four CSV manifests and a validation "
         "report. An isolated worker saves the DXF, re-reads it and runs 67 checks; this takes a few seconds. The "
         "same request always yields the same package_id, and existing packages are never overwritten. If a check "
         "fails, the result lists the failed checks. Manufacturing stays PENDING: no package should go to a machine "
         "before trial cuts.")
LIST = ("List the packages already built in the output folder, newest first, with window type, size, lattice, "
        "preset and check counts.")
GET = ("Show one built package: its request, sizes, check totals and any failed checks, the pending manufacturing "
       "items, its files and the sizes of its drawings.")
VERIFY = ("Re-hash every file of a built package against its manifest (read-only) and report PASS or the first "
          "changed or missing file.")
DRAWING = ("Return one drawing of a built package as a PNG image at most 480 px wide: nesting (all parts on the "
           "stock board), joinery (joint details), assembly (front view with outer and inner sizes), opening (plan "
           "of the leaves swinging open) or pockets (close-ups of every pocket).")


@dataclass(frozen=True)
class Tool:
    name: str
    title: str
    description: str
    read_only: bool
    schema: dict


@dataclass
class ToolResult:
    """What a tool returns: JSON data for the model, PNG images as (mime type, bytes), and whether it failed."""
    data: dict
    is_error: bool = False
    images: list = field(default_factory=list)


def _object(required=(), **properties):
    schema = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = list(required)
    return schema


def _pair(kind, low, high, description):
    return {"type": "array", "items": {"type": kind, "minimum": low, "maximum": high},
            "minItems": 2, "maxItems": 2, "description": description}


def design_schema(meta):
    """The request as a tool input: the fields of request.schema.json without oneOf, if/then or prefixItems,
    which several function-calling APIs refuse. resolve() still enforces every rule of the full schema."""
    member = format_mm(meta["frame_member_mm"])
    ratio = format_mm(next(p["min_leaf_ratio"] for p in meta["presets"] if p["id"] == "hanok_A3_portrait_R3"))
    return _object(
        ["type", "lattice_per_leaf"],
        type={"type": "string", "enum": ["single", "double"],
              "description": ("single: one leaf hinged on one side. double: two leaves meeting in the middle, each "
                              "hinged on the outer frame.")},
        hinge_side={"type": "string", "enum": ["left", "right"],
                    "description": "Hinge side of a single window. Leave it out for a double window."},
        outer_mm=_pair("number", 1, 3000, "Finished outer frame [width, height] in mm. Give either outer_mm or inner_mm."),
        inner_mm=_pair("number", 1, 3000, (f"Clear opening inside the fixed frame [width, height] in mm; the outer "
                                           f"frame is inner + 2 x {member} mm. Give either inner_mm or outer_mm.")),
        lattice_per_leaf=_pair("integer", 0, 32, ("Lattice bars per leaf [vertical, horizontal]; 0 is allowed in "
                                                  "either direction. The R3 window uses [2, 4].")),
        preset={"type": "string", "enum": list(PRESETS),
                "description": (f"Leave out for {meta['default_preset']}. hanok_A3_portrait_R3 follows the R3 "
                                f"portrait window: double only, each leaf at least {ratio} times taller than wide, "
                                "an A3 picture by default.")},
        picture={"type": ["object", "null"], "additionalProperties": False, "required": ["size_mm"],
                 "description": ("Rear picture sheet centred behind the frame. Leave out for the preset's default, "
                                 "null for no picture."),
                 "properties": {
                     "size_mm": _pair("number", 0.1, 3000, "Sheet [width, height] in mm; A3 portrait is [297, 420]."),
                     "margin_mm": {"type": "number", "minimum": 0, "maximum": 500,
                                   "description": f"Least clearance on every side in mm, default "
                                                  f"{format_mm(meta['picture_margin_mm'])}."}}},
        stock_mm={"type": "array", "items": {"type": "number", "minimum": 1, "maximum": 3000},
                  "minItems": 3, "maxItems": 3,
                  "description": (f"Stock board [length, width, thickness] in mm, default {meta['stock_mm']}; "
                                  "thickness 5 to 60. Every part must fit on this one board.")})


def canonical_request(args, meta):
    """The request as the web form and examples/*.json write it: defaults left out, whole numbers as integers.
    design_request.json keeps what was submitted and the package_id covers it, so this keeps one package_id
    per design whichever interface built it. Mistakes are kept, for resolve() to name."""
    def whole(value):
        return int(value) if isinstance(value, float) and value.is_integer() else value

    def numbers(value):
        return [whole(v) for v in value] if isinstance(value, list) else value

    request = {key: args[key] for key in ORDER if key in args}
    request.update((key, value) for key, value in args.items() if key not in ORDER)
    for key in ("outer_mm", "inner_mm", "lattice_per_leaf", "stock_mm"):
        if key in request:
            request[key] = numbers(request[key])
    preset = request.get("preset", meta["default_preset"])
    if request.get("preset") == meta["default_preset"]:
        del request["preset"]
    if isinstance(request.get("picture"), dict):
        picture = dict(request["picture"])
        if "size_mm" in picture:
            picture["size_mm"] = numbers(picture["size_mm"])
        picture["margin_mm"] = whole(picture.get("margin_mm", meta["picture_margin_mm"]))
        request["picture"] = picture
    defaults = {p["id"]: p["picture"] for p in meta["presets"]}
    if "picture" in request and preset in defaults and canonical(request["picture"]) == canonical(defaults[preset]):
        del request["picture"]
    if request.get("stock_mm") == meta["stock_mm"]:
        del request["stock_mm"]
    if request.get("schema_version") == 1:
        del request["schema_version"]
    return request


def _png_size(data):
    return list(struct.unpack(">II", data[16:24]))  # width and height from the IHDR chunk


BRIEF = ("package_id", "created", "type", "hinge_side", "preset", "size", "lattice_per_leaf", "picture", "checks",
         "validation_status", "manufacturing_status", "error")
DETAIL = ("package_id", "created", "revision", "type", "hinge_side", "preset", "size", "lattice_per_leaf", "picture",
          "stock_mm", "parts", "pockets", "dogbones", "checks", "validation_status", "manufacturing_status")


class Toolbox:
    """The tools bound to one output folder. call() reports a tool's own failures as results; it never raises
    for them, so one bad request cannot stop an agent loop."""

    def __init__(self, output, *, timeout=120):
        self.service = Service(output)
        self.timeout = timeout
        meta = self.service.meta()
        design = design_schema(meta)
        package = {"type": "string", "pattern": "^[0-9a-f]{8,64}$",
                   "description": ("package_id from build_package or list_packages; a unique prefix of 8 or more "
                                   "characters is enough.")}
        self.tools = {tool.name: tool for tool in (
            Tool("describe_generator", "Describe the generator", DESCRIBE, True, _object()),
            Tool("check_design", "Check a design", CHECK, True, design),
            Tool("build_package", "Build a CNC package", BUILD, False, design),
            Tool("list_packages", "List built packages", LIST, True,
                 _object(limit={"type": "integer", "minimum": 1, "maximum": 100,
                                "description": "How many of the newest packages to return, default 20."})),
            Tool("get_package", "Show a package", GET, True, _object(["package_id"], package_id=package)),
            Tool("verify_package", "Verify package files", VERIFY, True, _object(["package_id"], package_id=package)),
            Tool("get_drawing", "Look at a drawing", DRAWING, True,
                 _object(["package_id", "drawing"], package_id=package,
                         drawing={"type": "string", "enum": list(DRAWINGS), "description": "Which drawing to return."})),
        )}

    def definitions(self, fmt="mcp"):
        """Tool definitions in one of FORMATS, ready to hand to a model API or an MCP client."""
        try:
            convert = FORMATS[fmt]
        except KeyError:
            raise ValueError(f"unknown format {fmt!r}; use one of: {', '.join(FORMATS)}") from None
        return [convert(tool) for tool in self.tools.values()]

    def call(self, name, arguments=None):
        """Run one tool. An unknown name raises KeyError; everything else comes back as a ToolResult."""
        tool = self.tools[name]
        arguments = {} if arguments is None else arguments
        if not isinstance(arguments, dict):
            return self._error("tool.arguments", "Arguments must be a JSON object.")
        try:
            size = len(canonical(arguments).encode())
        except (TypeError, ValueError):
            return self._error("input.number", "Arguments must be plain JSON; NaN and Infinity are not allowed.")
        if size > MAX_ARGUMENTS:
            return self._error("input.too_large", f"The arguments are {size} bytes; the limit is {MAX_ARGUMENTS}.")
        if name not in DESIGN_TOOLS:  # a design's unknown fields are named by resolve() instead
            unknown = sorted(set(arguments) - set(tool.schema["properties"]))
            if unknown:
                return self._error("tool.arguments", f"Unknown arguments: {', '.join(unknown)}.", dict(unknown=unknown))
        try:
            return getattr(self, "_" + name)(arguments)
        except PackageError as exc:
            return self._error("package.integrity", str(exc))
        except Exception as exc:  # a defect is reported to the model instead of ending its session
            return self._error("tool.failed", f"{type(exc).__name__}: {exc}")

    def _error(self, rule_id, message, details=None, **extra):
        return ToolResult(dict(status="FAIL", rule_id=rule_id, message=message, details=details or {},
                               hint=HINTS.get(rule_id, ""), **extra), is_error=True)

    def _refused(self, body, request):
        """A pre-check failure without the drawing geometry, plus the fix hint."""
        keep = {k: body[k] for k in ("status", "rule_id", "message", "details", "where", "stage", "suggestion", "size")
                if k in body}
        return ToolResult(dict(keep, hint=HINTS.get(body.get("rule_id"), ""), request=request), is_error=True)

    def _package_id(self, args):
        """(full package_id, None) for a full id or a unique prefix, else (None, error result)."""
        ref = args.get("package_id")
        if not isinstance(ref, str) or not PACKAGE_REF.fullmatch(ref):
            return None, self._error("tool.arguments", "package_id must be 8 to 64 lowercase hexadecimal characters.",
                                     dict(field="package_id"))
        if len(ref) == 64:
            if self.service.folder(ref):
                return ref, None
            return None, self._error("package.not_found", f"No package {ref}.", dict(package_id=ref))
        matches = [s["package_id"] for s in self.service.packages()["packages"] if s["package_id"].startswith(ref)]
        if len(matches) == 1:
            return matches[0], None
        rule = "package.ambiguous" if matches else "package.not_found"
        return None, self._error(rule, f"{len(matches)} packages start with {ref}.", dict(prefix=ref, matches=matches[:10]))

    def _describe_generator(self, args):
        meta = self.service.meta()
        return ToolResult(dict(
            generator=dict(name="hanok-window-generator", version=meta["app_version"], engine=meta["engine_version"]),
            makes=("CNC packages for Korean hanok lattice windows: one DXF with every part laid out on one stock "
                   "board, five PNG drawings, four CSV manifests and a validation report that re-reads the saved DXF "
                   "(67 checks)."),
            workflow=["check_design: validate a request without writing files; fix the rule it reports with hint "
                      "and suggestion.",
                      "build_package: build the same request (a few seconds). The same request always gives the same "
                      "package_id.",
                      "get_drawing, get_package, verify_package: look at and inspect the result."],
            units=("Millimetres. Sizes are [width, height]; lattice_per_leaf is [vertical, horizontal] bars per leaf; "
                   "stock_mm is [length, width, thickness]."),
            size_basis=dict(outer_mm="finished outer frame",
                            inner_mm=("clear opening inside the fixed frame; outer = inner + 2 x "
                                      f"{format_mm(meta['frame_member_mm'])} mm")),
            presets=[dict(id=p["id"], window_types=p["types"], default_picture=p["picture"],
                          min_leaf_height_to_width=p["min_leaf_ratio"]) for p in meta["presets"]],
            defaults=dict(preset=meta["default_preset"], stock_mm=meta["stock_mm"],
                          picture_margin_mm=meta["picture_margin_mm"]),
            limits=meta["limits"], picture_sizes_mm=meta["picture_sizes"], examples=EXAMPLES,
            statuses=dict(
                RESOLVED_NOT_DXF_VALIDATED="check_design passed; only build_package re-reads and checks the saved DXF.",
                PASS="build_package: every check on the saved DXF passed.",
                PENDING=("Manufacturing is not approved: hinges and screws, backing and mounting, stock, fit "
                         "tolerances, CAM and workholding need real-world confirmation and trial cuts.")),
            output_folder=str(self.service.root)))

    def _check_design(self, args):
        request = canonical_request(args, self.service.meta())
        code, body = self.service.preview(request)
        if code != 200:
            return self._refused(body, request)
        derived, nest = body["derived"], body["nesting"]
        return ToolResult(dict(
            status=body["status"], request=request, resolved_request=body["request"], revision=body["revision"],
            size=body["size"], leaf_mm=derived["leaf_width_height"], leaf_opening_mm=derived["leaf_opening"],
            lattice=dict(per_leaf=derived["lattice_per_leaf"], cell_mm=derived["lattice_cell"],
                         crossings_total=derived["crossings_total"]),
            picture=body["assembly"]["picture"], totals=derived["totals"], part_counts=derived["part_counts"],
            board=dict(stock_mm=nest["stock_mm"], usable_mm=nest["usable_mm"], used_mm=nest["used_mm"]),
            same_design_packages=body["same_revision"],
            next="build_package with the same request builds the package and runs every check on the saved DXF."))

    def _build_package(self, args):
        request = canonical_request(args, self.service.meta())
        code, body = self.service.preview(request)
        if code != 200:
            return self._refused(body, request)
        before = {s["package_id"] for s in self.service.packages()["packages"]}
        try:
            result = run_job(request, self.service.root, timeout=self.timeout)
        except JobError as exc:
            failed = failed_build(exc.result)
            return ToolResult(dict(failed, hint=HINTS.get(failed["rule_id"], ""), request=request), is_error=True)
        package_id = result["package_id"]
        detail = self.service.package(package_id)
        return ToolResult(dict(
            status=result["status"], package_id=package_id, already_existed=package_id in before,
            folder=result["package"], request=request, checks=detail["checks"], parts=result["parts"],
            pockets=result["pockets"], dogbones=result["dogbones"],
            manufacturing_status=result["manufacturing_status"], pending=detail["validation"]["pending"],
            drawings=list(DRAWINGS),
            next="get_drawing shows a drawing, for example drawing \"assembly\" for the front view."))

    def _list_packages(self, args):
        limit = args.get("limit", 20)
        if type(limit) is not int or not 1 <= limit <= 100:
            return self._error("tool.arguments", "limit must be a whole number from 1 to 100.", dict(field="limit"))
        index = self.service.packages()
        return ToolResult(dict(output_folder=str(self.service.root), latest=index["latest"],
                               total=len(index["packages"]),
                               packages=[{k: s[k] for k in BRIEF if k in s} for s in index["packages"][:limit]]))

    def _get_package(self, args):
        package_id, error = self._package_id(args)
        if error:
            return error
        detail = self.service.package(package_id)
        if detail is None:
            return self._error("package.not_found", f"No package {package_id}.", dict(package_id=package_id))
        return ToolResult(dict(
            {k: detail[k] for k in DETAIL if k in detail},
            folder=str(self.service.folder(package_id)), latest=detail["latest"],
            failed_checks=[c for c in detail["validation"]["checks"] if c.get("status") != "PASS"],
            pending=detail["validation"]["pending"], request=detail["request"],
            files=[row["path"] for row in detail["files"]],
            drawings={key: detail["drawings"].get(name) for key, name in DRAWINGS.items()}))

    def _verify_package(self, args):
        package_id, error = self._package_id(args)
        if error:
            return error
        result = self.service.verify(package_id)
        if result is None:
            return self._error("package.not_found", f"No package {package_id}.", dict(package_id=package_id))
        if result.get("status") != "PASS":
            return ToolResult(dict(result, hint=HINTS["package.integrity"]), is_error=True)
        return ToolResult(result)

    def _get_drawing(self, args):
        package_id, error = self._package_id(args)
        if error:
            return error
        drawing = args.get("drawing")
        if drawing not in DRAWINGS:
            return self._error("tool.arguments", f"drawing must be one of: {', '.join(DRAWINGS)}.",
                               dict(field="drawing", allowed=list(DRAWINGS)))
        data = self.service.thumbnail(package_id, DRAWINGS[drawing])
        if data is None:
            return self._error("package.not_found", f"Package {package_id} has no drawing {drawing}.",
                               dict(package_id=package_id, drawing=drawing))
        width, height = _png_size(data)
        return ToolResult(dict(package_id=package_id, drawing=drawing, file=DRAWINGS[drawing], width=width,
                               height=height, note="A reduced copy; the package holds the full-size PNG."),
                          images=[("image/png", data)])


def _mcp(tool):
    return dict(name=tool.name, title=tool.title, description=tool.description, inputSchema=tool.schema,
                annotations=dict(title=tool.title, readOnlyHint=tool.read_only, destructiveHint=False,
                                 idempotentHint=True, openWorldHint=False))


def _openai(tool):  # Chat Completions; also Ollama, vLLM, LM Studio and other OpenAI-compatible servers
    return dict(type="function", function=dict(name=tool.name, description=tool.description,
                                               parameters=tool.schema, strict=False))


def _openai_responses(tool):
    return dict(type="function", name=tool.name, description=tool.description, parameters=tool.schema, strict=False)


def _anthropic(tool):
    return dict(name=tool.name, description=tool.description, input_schema=tool.schema)


FORMATS = {"mcp": _mcp, "openai": _openai, "openai-responses": _openai_responses, "anthropic": _anthropic}
