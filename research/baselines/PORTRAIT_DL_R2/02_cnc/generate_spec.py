#!/usr/bin/env python3
"""Derive the complete CNC design spec from design_parameters.json.

design_parameters.json is the single source of truth. This module expands those
few numbers into the full part list, joint pockets, corner reliefs and one-board
nesting, then writes design_spec.json. build_portrait_double_leaf.py imports the
same derivation, so the DXF writer and the geometry validator cannot drift apart
the way a hand-maintained spec plus a hand-written check formula can.

Run:
    python generate_spec.py                       # write design_spec.json
    python generate_spec.py --compare OTHER.json  # diff against another spec
    python generate_spec.py --stdout              # print without writing

Nothing here emits toolpaths, feeds, speeds or G-code. All values are nominal
millimetres with zero fit allowance; coupons decide the real tolerance.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARAMS_FILE = HERE / 'design_parameters.json'
SPEC_FILE = HERE / 'design_spec.json'

# A member is either a vertical (V) or a horizontal (H) run in the assembled
# front view. Every joint in this design is a half lap between one V and one H
# member of the same assembly group, so the axis drives face assignment too:
# V members keep face A toward the front, H members are flipped after cutting.
FACE_OF_AXIS = {'V': 'FRONT', 'H': 'BACK'}
JOINT_OF_FAMILIES = {
    ('FRAME', 'FRAME'): 'J1',
    ('SASH', 'SASH'): 'J2',
    ('LATTICE', 'LATTICE'): 'J3',
    ('SASH', 'LATTICE'): 'J4',
    ('LATTICE', 'SASH'): 'J4',
}


@dataclass
class Part:
    """One wooden member, both as an assembled rectangle and as nested stock."""

    part_id: str
    kind: str
    axis: str
    family: str
    group: str
    anchor: str  # 'near' or 'far'; picks which end of the member is local u=0
    x0: float
    y0: float
    x1: float
    y1: float
    thickness: float
    nest_x: float = 0.0
    nest_y: float = 0.0

    @property
    def length(self) -> float:
        return self.y1 - self.y0 if self.axis == 'V' else self.x1 - self.x0

    @property
    def width(self) -> float:
        return self.x1 - self.x0 if self.axis == 'V' else self.y1 - self.y0

    @property
    def face_a(self) -> str:
        return FACE_OF_AXIS[self.axis]

    @property
    def transform(self) -> list:
        """Affine [a, b, d, e, tx, ty] mapping local (u, v) to assembly (X, Y).

        The determinant sign encodes the flip: positive keeps face A at the
        front, negative means the part is turned over during assembly.
        """
        if self.axis == 'V':
            if self.anchor == 'near':  # X = v + x0,  Y = y1 - u
                return [0, 1, -1, 0, self.x0, self.y1]
            return [0, -1, 1, 0, self.x1, self.y0]  # X = x1 - v,  Y = u + y0
        if self.anchor == 'near':  # X = x1 - u,  Y = v + y0
            return [-1, 0, 0, 1, self.x1, self.y0]
        return [1, 0, 0, -1, self.x0, self.y1]  # X = u + x0,  Y = y1 - v

    def to_local(self, x: float, y: float) -> tuple:
        """Inverse of `transform`, used to pull assembled joints back to stock."""
        if self.axis == 'V':
            if self.anchor == 'near':
                return self.y1 - y, x - self.x0
            return y - self.y0, self.x1 - x
        if self.anchor == 'near':
            return self.x1 - x, y - self.y0
        return x - self.x0, self.y1 - y

    def local_rect(self, x0: float, y0: float, x1: float, y1: float) -> tuple:
        """Map an assembly-space rectangle into this part's local (u, v) box."""
        ua, va = self.to_local(x0, y0)
        ub, vb = self.to_local(x1, y1)
        return min(ua, ub), min(va, vb), max(ua, ub), max(va, vb)


