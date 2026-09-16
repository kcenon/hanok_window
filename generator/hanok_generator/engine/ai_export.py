"""Write the machining on the board as a legacy Illustrator 8 file, and read one back.

Illustrator 8 is the last plain-text PostScript AI format, and every Illustrator from 8 to
CS6 and later still opens it. The file is written from the entities the DXF already carries,
without reading a font file and without recording a time, a job id or anything else about
the machine, so one design always produces one set of bytes. That is what lets window.ai be
a package file whose hash takes part in the package_id.

Only what lies on the stock board is exported: part outlines, pockets, corner reliefs, part
labels and the hardware marks of the nesting view. The assembly, detail and opening views,
the dimensions and the sheet notes stay out.

Nothing here defines a PostScript procedure. Illustrator reads the prolog comments and
supplies its own procedure set, so the operators below are the ones it already knows.
"""
import math
from pathlib import Path
import re

from .cad_helpers import meta
from .numeric_policy import ARC_CHORD_TOL_MM, LENGTH_TOL_MM, bulge_arc, polyline_arcs

PT_PER_MM = 72/25.4
# Decimals of a point coordinate. Fewer does not survive reading the file back: at 6 decimals
# a vertex returns 2.4e-7 mm away and at 4 decimals 2.5e-5 mm, both past LENGTH_TOL_MM, while
# 7 decimals return 2.4e-8 mm. Each further decimal costs about 6 KB on an R3 board.
DIGITS = 7
# An arc becomes cubic Beziers of at most this sweep, so one circle is twelve pieces. The
# resulting error measures around 1e-13 mm, eight orders below ARC_CHORD_TOL_MM.
MAX_SWEEP = math.pi/6
BOARD_LAYERS = ('BOARD_BOUNDARY', 'CUT_THROUGH', 'DOGBONE', 'PART_ID')
# These carry the same hardware mark in three views; only the one nested on the board belongs here.
NEST_ONLY_LAYERS = ('HINGE_REF', 'LATCH_REF')
DRAWING_ORDER = ('BOARD_BOUNDARY', 'CUT_THROUGH', 'POCKET', 'DOGBONE', 'HINGE_REF', 'LATCH_REF', 'PART_ID')
# Stroke colour as CMYK and layer colour as RGB. A DXF colour index cannot be carried over:
# CUT_THROUGH and PART_ID are index 7, which the ezdxf palette resolves to white, and the
# cutting outlines would be invisible on a white artboard. CMYK rather than RGB because the
# format specification introduces the RGB operators in version 7.0.
INK = {'BOARD_BOUNDARY': ((0, 0, 0, 0.35), (128, 128, 128)),
       'CUT_THROUGH': ((0, 0, 0, 1), (0, 0, 0)),
       'POCKET': ((0, 0.45, 0.9, 0), (255, 127, 0)),
       'DOGBONE': ((0, 0.8, 0, 0), (255, 0, 255)),
       'HINGE_REF': ((0.7, 0, 0.2, 0.1), (0, 160, 190)),
       'LATCH_REF': ((0.7, 0, 0.2, 0.1), (0, 160, 190)),
       'PART_ID': ((0, 0, 0, 1), (0, 0, 0))}
