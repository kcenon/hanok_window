"""Measure actual pocket/relief unions on each part and shared depth interval."""
from collections import defaultdict
from itertools import combinations
from shapely.geometry import LineString
from shapely.ops import unary_union
from cad_helpers import meta
from numeric_policy import LENGTH_TOL_MM, curve_error


def cut_interval(data, thickness):
    depth = data['depth_mm']
    if depth <= 0 or depth > thickness+LENGTH_TOL_MM:
        raise ValueError('Invalid machining depth')
    if data['machining_face'] == 'A':
        return thickness-depth, thickness
    if data['machining_face'] == 'B':
        return 0., depth
    raise ValueError('Unknown machining face')


def measure_machining(pockets, dogs, geometry, part_geometry, thickness):
    children=defaultdict(list)
    for e in dogs:
        children[meta(e)['parent_pocket']].append(e)
    groups=defaultdict(list)
    edge_failures=[];edge_measurements=[]
    for e in pockets:
        data=meta(e);pid=data['part_id'];fid=data['feature_id']
        entities=[e]+children[fid]
        cut=unary_union([geometry[q.dxf.handle] for q in entities])
        error=max(curve_error(q) for q in entities)
        z0,z1=cut_interval(data,thickness)
        groups[pid].append(dict(id=fid,joint=data['joint'],geometry=cut,error=error,z0=z0,z1=z1))
        x0,y0,x1,y1=part_geometry[pid].bounds
        edges={'U_MIN':LineString([(x0,y0),(x0,y1)]),'U_MAX':LineString([(x1,y0),(x1,y1)]),
               'V_MIN':LineString([(x0,y0),(x1,y0)]),'V_MAX':LineString([(x0,y1),(x1,y1)])}
        nominal=geometry[e.dxf.handle]
        measured_open={name for name,edge in edges.items() if nominal.distance(edge)<=LENGTH_TOL_MM}
        declared_open=set(data.get('open_edges',[]))
        if measured_open != declared_open:
            edge_failures.append(dict(part_id=pid,feature_id=fid,reason='open-edge intent differs from nominal geometry',
                                      declared=sorted(declared_open),measured=sorted(measured_open)))
        for name,edge in edges.items():
            if name in declared_open:
                continue
            distance=cut.distance(edge)
            row=dict(part_id=pid,feature_id=fid,edge=name,distance_mm=distance,
                     uncertainty_mm=error+LENGTH_TOL_MM)
            edge_measurements.append(row)
            if distance<=row['uncertainty_mm']:
                edge_failures.append(row)
    pairs=[];connections=[]
    for pid,cuts in groups.items():
        for a,b in combinations(cuts,2):
            shared=min(a['z1'],b['z1'])-max(a['z0'],b['z0'])
            if shared<=LENGTH_TOL_MM:
                continue
            distance=a['geometry'].distance(b['geometry'])
            uncertainty=a['error']+b['error']+LENGTH_TOL_MM
            row=dict(part_id=pid,features=[a['id'],b['id']],joints=[a['joint'],b['joint']],
                     shared_cut_depth_mm=shared,distance_mm=distance,uncertainty_mm=uncertainty)
            pairs.append(row)
            if distance<=uncertainty:
                row['overlap_area_mm2']=a['geometry'].intersection(b['geometry']).area
                row['reason']='overlap, contact, or separation within numerical uncertainty'
                connections.append(row)
    closest=min(pairs,key=lambda q:q['distance_mm']) if pairs else None
    edge_closest=min(edge_measurements,key=lambda q:q['distance_mm']) if edge_measurements else None
    return dict(
        separated=not connections,non_open_edges_preserved=not edge_failures,
        separation=dict(pairs_compared=len(pairs),closest_pair=closest,connections=connections,
                        method='each nominal pocket union its own reliefs; same part and overlapping actual cut-depth intervals'),
        edges=dict(edges_compared=len(edge_measurements),closest_edge=edge_closest,failures=edge_failures),
        manufacturing_assessment=dict(
            status='PENDING',
            machined_web=dict(measured_mm=closest['distance_mm'] if closest else None,required_minimum_mm=None),
            edge_web=dict(measured_mm=edge_closest['distance_mm'] if edge_closest else None,required_minimum_mm=None),
            remaining_thickness=dict(measured_mm=min(thickness-meta(e)['depth_mm'] for e in pockets),required_minimum_mm=None),
            reason='Material/process-qualified minima and fit coupons are not supplied. Geometric separation is not strength or manufacturing approval.'))