@dataclass
class Derived:
    """Every dimension implied by design_parameters.json, computed once."""

    params: dict
    values: dict = field(default_factory=dict)

    def __getitem__(self, key):
        return self.values[key]


def derive(params: dict) -> Derived:
    """Expand the parameter file into the dimensions the rest of the package uses."""
    frame, leaf, lat = params['frame'], params['leaf'], params['lattice']
    clear, pic, stock = params['clearance'], params['picture'], params['stock']

    fw = frame['member_width']
    board_w, board_h = frame['outer_width'], frame['outer_height']
    inner_w, inner_h = board_w - 2 * fw, board_h - 2 * fw

    n = leaf['count']
    sm = leaf['member_width']
    leaf_h = inner_h - 2 * clear['frame_to_leaf']
    leaf_w = (inner_w - 2 * clear['frame_to_leaf']
              - (n - 1) * clear['leaf_to_leaf']) / n
    open_w, open_h = leaf_w - 2 * sm, leaf_h - 2 * sm

    bw, lap = lat['bar_width'], lat['end_lap_length']
    nv, nh = lat['vertical_per_leaf'], lat['horizontal_per_leaf']

    region_w = board_w - 2 * (fw + clear['frame_to_leaf'] + sm)
    region_h = board_h - 2 * (fw + clear['frame_to_leaf'] + sm)

    v = dict(
        frame_member=fw, board_w=board_w, board_h=board_h,
        inner_w=inner_w, inner_h=inner_h,
        leaf_count=n, leaf_member=sm, leaf_w=leaf_w, leaf_h=leaf_h,
        leaf_y0=fw + clear['frame_to_leaf'], leaf_y1=fw + clear['frame_to_leaf'] + leaf_h,
        open_w=open_w, open_h=open_h,
        bar_width=bw, end_lap=lap, n_vertical=nv, n_horizontal=nh,
        vertical_gap=(open_w - nv * bw) / (nv + 1),
        horizontal_gap=(open_h - nh * bw) / (nh + 1),
        crossings_per_leaf=nv * nh, crossings_total=nv * nh * n,
        picture_region_w=region_w, picture_region_h=region_h,
        picture_x0=fw + clear['frame_to_leaf'] + sm,
        picture_y0=fw + clear['frame_to_leaf'] + sm,
        pocket_depth=params['machining']['pocket_depth'],
        relief_radius=params['machining']['relief_radius'],
        thickness=stock['thickness'],
        part_lengths={
            'F01': board_h, 'F02': board_w,
            'S01': leaf_h, 'S02': leaf_w,
            'L01': open_h + 2 * lap, 'L02': open_w + 2 * lap,
        },
        part_widths={'F01': fw, 'F02': fw, 'S01': sm, 'S02': sm, 'L01': bw, 'L02': bw},
        part_counts={'F01': 2, 'F02': 2, 'S01': 2 * n, 'S02': 2 * n,
                     'L01': nv * n, 'L02': nh * n},
    )

    # Consistency relations that a hand-edited parameter file could break.
    assert region_w == pic['sheet_width'] + 2 * pic['region_margin'], (
        'picture region width must equal sheet width plus twice the margin')
    assert region_h == pic['sheet_height'] + 2 * pic['region_margin'], (
        'picture region height must equal sheet height plus twice the margin')
    assert region_h == open_h, 'picture region height must match the leaf opening height'
    assert v['vertical_gap'] > 0 and v['horizontal_gap'] > 0, 'lattice bars do not fit'
    # Growing the frame sideways can keep every relation above intact and still
    # flatten the leaves toward squares, so the portrait proportion is a bound too.
    ratio, min_ratio = leaf_h / leaf_w, leaf['min_height_to_width_ratio']
    assert ratio >= min_ratio, (
        f'leaf height / width ({leaf_h:g} / {leaf_w:g} = {ratio:.4f}) is below the '
        f'required minimum {min_ratio}')
    # Every joint here is a half lap cut to one depth from face A on both mating
    # members. Their retained halves only meet flush when the depth is exactly
    # half the stock; any other depth leaves the two halves overlapping or short.
    depth, thick = params['machining']['pocket_depth'], stock['thickness']
    assert 2 * depth == thick, (
        f'half-lap joints need pocket_depth ({depth}) to be exactly half the stock '
        f'thickness ({thick}); {2 * depth} != {thick}')
    assert 0 < lap <= sm, (
        f'lattice end lap ({lap}) must fit inside the sash member width ({sm})')
    assert lap <= v['open_w'] and lap <= v['open_h'], 'end lap longer than the opening'
    # A round cutter cannot leave a square inside corner, so the relief circle has
    # to be at least as large as the tool it is meant to clear.
    tool_r = params['machining']['tool_diameter'] / 2
    assert v['relief_radius'] >= tool_r, (
        f'relief_radius ({v["relief_radius"]}) is smaller than the tool radius ({tool_r})')
    return Derived(params, v)


