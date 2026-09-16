"""Values that clear a design rule, found by asking the engine again.

Each suggestion changes one input at a time: a lattice bar count, one side of the window, the
picture, the artwork panel, or the stock board. The engine's own derive() and build() decide
whether a value clears the rule, so no rule is restated here. Window sizes come back in the
request's basis (outer_mm, inner_mm or artwork) as whole millimetres rounded the safe way,
picture and panel sizes in tenths of a millimetre.
A suggestion clears only the rule it answers; the next check may name another one.
"""
from __future__ import annotations

import copy
import math

from ..engine import generate_spec
from ..engine.generate_spec import ParameterError

SIZE_LIMIT = 3000  # the largest outer size a request may give (request.schema.json)


def _raised(params, rule_id, spec=False):
    """The engine's error for rule_id on these parameters, or None once it is not reported."""
    try:
        (generate_spec.build if spec else generate_spec.derive)(params)
    except ParameterError as exc:
        return exc if exc.rule_id == rule_id else None
    return None


def _changed(params, change):
    trial = copy.deepcopy(params)
    change(trial)
    return trial


def lattice_counts(params, exc):
    """Largest bar count per closed axis that clears the engine's own gap rule."""
    found = {}
    # details["horizontal"] is the gap between vertical bars, so it closes when there are too
    # many vertical bars; details["vertical"] likewise.
    for count, gap in (("vertical_per_leaf", "horizontal"), ("horizontal_per_leaf", "vertical")):
        if exc.details[gap] > 0:
            continue
        trial = copy.deepcopy(params)
        for n in range(params["lattice"][count] - 1, -1, -1):
            trial["lattice"][count] = n
            try:
                generate_spec.derive(trial)
            except ParameterError as again:
                if again.rule_id == "lattice.positive_gap" and again.details[gap] <= 0:
                    continue
            found[count] = n
            break
    return found


def _isolate(params):
    # The picture and lattice rules come before the leaf proportion and the hinge spacing. While
    # a search shrinks the window they would fail first and hide the rule being searched.
    params["picture"]["enabled"] = False
    params["lattice"].update(vertical_per_leaf=0, horizontal_per_leaf=0)


def _side(params, rule_id, axis, grow, *, spec=False, detail=None, isolate=False):
    """Whole-mm outer width (axis 0) or height (axis 1) nearest the current one that clears rule_id
    when only that side changes, or None if no size within the request limit does."""
    key = ("outer_width", "outer_height")[axis]
    panel = ("sheet_width", "sheet_height")[axis]

    def trial(value):
        def change(t):
            t["frame"][key] = value
            if t.get("artwork"):
                # resolve() builds the frame around the panel, so a trial that moves one without
                # the other breaks artwork.covers_inner. That rule would then be raised instead
                # of the one being searched for, and every trial would read as cleared.
                t["artwork"][panel] = value - 2 * t["frame"]["member_width"] + 2 * t["artwork"]["cover"]
            if isolate:
                _isolate(t)
        return _changed(params, change)

    def clears(value):
        exc = _raised(trial(value), rule_id, spec)
        return exc is None or (detail is not None and exc.details[detail] > 0)

    current = params["frame"][key]
    start, end = (math.ceil(current), SIZE_LIMIT) if grow else (math.floor(current), 1)
    if (grow and start > SIZE_LIMIT) or (not grow and start < 1):
        return None
    if clears(start):
        value = start
    elif not clears(end):
        return None
    else:
        low, high = (start, end) if grow else (end, start)
        low_clears = clears(low)
        while high - low > 1:
            middle = (low + high) // 2
            if clears(middle) == low_clears:
                low = middle
            else:
                high = middle
        value = low if low_clears else high
    if not grow:
        # Shrinking runs into the rules that come first (the opening, or any geometry rule for a
        # layout rule). A value that only moves the error to one of them is no suggestion.
        try:
            generate_spec.derive(trial(value))
        except ParameterError as exc:
            if spec or exc.rule_id == "opening.positive_size":
                return None
    return value


def _tenth(value):
    value = math.floor(value * 10 + 1e-9) / 10
    return int(value) if value.is_integer() else value


def _picture(params, exc, axis):
    """Largest sheet side, or margin, that fits the picture region the engine measured."""
    pic = params["picture"]
    side = ("sheet_width", "sheet_height")[axis]
    available, margin = exc.details["available"], pic["region_margin"]
    options = ((("width_at_most", "height_at_most")[axis], side, _tenth(available - 2 * margin), 0.1),
               ("margin_at_most", "region_margin", _tenth((available - pic[side]) / 2), 0))
    found = {}
    for label, name, value, least in options:
        if value >= least and _raised(_changed(params, lambda t: t["picture"].update({name: value})),
                                      exc.rule_id) is None:
            found[label] = value
    return found


