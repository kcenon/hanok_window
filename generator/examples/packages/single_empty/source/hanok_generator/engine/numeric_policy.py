"""Numerical error bounds for nominal CAD geometry, not manufacturing allowances.

Inputs retain their floating-point values; they are never rounded to a grid.
Integer counts and identifiers still use exact comparison. Circular DXF bulges
are sampled from their actual circles, without an intermediate Bezier curve.
"""
import math

POLICY_VERSION = 'HANOK_NUMERIC_V1'
PARAMETER_TOL_MM = 1e-9
LENGTH_TOL_MM = 1e-7
RATIO_TOL = 1e-9
AREA_TOL_MM2 = 1e-7
VOLUME_TOL_MM3 = 1e-5
ARC_CHORD_TOL_MM = 1e-5


def close(a, b, tolerance=PARAMETER_TOL_MM):
    return math.isfinite(a) and math.isfinite(b) and abs(a-b) <= tolerance


def coordinates_match(a, b, tolerance=LENGTH_TOL_MM):
    return len(a) == len(b) and all(close(x, y, tolerance) for x, y in zip(a, b))


def geometry_matches(actual, expected, tolerance=LENGTH_TOL_MM):
    """Bound the whole boundary in mm as well as the difference area in mm2.

    Two-way boundary containment covers every line segment, including holes;
    it does not depend on vertex order and does not accept a distant thin spur
    merely because its area is small. Small numerical seams at a legitimate
    boundary are allowed within the declared linear tolerance.
    """
    if actual.is_empty or expected.is_empty or not actual.is_valid or not expected.is_valid:
        return False
    if not coordinates_match(actual.bounds, expected.bounds, tolerance):
        return False
    a, b = actual.boundary, expected.boundary
    if not b.buffer(tolerance).covers(a) or not a.buffer(tolerance).covers(b):
        return False
    area_limit = tolerance*(a.length+b.length) + math.pi*tolerance*tolerance
    return actual.symmetric_difference(expected).area <= area_limit


def bulge_arc(start, end, bulge):
    """Return (cx, cy, radius, start_angle, signed_sweep) for an actual DXF arc."""
    x0, y0 = start
    x1, y1 = end
    chord = math.hypot(x1-x0, y1-y0)
    if not all(math.isfinite(v) for v in (x0,y0,x1,y1,bulge)) or chord == 0 or bulge == 0:
        raise ValueError('A circular bulge needs finite, distinct endpoints and a nonzero bulge')
    factor = (1-bulge*bulge)/(4*bulge)
    cx = (x0+x1)/2 - (y1-y0)*factor
    cy = (y0+y1)/2 + (x1-x0)*factor
    radius = chord*(1+bulge*bulge)/(4*abs(bulge))
    return cx, cy, radius, math.atan2(y0-cy, x0-cx), 4*math.atan(bulge)


def polyline_arcs(entity):
    vertices = list(entity.get_points('xyb'))
    count = len(vertices) if entity.closed else max(0, len(vertices)-1)
    return [bulge_arc(vertices[i][:2], vertices[(i+1)%len(vertices)][:2], vertices[i][2])
            for i in range(count) if vertices[i][2] != 0]


def polyline_points(entity, chord_tolerance=ARC_CHORD_TOL_MM):
    """Sample circular segments with a bounded sagitta (arc-to-chord error)."""
    if chord_tolerance <= 0 or not math.isfinite(chord_tolerance):
        raise ValueError('chord_tolerance must be positive and finite')
    vertices = list(entity.get_points('xyb'))
    count = len(vertices) if entity.closed else max(0, len(vertices)-1)
    points = [tuple(vertices[0][:2])] if vertices else []
    for i in range(count):
        start, end = vertices[i], vertices[(i+1)%len(vertices)]
        if start[2] == 0:
            points.append(tuple(end[:2]))
            continue
        cx, cy, radius, angle, sweep = bulge_arc(start[:2], end[:2], start[2])
        # 4 asin(sqrt(error/(2R))) avoids cancellation in acos(1-error/R).
        step = 4*math.asin(math.sqrt(min(1., chord_tolerance/(2*radius))))
        segments = max(4, 4*math.ceil(abs(sweep)/step/4))
        for j in range(1, segments):
            theta = angle+sweep*j/segments
            points.append((cx+radius*math.cos(theta), cy+radius*math.sin(theta)))
        points.append(tuple(end[:2]))  # retain exact DXF endpoints
    return points


def curve_error(entity):
    return ARC_CHORD_TOL_MM if any(v[2] != 0 for v in entity.get_points('xyb')) else 0.


def policy_record():
    return dict(version=POLICY_VERSION, input_representation='IEEE-754 binary64; no input quantization',
                parameter_absolute_mm=PARAMETER_TOL_MM, linear_absolute_mm=LENGTH_TOL_MM,
                ratio_absolute=RATIO_TOL, overlap_area_mm2=AREA_TOL_MM2,
                interpenetration_volume_mm3=VOLUME_TOL_MM3,
                circular_chord_error_mm=ARC_CHORD_TOL_MM,
                geometry_equivalence='two-way whole-boundary containment plus perimeter-scaled area difference',
                contact_uncertainty='sum of both circular approximation bounds plus linear tolerance',
                manufacturing_allowance=False)