def leaf_bounds(d: Derived, i: int) -> tuple:
    """Assembly-space rectangle of leaf `i`, counted left to right from zero."""
    p = d.params
    x0 = p['frame']['member_width'] + p['clearance']['frame_to_leaf'] + i * (
        d['leaf_w'] + p['clearance']['leaf_to_leaf'])
    return x0, d['leaf_y0'], x0 + d['leaf_w'], d['leaf_y1']


def opening_bounds(d: Derived, i: int) -> tuple:
    x0, y0, x1, y1 = leaf_bounds(d, i)
    sm = d['leaf_member']
    return x0 + sm, y0 + sm, x1 - sm, y1 - sm


def bar_offsets(d: Derived, axis: str) -> list:
    """Lattice bar centre offsets measured from the leaf opening origin.

    Bars are evenly spaced with equal gaps at both ends, so `n` bars of width
    `bw` across a span `s` leave gaps of (s - n*bw)/(n+1). The validator rebuilds
    the expected pocket rectangles from these same offsets.
    """
    n = d['n_vertical'] if axis == 'V' else d['n_horizontal']
    gap = d['vertical_gap'] if axis == 'V' else d['horizontal_gap']
    bw = d['bar_width']
    return [(i + 1) * gap + i * bw + bw / 2 for i in range(n)]


def group_name(d: Derived, i: int) -> str:
    if d['leaf_count'] == 2:
        return 'LEFT_LEAF' if i == 0 else 'RIGHT_LEAF'
    return f'LEAF_{i + 1}'


def build_parts(d: Derived) -> list:
    """Place all members in assembly space, in canonical part-id order."""
    p = d.params
    fw, sm, bw, lap = d['frame_member'], d['leaf_member'], d['bar_width'], d['end_lap']
    W, H, t = d['board_w'], d['board_h'], d['thickness']
    parts = []

    def add(pid, kind, axis, group, anchor, rect):
        parts.append(Part(pid, kind, axis, p['part_kinds'][kind]['family'], group,
                          anchor, *rect, thickness=t))

    add('F01-1', 'F01', 'V', 'FIXED', 'near', (0, 0, fw, H))
    add('F01-2', 'F01', 'V', 'FIXED', 'far', (W - fw, 0, W, H))
    add('F02-1', 'F02', 'H', 'FIXED', 'near', (0, 0, W, fw))
    add('F02-2', 'F02', 'H', 'FIXED', 'far', (0, H - fw, W, H))

    n = d['leaf_count']
    for i in range(n):
        lx0, ly0, lx1, ly1 = leaf_bounds(d, i)
        add(f'S01-{2 * i + 1}', 'S01', 'V', group_name(d, i), 'near', (lx0, ly0, lx0 + sm, ly1))
        add(f'S01-{2 * i + 2}', 'S01', 'V', group_name(d, i), 'far', (lx1 - sm, ly0, lx1, ly1))
    for i in range(n):
        lx0, ly0, lx1, ly1 = leaf_bounds(d, i)
        add(f'S02-{2 * i + 1}', 'S02', 'H', group_name(d, i), 'near', (lx0, ly0, lx1, ly0 + sm))
        add(f'S02-{2 * i + 2}', 'S02', 'H', group_name(d, i), 'far', (lx0, ly1 - sm, lx1, ly1))

    nv, nh = d['n_vertical'], d['n_horizontal']
    vx, hy = bar_offsets(d, 'V'), bar_offsets(d, 'H')
    for i in range(n):
        ox0, oy0, ox1, oy1 = opening_bounds(d, i)
        for j, off in enumerate(vx):
            cx = ox0 + off
            add(f'L01-{i * nv + j + 1}', 'L01', 'V', group_name(d, i), 'far',
                (cx - bw / 2, oy0 - lap, cx + bw / 2, oy1 + lap))
    for i in range(n):
        ox0, oy0, ox1, oy1 = opening_bounds(d, i)
        for k, off in enumerate(hy):
            cy = oy0 + off
            add(f'L02-{i * nh + k + 1}', 'L02', 'H', group_name(d, i), 'far',
                (ox0 - lap, cy - bw / 2, ox1 + lap, cy + bw / 2))
    return parts


