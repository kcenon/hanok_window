"""Strict public inputs and versioned preset resolution, independent of CAD I/O."""
from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
import copy
import hashlib
import json
import math

from . import __version__ as ENGINE_VERSION

PRESETS = ("standard_v1", "hanok_A3_portrait_R3", "standard_4x8_v1")
# Stock board [length, width, thickness] of a request that gives none.
DEFAULT_STOCK_MM = [1220, 900, 20]
# Presets that lay parts out on a 4 x 8 ft board: its default size, the margin left
# at the board edge and the gap between parts. Other presets keep DEFAULT_STOCK_MM
# and the edge_margin and part_gap of presets/r3_parameters.json.
PRESET_STOCK = {"standard_4x8_v1": dict(stock_mm=[2400, 1200, 20], edge_margin=10, part_gap=12)}
# Fields of a frame-type (액자형) request, each (default, minimum, maximum) in mm: the artwork
# panel thickness, how much of the panel edge the fixed frame covers, the fit clearance around
# the panel inside the back frame, and the procured spacer that holds the panel off the lattice.
ARTWORK_FIELDS = {"thickness_mm": (3, 0.1, 60), "cover_mm": (8, 0.1, 500),
                  "fit_mm": (1, 0, 50), "spacer_mm": (3, 0, 60)}
# A size is given as the finished outer frame (외경), as the clear opening inside the fixed frame
# (내경), or as the artwork panel the frame is built around (화판): request key -> (basis,
# provenance wording).
SIZE_BASES = {"outer_mm": ("outer", "finished outer frame"),
              "inner_mm": ("inner", "fixed-frame inner opening"),
              "artwork": ("artwork", "artwork panel behind the fixed frame")}


class InputError(ValueError):
    def __init__(self, rule_id, message, **details):
        self.rule_id, self.message, self.details = rule_id, message, details
        super().__init__(message)

    def record(self):
        return dict(rule_id=self.rule_id, message=self.message, details=self.details)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _require(ok, rule, message, **details):
    if not ok:
        raise InputError(rule, message, **details)


def _number(value, field, minimum, maximum, integer=False):
    _require(type(value) in (int, float) and (type(value) is int or math.isfinite(value)),
             "input.number", "유한한 숫자를 입력하세요.", field=field)
    _require(not integer or type(value) is int or value.is_integer(),
             "input.number", "창살 개수는 정수여야 합니다.", field=field)
    _require(minimum <= value <= maximum, "input.range", "입력 범위를 벗어났습니다.",
             field=field, actual=value, minimum=minimum, maximum=maximum)
    return int(value) if integer or float(value).is_integer() else value


def _vector(value, field, count, minimum, maximum, integer=False):
    _require(isinstance(value, list) and len(value) == count, "input.vector",
             "배열의 항목 수가 맞지 않습니다.", field=field, required=count)
    return [_number(v, f"{field}[{i}]", minimum, maximum, integer) for i, v in enumerate(value)]


@dataclass(frozen=True)
class ResolvedDesign:
    request: dict
    parameters: dict
    provenance: dict
    input_request: dict