# A stroke font: each glyph is a list of polylines on a 2 x 4 grid, x right and y up. Part
# labels are drawn with it rather than set in a typeface, because reading a font file would
# make the bytes depend on the fonts installed on the machine. Only the characters a part id
# can hold are defined. B and 8, and S and 5, have to stay apart, so no seven-segment shapes.
GLYPHS = {
    '0': [[(0, 0), (2, 0), (2, 4), (0, 4), (0, 0)]],
    '1': [[(0, 3), (1, 4), (1, 0)], [(0, 0), (2, 0)]],
    '2': [[(0, 3.5), (0.5, 4), (1.5, 4), (2, 3.5), (2, 2.5), (0, 0.5), (0, 0), (2, 0)]],
    '3': [[(0, 4), (2, 4), (2, 2), (0, 2)], [(2, 2), (2, 0), (0, 0)]],
    '4': [[(0, 4), (0, 2), (2, 2)], [(2, 4), (2, 0)]],
    '5': [[(2, 4), (0, 4), (0, 2.2), (1.5, 2.2), (2, 1.7), (2, 0.5), (1.5, 0), (0, 0)]],
    '6': [[(2, 4), (0.5, 4), (0, 3.5), (0, 0.5), (0.5, 0), (1.5, 0), (2, 0.5), (2, 1.5), (1.5, 2), (0, 2)]],
    '7': [[(0, 4), (2, 4), (1, 0)]],
    '8': [[(0, 0), (2, 0), (2, 4), (0, 4), (0, 0)], [(0, 2), (2, 2)]],
    '9': [[(2, 2), (0.5, 2), (0, 2.5), (0, 3.5), (0.5, 4), (1.5, 4), (2, 3.5), (2, 0.5), (1.5, 0), (0, 0)]],
    'B': [[(0, 0), (0, 4), (1.5, 4), (2, 3.5), (2, 2.5), (1.5, 2), (0, 2)],
          [(1.5, 2), (2, 1.5), (2, 0.5), (1.5, 0), (0, 0)]],
    'F': [[(2, 4), (0, 4), (0, 0)], [(0, 2), (1.5, 2)]],
    'L': [[(0, 4), (0, 0), (2, 0)]],
    'S': [[(2, 3.5), (1.5, 4), (0.5, 4), (0, 3.5), (0, 2.5), (0.5, 2), (1.5, 2), (2, 1.5), (2, 0.5),
           (1.5, 0), (0.5, 0), (0, 0.5)]],
    '-': [[(0.3, 2), (1.7, 2)]],
}
GLYPH_W, GLYPH_H, GLYPH_GAP = 2., 4., 0.8
NUMBER = r'-?\d+(?:\.\d+)?'
PATH_OP = re.compile(rf'^((?:{NUMBER}\s+)*)([a-zA-Z]{{1,2}})$')
CLOSING_PAINTS = ('s', 'f', 'b', 'n')
PAINTS = CLOSING_PAINTS+('S', 'F', 'B', 'N')


def pt(value):
    """One millimetre coordinate as the point number the file carries."""
    text = f'{value*PT_PER_MM:.{DIGITS}f}'.rstrip('0').rstrip('.')
    return '0' if text in ('', '-0') else text


def board_entities(doc):
    """The entities that lie on the stock board, which are the ones this file may carry.

    tests/test_generator.py measures the same rule against the DXF, so it is written once here
    instead of once per caller.
    """
    out = []
    for e in doc.modelspace():
        layer = e.dxf.layer
        if layer in NEST_ONLY_LAYERS:
            if meta(e).get('view') != 'nest':
                continue
        elif not (layer in BOARD_LAYERS or layer.startswith('POCKET_')):
            continue
        out.append(e)
    return out


def layer_order(entities):
    """Layer names in the fixed drawing order, leaving out the ones this design does not use."""
    present = {e.dxf.layer for e in entities}
    out = []
    for name in DRAWING_ORDER:
        if name == 'POCKET':
            out += sorted(q for q in present if q.startswith('POCKET_'))
        elif name in present:
            out.append(name)
    return out


def ink(layer):
    return INK['POCKET' if layer.startswith('POCKET_') else layer]


def anchor(e):
    """Where a label sits: its alignment point once an alignment was set, else its insert."""
    point = e.dxf.align_point if (e.dxf.halign or e.dxf.valign) else e.dxf.insert
    return point.x, point.y


def arc_beziers(start, end, bulge):
    """One bulged segment as cubic Bezier pieces of at most MAX_SWEEP each."""
    cx, cy, radius, angle, sweep = bulge_arc(start, end, bulge)
    count = max(1, math.ceil(abs(sweep)/MAX_SWEEP))
    step = sweep/count
    # The classic control-point length for a circular arc of this sweep. It puts the curve on
    # the arc at both ends and at the middle, so measuring it there says nothing; what the
    # pieces do in between is measured from the written file by curve_deviation().
    k = 4/3*math.tan(step/4)
    out = []
    for i in range(count):
        t0, t1 = angle+step*i, angle+step*(i+1)
        p0 = (cx+radius*math.cos(t0), cy+radius*math.sin(t0))
        p3 = (cx+radius*math.cos(t1), cy+radius*math.sin(t1))
        c1 = (p0[0]-k*radius*math.sin(t0), p0[1]+k*radius*math.cos(t0))
        c2 = (p3[0]+k*radius*math.sin(t1), p3[1]-k*radius*math.cos(t1))
        out.append((c1, c2, p3))
    return out