def build_joints(d: Derived, parts: list) -> list:
    """Every half lap is a vertical member crossing a horizontal member.

    Two members of the same assembly group that overlap in the front view must
    share that volume, so each overlap becomes one pocket per member: the
    front-facing member loses its front half, the flipped one loses its back
    half, and the retained 10 mm halves interlock.
    """
    verticals = [q for q in parts if q.axis == 'V']
    horizontals = [q for q in parts if q.axis == 'H']
    joints = []
    for a in verticals:
        for b in horizontals:
            if a.group != b.group:
                continue
            x0, y0 = max(a.x0, b.x0), max(a.y0, b.y0)
            x1, y1 = min(a.x1, b.x1), min(a.y1, b.y1)
            if x1 - x0 <= 0 or y1 - y0 <= 0:
                continue
            joint = JOINT_OF_FAMILIES[(a.family, b.family)]
            joints.append(dict(joint=joint, box=(x0, y0, x1, y1), members=(a, b),
                               seat_family='SASH' if joint == 'J4' else None))
    return joints


def build_pockets(d: Derived, parts: list, joints: list) -> tuple:
    """Assign pocket ids per part and pair ids in canonical walk order.

    End laps come before interior pockets, each block ordered by ascending u, so
    the schedule reads the way an operator scans a stick of wood end to end.
    """
    by_part = {q.part_id: [] for q in parts}
    for jn in joints:
        entry = []
        for member in jn['members']:
            u0, v0, u1, v1 = member.local_rect(jn['box'][0], jn['box'][1],
                                               jn['box'][2], jn['box'][3])
            rec = dict(part=member, joint=jn['joint'], u0=u0, v0=v0, u1=u1, v1=v1,
                       seat=jn['seat_family'] == member.family)
            entry.append(rec)
        entry[0]['mate'], entry[1]['mate'] = entry[1], entry[0]
        for rec in entry:
            by_part[rec['part'].part_id].append(rec)

    order = {q.part_id: q for q in parts}
    for pid, recs in by_part.items():
        L = order[pid].length
        recs.sort(key=lambda r: (0 if r['u0'] <= 0 or r['u1'] >= L else 1, r['u0']))
        for idx, rec in enumerate(recs, 1):
            rec['feature_id'] = f'{pid}-P{idx:02d}'

    pair_no = 0
    for q in parts:
        for rec in by_part[q.part_id]:
            if 'pair' in rec:
                continue
            pair_no += 1
            rec['pair'] = rec['mate']['pair'] = f'PAIR-{pair_no:02d}'

    pockets = []
    for q in parts:
        for rec in by_part[q.part_id]:
            pockets.append(dict(
                feature_id=rec['feature_id'], part_id=q.part_id, joint=rec['joint'],
                seat=rec['seat'], u0=rec['u0'], v0=rec['v0'], u1=rec['u1'], v1=rec['v1'],
                depth=d['pocket_depth'], face_a=q.face_a, joint_pair_id=rec['pair'],
                mate_feature_id=rec['mate']['feature_id'],
                mate_part_id=rec['mate']['part'].part_id))
    return pockets, by_part