# Frame-type rules whose values the page can offer. artwork.covers_inner is not among them: a
# request names the panel and the engine derives the frame from it, so it holds by construction
# and can only be broken by editing the parameters directly.
ARTWORK_RULES = ("artwork.cover_hides_edge", "artwork.back_member_width", "artwork.depth_within_stock")
# The smallest value the schema accepts for each panel field.
ARTWORK_LEAST = {"thickness": 0.1, "cover": 0.1, "fit": 0.0, "spacer": 0.0}


def _artwork(params, exc):
    """Panel values that clear one frame-type rule, each on its own."""
    art, details = params["artwork"], exc.details
    if exc.rule_id == "artwork.cover_hides_edge":
        wanted = {"fit_at_most": ("fit", _tenth(art["cover"] - 0.1)),
                  "cover_at_least": ("cover", _tenth(art["fit"]) + 0.1)}
    elif exc.rule_id == "artwork.back_member_width":
        short = details["minimum"] - details["back_member_width"]
        wanted = {"cover_at_most": ("cover", details["cover_at_most"]),
                  "fit_at_most": ("fit", _tenth(art["fit"] - short))}
    else:
        available = details["available"]
        wanted = {"thickness_at_most": ("thickness", _tenth(available - art["spacer"])),
                  "spacer_at_most": ("spacer", _tenth(available - art["thickness"]))}

    def change(name, value):
        def apply(trial):
            trial["artwork"][name] = value
            if name == "cover":
                # resolve() builds the frame around the panel, so a different cover is a
                # different outer frame. Without this the trial would answer for a window the
                # request can never produce.
                member = trial["frame"]["member_width"]
                for key, side in (("outer_width", "sheet_width"), ("outer_height", "sheet_height")):
                    trial["frame"][key] = trial["artwork"][side] - 2 * value + 2 * member
        return apply

    found = {}
    for label, (name, value) in wanted.items():
        if value >= ARTWORK_LEAST[name] and _raised(_changed(params, change(name, value)), exc.rule_id) is None:
            found[label] = value
    return found


def _stock(params, exc):
    """Smallest stock length or width that holds the part, or the layout, the engine reported."""
    stock, details = params["stock"], exc.details
    if exc.rule_id == "nesting.part_fits_stock":
        wanted = {name: math.ceil(stock[name] + details["part"][i] - details["usable"][i])
                  for i, name in enumerate(("length", "width")) if details["part"][i] > details["usable"][i]}
    else:
        wanted = {"width": math.ceil(stock["width"] + details["top"] - details["limit"])}
    found = {}
    for name, value in wanted.items():
        if value <= SIZE_LIMIT and _raised(_changed(params, lambda t: t["stock"].update({name: value})),
                                           exc.rule_id, spec=True) is None:
            found[f"{name}_at_least"] = value
    return found


def suggest(params, exc, size_key):
    """Values that clear the rule of exc, keyed by the request field to change, or None.

    {"vertical_per_leaf": 4, "outer_mm": {"width_at_least": 306}} means: four vertical bars per
    leaf, or an outer width of at least 306 mm, each on its own."""
    rule, details = exc.rule_id, exc.details
    member = params["frame"]["member_width"]
    # outer = inner + 2 x member, and outer = panel - 2 x cover + 2 x member, so a suggested
    # outer size is turned back into the field the request used.
    shift = (2 * member if size_key == "inner_mm" else
             2 * (member - params["artwork"]["cover"]) if size_key == "artwork" else 0)
    found = {}

    def side(axis, grow, **options):
        value = _side(params, rule, axis, grow, **options)
        if value is not None:
            label = ("width", "height")[axis] + ("_at_least" if grow else "_at_most")
            found.setdefault(size_key, {})[label] = value - shift

    if rule == "lattice.positive_gap":
        found.update(lattice_counts(params, exc))
        for axis, gap in ((0, "horizontal"), (1, "vertical")):
            if details[gap] <= 0:
                side(axis, True, detail=gap)
    elif rule == "opening.positive_size":
        for axis, gap in ((0, "width"), (1, "height")):
            if details[gap] <= 0:
                side(axis, True, detail=gap)
    elif rule == "leaf.aspect_ratio":
        side(0, False, isolate=True)
        side(1, True, isolate=True)
    elif rule == "hardware.reference_spacing":
        side(1, True, isolate=True)
    elif rule in ("picture.fits_width", "picture.fits_height"):
        axis = 0 if rule == "picture.fits_width" else 1
        found["picture"] = _picture(params, exc, axis)
        side(axis, True)
    elif rule in ("nesting.part_fits_stock", "nesting.board_width"):
        found["stock_mm"] = _stock(params, exc)
        if rule == "nesting.part_fits_stock":
            side(0, False, spec=True)
            side(1, False, spec=True)
    elif rule in ARTWORK_RULES:
        found["artwork"] = _artwork(params, exc)
        if rule == "artwork.depth_within_stock":
            # The board itself is the other way out of this one.
            thickness = details["required"]
            if thickness <= 60 and _raised(_changed(params, lambda t: t["stock"].update(thickness=thickness)),
                                           rule) is None:
                found["stock_mm"] = {"thickness_at_least": thickness}
    return {key: value for key, value in found.items() if value != {}} or None