def bezier_point(p0, c1, c2, p3, t):
    u = 1-t
    weights = (u*u*u, 3*u*u*t, 3*u*t*t, t*t*t)
    return tuple(sum(w*p[axis] for w, p in zip(weights, (p0, c1, c2, p3))) for axis in (0, 1))


def label_strokes(text, height, x, y):
    """A part label as polylines, centred where the DXF anchors its MIDDLE_CENTER text."""
    unknown = sorted(set(text)-set(GLYPHS))
    if unknown:
        raise ValueError(f'The stroke font has no glyph for: {" ".join(unknown)}')
    unit = height/GLYPH_H
    advance = (GLYPH_W+GLYPH_GAP)*unit
    width = advance*len(text)-GLYPH_GAP*unit
    left, bottom = x-width/2, y-height/2
    return [[(left+index*advance+px*unit, bottom+py*unit) for px, py in stroke]
            for index, char in enumerate(text) for stroke in GLYPHS[char]]


def stroke_lines(points):
    """An open polyline as moveto, linetos and a stroke."""
    return ([f'{pt(points[0][0])} {pt(points[0][1])} m']
            + [f'{pt(x)} {pt(y)} L' for x, y in points[1:]]+['S'])


def shape_lines(e):
    """One machining contour as a path: moveto, linetos, arcs as curves, and the painting."""
    vertices = list(e.get_points('xyb'))
    out = [f'{pt(vertices[0][0])} {pt(vertices[0][1])} m']
    span = len(vertices) if e.closed else len(vertices)-1
    for i in range(span):
        x0, y0, bulge = vertices[i]
        x1, y1 = vertices[(i+1) % len(vertices)][:2]
        if bulge:
            out += [f'{pt(c1[0])} {pt(c1[1])} {pt(c2[0])} {pt(c2[1])} {pt(p3[0])} {pt(p3[1])} C'
                    for c1, c2, p3 in arc_beziers((x0, y0), (x1, y1), bulge)]
        elif not (e.closed and i == span-1):
            out.append(f'{pt(x1)} {pt(y1)} L')
        # The closing straight segment of a closed contour is left to the painting operator,
        # so the path holds no zero-length step back onto its own first point.
    out.append('s' if e.closed else 'S')
    return out


def header(cfg):
    """The document comments. No time, no job id: the same design has to give the same bytes.

    %%Creator names the application that wrote the file, which is this generator and not
    Illustrator. What lets Illustrator recognise the format is the %!PS-Adobe line and the
    layer and path operators below, not this comment.
    """
    return ['%!PS-Adobe-3.0',
            '%%Creator: hanok-window-generator',
            f"%%Title: ({cfg.PARAMS['revision']})",
            f'%%BoundingBox: 0 0 {math.ceil(cfg.BL*PT_PER_MM)} {math.ceil(cfg.BWD*PT_PER_MM)}',
            f'%%HiResBoundingBox: 0 0 {pt(cfg.BL)} {pt(cfg.BWD)}',
            '%%DocumentProcessColors: Cyan Magenta Yellow Black',
            '%%ColorUsage: Color',
            '%%DocumentPreview: None',
            '%%EndComments',
            '%%BeginProlog',
            '%%EndProlog',
            '%%BeginSetup',
            '%%EndSetup']


def write(cfg, doc, path):
    """Write the board of `doc` to `path`, one millimetre to 72/25.4 points."""
    entities = board_entities(doc)
    order = layer_order(entities)
    lines = header(cfg)
    strokes = 0
    for index, layer in enumerate(order):
        cmyk, rgb = ink(layer)
        lines += ['%AI5_BeginLayer',
                  f'1 1 1 1 0 0 {index} {rgb[0]} {rgb[1]} {rgb[2]} Lb',
                  f'({layer}) Ln',
                  '0 J 0 j 0.25 w 4 M []0 d',
                  ' '.join(f'{v:g}' for v in cmyk)+' K']
        for e in [q for q in entities if q.dxf.layer == layer]:
            if e.dxftype() == 'TEXT':
                for stroke in label_strokes(e.dxf.text, e.dxf.height, *anchor(e)):
                    lines += stroke_lines(stroke)
                    strokes += 1
            else:
                lines += shape_lines(e)
        lines += ['LB', '%AI5_EndLayer--']
    lines += ['%%PageTrailer', 'gsave annotatepage grestore showpage', '%%Trailer', '%%EOF']
    data = ('\n'.join(lines)+'\n').encode('ascii')
    Path(path).write_bytes(data)
    return dict(bytes=len(data), layers=order, shapes=sum(1 for e in entities if e.dxftype() != 'TEXT'),
                label_strokes=strokes)