def build_dogbones(d: Derived, parts: list, pockets: list) -> list:
    """A relief is needed wherever a pocket corner is trapped inside the part.

    Corners that sit on a part edge are reachable because the cutter can run out
    into the waste; a corner with both coordinates strictly inside the outline
    cannot be cut square by a round tool, so it gets an R-radius circle unioned
    with the pocket.
    """
    dims = {q.part_id: (q.length, q.width) for q in parts}
    r = d['relief_radius']
    out = []
    for pk in pockets:
        L, B = dims[pk['part_id']]
        interior = [(u, v)
                    for u in (pk['u0'], pk['u1']) if 0 < u < L
                    for v in (pk['v0'], pk['v1']) if 0 < v < B]
        interior.sort()
        for suffix, (u, v) in zip(('L', 'R'), interior):
            out.append(dict(feature_id=f"{pk['feature_id']}-DB-{suffix}",
                            parent_pocket=pk['feature_id'], part_id=pk['part_id'],
                            center_u=u, center_v=v, radius=r, depth=d['pocket_depth']))
        if interior and len(interior) != 2:
            raise ValueError(f"unexpected relief count on {pk['feature_id']}")
    return out


def nest(d: Derived, parts: list) -> None:
    """First-fit-decreasing shelf packing, scoped per (family, member width).

    Keeping a family on its own shelves means an operator lifting 10 mm sticks
    off the bed finds the frame, sash and lattice groups in separate bands. All
    lengths stay parallel to +X so every part follows the board grain.
    """
    stock = d.params['stock']
    margin, gap = stock['edge_margin'], stock['part_gap']
    x_limit = stock['length'] - margin
    shelves = []  # each: dict(key, y, width, cursor)
    y_cursor = margin

    def family_order(q):
        return (-q.length, q.part_id)

    seen_keys = []
    for q in parts:
        key = (q.family, q.width)
        if key not in seen_keys:
            seen_keys.append(key)
    for key in seen_keys:
        members = sorted((q for q in parts if (q.family, q.width) == key), key=family_order)
        for q in members:
            for shelf in shelves:
                if shelf['key'] != key or shelf['cursor'] + q.length > x_limit:
                    continue
                q.nest_x, q.nest_y = shelf['cursor'], shelf['y']
                shelf['cursor'] += q.length + gap
                break
            else:
                shelf = dict(key=key, y=y_cursor, width=q.width, cursor=margin)
                shelves.append(shelf)
                y_cursor += q.width + gap
                q.nest_x, q.nest_y = shelf['cursor'], shelf['y']
                shelf['cursor'] += q.length + gap

    top = max(q.nest_y + q.width for q in parts)
    if top > stock['width'] - margin:
        raise ValueError(f'nesting exceeds the board: {top} > {stock["width"] - margin}')