def resolve(data: dict) -> ResolvedDesign:
    _require(type(data) is dict, "input.object", "입력은 JSON 객체여야 합니다.")
    allowed = {"schema_version", "type", "hinge_side", *SIZE_BASES, "lattice_per_leaf", "preset", "picture", "stock_mm"}
    _require(not set(data) - allowed, "input.unknown_fields", "알 수 없는 입력 항목입니다.",
             fields=sorted(set(data) - allowed))
    _require(type(data.get("schema_version", 1)) in (int,float) and data.get("schema_version", 1) == 1,
             "input.schema_version", "지원하는 스키마 버전은 1입니다.")
    kind = data.get("type")
    _require(kind in ("single", "double"), "input.type", "창 형식은 single 또는 double입니다.")
    side = data.get("hinge_side")
    _require((kind == "single" and side in ("left", "right")) or (kind == "double" and "hinge_side" not in data),
             "input.hinge_side", "단문은 left/right 경첩 방향이 필요하고 양문은 바깥쪽 경첩을 사용합니다.")
    given = [key for key in SIZE_BASES if key in data]
    _require(len(given) == 1, "input.size_basis",
             "창 크기는 outer_mm(외경), inner_mm(내경), artwork(화판) 중 하나로만 지정합니다.", fields=given)
    size_key = given[0]
    artwork = None
    if size_key == "artwork":
        artwork = data["artwork"]
        _require(type(artwork) is dict and not set(artwork) - {"size_mm", *ARTWORK_FIELDS},
                 "input.artwork", "화판은 size_mm과 thickness_mm·cover_mm·fit_mm·spacer_mm으로 지정합니다.")
        size = _vector(artwork.get("size_mm"), "artwork.size_mm", 2, 1, 3000)
        artwork = dict(size_mm=size, **{key: _number(artwork.get(key, default), f"artwork.{key}", low, high)
                                        for key, (default, low, high) in ARTWORK_FIELDS.items()})
    else:
        size = _vector(data[size_key], size_key, 2, 1, 3000)
    lattice = _vector(data.get("lattice_per_leaf"), "lattice_per_leaf", 2, 0, 32, True)
    preset = data.get("preset", "standard_v1")
    _require(preset in PRESETS, "input.preset", "지원하지 않는 프리셋입니다.", supported=list(PRESETS))
    _require(preset != "hanok_A3_portrait_R3" or kind == "double", "input.preset_type",
             "R3 프리셋은 세로형 양문 규칙입니다. 단문은 standard_v1을 사용하세요.")
    _require(artwork is None or preset != "hanok_A3_portrait_R3", "input.preset_artwork",
             "R3 프리셋은 A3 그림을 후면 지지판에 두는 규칙입니다. 액자형은 standard_v1이나 standard_4x8_v1을 사용하세요.")
    _require(artwork is None or "picture" not in data, "input.artwork_picture",
             "액자형은 화판이 그림 자리를 대신하므로 picture를 함께 지정하지 않습니다.")
    picture = data.get("picture", {"size_mm": [297, 420], "margin_mm": 10} if preset == "hanok_A3_portrait_R3" else None)
    if picture is not None:
        _require(type(picture) is dict and not set(picture)-{"size_mm", "margin_mm"},
                 "input.picture", "그림은 size_mm과 margin_mm으로 지정합니다.")
        picture = dict(size_mm=_vector(picture.get("size_mm"), "picture.size_mm", 2, 0.1, 3000),
                       margin_mm=_number(picture.get("margin_mm", 10), "picture.margin_mm", 0, 500))
    layout = PRESET_STOCK.get(preset, {})
    stock = _vector(data.get("stock_mm", layout.get("stock_mm", DEFAULT_STOCK_MM)), "stock_mm", 3, 1, 3000)
    _require(5 <= stock[2] <= 60, "input.stock_thickness", "지원하는 원판 두께는 5~60 mm입니다.")
    params = json.loads(files("hanok_generator").joinpath("presets/r3_parameters.json").read_text(encoding="utf-8"))
    # The inner size is the clear opening of the fixed frame, so the engine still
    # receives the outer size: one frame member is added on each side.
    member = params["frame"]["member_width"]
    # The fixed frame is built around the artwork panel: it covers cover_mm of the panel edge on
    # every side, so the clear opening is the panel less two covers.
    outer = (size if size_key == "outer_mm" else
             [v + 2 * member for v in size] if size_key == "inner_mm" else
             [v - 2 * artwork["cover_mm"] + 2 * member for v in size])
    _require(all(0 < v <= 3000 for v in outer), "input.range", "입력에서 유도한 외곽이 입력 범위를 벗어났습니다.",
             field="outer_mm", derived_from=size_key, actual=outer, maximum=3000)
    # An outer-size request normalizes exactly as in 0.1.0, so its revision is kept.
    request = dict(schema_version=1, type=kind, lattice_per_leaf=lattice,
                   preset=preset, picture=picture, stock_mm=stock)
    request[size_key] = artwork if artwork else size
    if side is not None:
        request["hinge_side"] = side
    params["frame"].update(outer_width=outer[0], outer_height=outer[1])
    params["size"] = dict(basis=SIZE_BASES[size_key][0], requested_mm=list(size))
    params["leaf"].update(count=1 if kind == "single" else 2,
                          min_height_to_width_ratio=2.6 if preset == "hanok_A3_portrait_R3" else 0)
    params["lattice"].update(vertical_per_leaf=lattice[0], horizontal_per_leaf=lattice[1])
    params["stock"].update(length=stock[0], width=stock[1], thickness=stock[2])
    params["stock"].update({k: v for k, v in layout.items() if k != "stock_mm"})
    params["machining"]["pocket_depth"] = stock[2] / 2
    params["picture"].update(enabled=picture is not None,
        sheet_width=picture["size_mm"][0] if picture else 0,
        sheet_height=picture["size_mm"][1] if picture else 0,
        region_margin=picture["margin_mm"] if picture else 0)
    if artwork:
        # Only a frame-type request carries these, so every design built so far keeps the
        # parameter file it has always had. The back frame kinds are added for the same reason.
        params["artwork"] = dict(sheet_width=size[0], sheet_height=size[1],
                                 thickness=artwork["thickness_mm"], cover=artwork["cover_mm"],
                                 fit=artwork["fit_mm"], spacer=artwork["spacer_mm"],
                                 mounting="One panel held behind the fixed frame by a back frame cut from the "
                                          "same board. Spacer, backing and fixings are procured separately.")
        params["part_kinds"].update(B01=dict(role="back frame stile", axis="V", family="BACK_FRAME"),
                                    B02=dict(role="back frame rail", axis="H", family="BACK_FRAME"))
        params["nesting"]["families"]["BACK_FRAME"] = ["B01", "B02"]
    params["window"] = dict(type=kind, hinge_side=side, preset=preset)
    params["revision"] = "HANOK_GEN_V1_" + hashlib.sha256(canonical(request).encode()).hexdigest()[:12]
    params["build_date"] = "2026-09-12"  # engine release date, not a volatile build timestamp
    params["title"] = "Hanok window / " + ("double leaf" if kind == "double" else f"single leaf, {side} hinges")
    for field in ("lattice_pattern_decision", "supersedes", "note"):
        params.pop(field, None)
    params["leaf"].pop("note", None)
    derived = {"machining.pocket_depth": "stock.thickness / 2"}
    if size_key == "inner_mm":
        derived["frame.outer_width, frame.outer_height"] = "inner_mm + 2 * frame.member_width"
    if size_key == "artwork":
        derived["frame.outer_width, frame.outer_height"] = ("artwork.size_mm - 2 * artwork.cover_mm "
                                                            "+ 2 * frame.member_width")
        derived["back frame member width"] = "frame.member_width - artwork.cover_mm - artwork.fit_mm"
    return ResolvedDesign(copy.deepcopy(request), params,
        dict(preset=preset, engine=ENGINE_VERSION, units="mm", size_basis=SIZE_BASES[size_key][1],
             user_fields=sorted(data), derived=derived,
             defaults="presets/r3_parameters.json", material_minima_status="PENDING"),copy.deepcopy(data))