def read(path):
    """Recover the paths of each layer, reading the file rather than trusting what wrote it."""
    layers, current, points, curves = [], None, [], []
    for line in Path(path).read_text(encoding='ascii').splitlines():
        if line.startswith('(') and line.endswith(') Ln'):
            current = dict(name=line[1:-4], paths=[])
            layers.append(current)
            continue
        match = PATH_OP.match(line)
        if match is None or current is None:
            continue
        operands = [float(v)/PT_PER_MM for v in match.group(1).split()]
        op = match.group(2)
        if op == 'm':
            points, curves = [tuple(operands)], []
        elif op in ('l', 'L'):
            points.append(tuple(operands))
        elif op in ('c', 'C'):
            curves.append((points[-1], tuple(operands[0:2]), tuple(operands[2:4]), tuple(operands[4:6])))
            points.append(tuple(operands[4:6]))
        elif op in PAINTS:
            current['paths'].append(dict(points=points, curves=curves, closed=op in CLOSING_PAINTS))
            points, curves = [], []
    return layers


def nearest_path(candidates, want, closed):
    """The recovered path lying closest to every vertex of one DXF contour, and how far it is."""
    best, best_error = None, None
    for candidate in candidates:
        if candidate['closed'] != closed or not candidate['points']:
            continue
        error = max(min(math.hypot(wx-gx, wy-gy) for gx, gy in candidate['points']) for wx, wy in want)
        if best_error is None or error < best_error:
            best, best_error = candidate, error
    return best, best_error


def curve_deviation(path, arcs):
    """How far the cubic pieces of a recovered path run from the circles they stand in for."""
    if not path['curves']:
        return 0.
    if not arcs:
        return math.inf  # a straight contour came back curved
    worst = 0.
    for p0, c1, c2, p3 in path['curves']:
        for t in (0.25, 0.5, 0.75):
            x, y = bezier_point(p0, c1, c2, p3, t)
            worst = max(worst, min(abs(math.hypot(x-cx, y-cy)-radius) for cx, cy, radius, _, _ in arcs))
    return worst


def verify(doc, path):
    """Read the written file back and compare it with the board of `doc`.

    Returns (passed, measurement). Vertices have to return inside the engine's linear
    tolerance and arcs inside its chord tolerance, every contour has to be found exactly once,
    and the layers have to be the ones this design puts on the board and no others.
    """
    entities = board_entities(doc)
    shapes = [e for e in entities if e.dxftype() != 'TEXT']
    labels = [e for e in entities if e.dxftype() == 'TEXT']
    measured = dict(entities=len(entities), paths=0, labels=len(labels),
                    worst_vertex_mm=None, worst_arc_mm=None)
    try:
        layers = read(path)
    except (OSError, ValueError, UnicodeDecodeError):
        return False, measured
    measured['paths'] = sum(len(q['paths']) for q in layers)
    pools = {q['name']: list(q['paths']) for q in layers}
    strokes = sum(len(label_strokes(e.dxf.text, e.dxf.height, *anchor(e))) for e in labels)
    found = len(pools) == len(layers) and [q['name'] for q in layers] == layer_order(entities)
    found = found and measured['paths'] == len(shapes)+strokes
    worst_vertex = worst_arc = 0.
    for e in shapes:
        want = [(v[0], v[1]) for v in e.get_points('xy')]
        best, error = nearest_path(pools.get(e.dxf.layer, []), want, bool(e.closed))
        if best is None:
            found = False
            continue
        pools[e.dxf.layer].remove(best)
        worst_vertex = max(worst_vertex, error)
        worst_arc = max(worst_arc, curve_deviation(best, polyline_arcs(e)))
    ok = found and worst_vertex <= LENGTH_TOL_MM and worst_arc <= ARC_CHORD_TOL_MM
    # JSON has no Infinity and a failure report carries this measurement, so a contour that came
    # back curved when it is straight is reported as no measurement rather than as Infinity.
    measured.update(worst_vertex_mm=worst_vertex,
                    worst_arc_mm=worst_arc if math.isfinite(worst_arc) else None)
    return bool(ok), measured