def build(params: dict | None = None) -> dict:
    """Produce the full design spec dictionary from the parameter file."""
    params = params if params is not None else json.loads(
        PARAMS_FILE.read_text(encoding='utf-8'))
    d = derive(params)
    parts = build_parts(d)
    joints = build_joints(d, parts)
    pockets, _ = build_pockets(d, parts, joints)
    dogbones = build_dogbones(d, parts, pockets)
    nest(d, parts)

    counts = d['part_counts']
    if len(parts) != sum(counts.values()):
        raise ValueError('part count mismatch')
    spec = dict(
        revision=params['revision'],
        generated_from='design_parameters.json',
        derived=dict(
            overall_width_height=[d['board_w'], d['board_h']],
            frame_inner=[d['inner_w'], d['inner_h']],
            leaf_width_height=[d['leaf_w'], d['leaf_h']],
            leaf_opening=[d['open_w'], d['open_h']],
            lattice_per_leaf=[d['n_vertical'], d['n_horizontal']],
            lattice_cell=[d['vertical_gap'], d['horizontal_gap']],
            crossings_total=d['crossings_total'],
            picture_region=[d['picture_region_w'], d['picture_region_h']],
            picture_origin=[d['picture_x0'], d['picture_y0']],
            part_lengths=d['part_lengths'], part_widths=d['part_widths'],
            part_counts=counts,
            totals=dict(parts=len(parts), pockets=len(pockets),
                        reliefs=len(dogbones), joint_pairs=len(pockets) // 2),
            nesting_bounds=[min(q.nest_x for q in parts), min(q.nest_y for q in parts),
                            max(q.nest_x + q.length for q in parts),
                            max(q.nest_y + q.width for q in parts)],
        ),
        parts=[dict(part_id=q.part_id, kind=q.kind, length=float(q.length),
                    width=float(q.width), thickness=q.thickness,
                    nest_x=q.nest_x, nest_y=q.nest_y, assembly_group=q.group,
                    face_a=q.face_a, assembly_transform=q.transform) for q in parts],
        pockets=pockets,
        dogbones=dogbones,
    )
    return spec


def compare(spec: dict, other_path: Path) -> int:
    """Report design differences against another spec, ignoring nesting layout."""
    other = json.loads(other_path.read_text(encoding='utf-8'))
    problems = []

    def index(payload, section, key='feature_id'):
        return {row[key]: row for row in payload[section]}

    for section, key, skip in (('parts', 'part_id', {'nest_x', 'nest_y'}),
                               ('pockets', 'feature_id', set()),
                               ('dogbones', 'feature_id', set())):
        mine, theirs = index(spec, section, key), index(other, section, key)
        for missing in sorted(set(theirs) - set(mine)):
            problems.append(f'{section}: {missing} missing from generated spec')
        for extra in sorted(set(mine) - set(theirs)):
            problems.append(f'{section}: {extra} only in generated spec')
        for name in sorted(set(mine) & set(theirs)):
            a, b = mine[name], theirs[name]
            for fld in sorted(set(a) | set(b)):
                if fld in skip or fld not in a or fld not in b:
                    continue
                va, vb = a[fld], b[fld]
                if isinstance(va, list) and isinstance(vb, list):
                    if len(va) != len(vb) or any(abs(p - q) > 1e-9 for p, q in zip(va, vb)):
                        problems.append(f'{section}.{name}.{fld}: {va} != {vb}')
                elif isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                    if abs(va - vb) > 1e-9:
                        problems.append(f'{section}.{name}.{fld}: {va} != {vb}')
                elif va != vb:
                    problems.append(f'{section}.{name}.{fld}: {va!r} != {vb!r}')

    label = f'design content vs {other_path.name}'
    if problems:
        print(f'DIFFER / {label} / {len(problems)} difference(s)')
        for line in problems[:40]:
            print('  ', line)
        if len(problems) > 40:
            print(f'   ... and {len(problems) - 40} more')
        return 1
    print(f'IDENTICAL / {label} / nesting positions excluded by design')
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compare', metavar='SPEC', help='diff design content against another spec')
    ap.add_argument('--stdout', action='store_true', help='print the spec instead of writing it')
    args = ap.parse_args()

    spec = build()
    text = json.dumps(spec, ensure_ascii=False, indent=2) + '\n'
    if args.stdout:
        print(text, end='')
    else:
        SPEC_FILE.write_text(text, encoding='utf-8')
        t = spec['derived']['totals']
        print(f"wrote {SPEC_FILE.name}: {t['parts']} parts / {t['pockets']} pockets / "
              f"{t['reliefs']} reliefs / {t['joint_pairs']} joint pairs")
    return compare(spec, Path(args.compare)) if args.compare else 0


if __name__ == '__main__':
    raise SystemExit(main())
