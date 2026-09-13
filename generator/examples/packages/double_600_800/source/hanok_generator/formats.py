"""Leaf topology, reference hardware attachment and swing direction."""
from dataclasses import dataclass


@dataclass(frozen=True)
class LeafFormat:
    index: int
    side: str
    group: str
    hinge_stile: str
    fixed_stile: str
    handle_stile: str
    top_rail: str

    @property
    def angle(self):
        return 90 if self.side == "left" else -90


def leaves(parameters):
    window = parameters["window"]
    sides = ["left", "right"] if window["type"] == "double" else [window["hinge_side"]]
    out = []
    for i, side in enumerate(sides):
        left, right = f"S01-{2*i+1}", f"S01-{2*i+2}"
        out.append(LeafFormat(i, side,
            ("LEFT_LEAF" if i == 0 else "RIGHT_LEAF") if len(sides) == 2 else "LEAF_1",
            left if side == "left" else right,
            "F01-1" if side == "left" else "F01-2",
            right if side == "left" else left, f"S02-{2*i+2}"))
    return out


def title(parameters):
    window = parameters["window"]
    return "DOUBLE LEAF" if window["type"] == "double" else f"SINGLE LEAF / {window['hinge_side'].upper()} HINGES"


def detail_variants(parameters):
    v, h = (parameters["lattice"][k] for k in ("vertical_per_leaf", "horizontal_per_leaf"))
    result = ["J1", "J2"]
    if v and h:
        result.append("J3")
    if v:
        result.append("J4V")
    if h:
        result.append("J4H")
    return result
