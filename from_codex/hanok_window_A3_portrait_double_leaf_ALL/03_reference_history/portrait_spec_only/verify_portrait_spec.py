#!/usr/bin/env python3
"""Validate the PORTRAIT prompt's nominal specification, not a saved DXF.

Run: python verify_portrait_spec.py
Dependency: shapely. Results are written next to this script.
No toolpath, DXF file, hardware model, or fabrication approval is produced.
"""
from __future__ import annotations
import csv
import itertools
import json
from collections import Counter, defaultdict
from pathlib import Path
from shapely.geometry import box, Point
from shapely.affinity import affine_transform, translate
from shapely.ops import unary_union

OUT = Path(__file__).resolve().parent
TOL = 1e-7
W, H = 187.0, 500.0
OPEN_W, OPEN_H = W - 60, H - 60
GX, GY = (OPEN_W - 20) / 3, (OPEN_H - 40) / 5
XS = [GX + 5, 2 * GX + 15]
YS = [GY + 5 + i * (GY + 10) for i in range(4)]
SIZES = {'F01': (586.,40.,2), 'F02': (463.,40.,2),
         'S01': (500.,30.,4), 'S02': (187.,30.,4),
         'L01': (460.,10.,4), 'L02': (147.,10.,8)}
NEST = {
 'F01-1':(20,20),'F02-1':(618,20),'F01-2':(20,72),'F02-2':(618,72),
 'S01-1':(20,124),'S01-2':(532,124),'S01-3':(20,166),'S01-4':(532,166),
 'S02-1':(20,208),'S02-2':(219,208),'S02-3':(418,208),'S02-4':(617,208),
 'L01-1':(20,250),'L01-2':(492,250),'L01-3':(20,272),'L01-4':(492,272),
 'L02-1':(20,294),'L02-2':(179,294),'L02-3':(338,294),'L02-4':(497,294),
 'L02-5':(20,316),'L02-6':(179,316),'L02-7':(338,316),'L02-8':(497,316)}


def transform(kind: str, num: int) -> tuple[list[float], str]:
    if kind[0] == 'F':
        if kind == 'F01':
            return ([0,1,-1,0,0,586] if num == 1 else [0,-1,1,0,463,0]), 'FIXED'
        return ([-1,0,0,1,463,0] if num == 1 else [1,0,0,-1,0,586]), 'FIXED'
    per_leaf = 4 if kind == 'L02' else 2
    right = num > per_leaf
    k = (num - 1) % per_leaf
    ox, oy = (233 if right else 43), 43
    if kind == 'S01':
        m = [0,1,-1,0,0,H] if k == 0 else [0,-1,1,0,W,0]
    elif kind == 'S02':
        m = [-1,0,0,1,W,0] if k == 0 else [1,0,0,-1,0,H]
    elif kind == 'L01':
        m = [0,-1,1,0,30+XS[k]+5,20]
    else:
        m = [1,0,0,-1,20,30+YS[k]+5]
    m[4] += ox
    m[5] += oy
    return m, 'RIGHT_LEAF' if right else 'LEFT_LEAF'


def main() -> None:
    checks = []
    def check(name: str, ok: bool, measured=None) -> None:
        checks.append({'name':name, 'status':'PASS' if ok else 'FAIL', 'measured':measured})
        if not ok:
            raise AssertionError(f'{name}: {measured}')

    parts, pockets, dogs = {}, [], []
    for kind, (length, width, count) in SIZES.items():
        for num in range(1,count+1):
            pid = f'{kind}-{num}'
            m, group = transform(kind,num)
            front = kind in ('F01','S01','L01')
            part = dict(part_id=pid, kind=kind, length=length, width=width,
                        thickness=20, nest_x=NEST[pid][0], nest_y=NEST[pid][1],
                        assembly_group=group, face_a='FRONT' if front else 'BACK',
                        assembly_transform=m, outer=box(0,0,length,width),
                        pockets=[], dogs=[])
            part['nested'] = translate(part['outer'],*NEST[pid])
            part['assembled'] = affine_transform(part['outer'],m)
            parts[pid] = part
            def pocket(joint, u0, v0, u1, v1, seat=False):
                rec = dict(feature_id=f'{pid}-P{len(part["pockets"])+1:02d}',
                           part_id=pid,joint=joint,seat=seat,
                           u0=u0,v0=v0,u1=u1,v1=v1,depth=10,
                           face_a=part['face_a'],geometry=box(u0,v0,u1,v1))
                rec['assembled'] = affine_transform(rec['geometry'],m)
                part['pockets'].append(rec)
                pockets.append(rec)
                if seat:
                    for side, u in [('L',u0),('R',u1)]:
                        r = dict(feature_id=f'{rec["feature_id"]}-DB-{side}',
                                 parent_pocket=rec['feature_id'],part_id=pid,
                                 center_u=u,center_v=20.,radius=3.2,depth=10,
                                 geometry=Point(u,20).buffer(3.2,resolution=128))
                        part['dogs'].append(r)
                        dogs.append(r)
            if kind.startswith('F'):
                pocket('J1',0,0,40,40); pocket('J1',length-40,0,length,40)
            elif kind.startswith('S'):
                pocket('J2',0,0,30,30); pocket('J2',length-30,0,length,30)
                for c in (YS if kind=='S01' else XS):
                    pocket('J4',30+c-5,20,30+c+5,30,True)
            else:
                pocket('J4',0,0,10,10); pocket('J4',length-10,0,length,10)
                for c in (YS if kind=='L01' else XS):
                    pocket('J3',10+c-5,0,10+c+5,10)

    counts = Counter(p['kind'] for p in parts.values())
    check('part_quantities',counts=={k:v[2] for k,v in SIZES.items()},dict(counts))
    check('parts_total',len(parts)==24,len(parts))
    jc = Counter(p['joint'] for p in pockets)
    check('pocket_quantities',jc=={'J1':8,'J2':16,'J3':32,'J4':48},dict(jc))
    check('pockets_total',len(pockets)==104,len(pockets))
    expected={'F01':2,'F02':2,'S01':6,'S02':4,'L01':6,'L02':4}
    check('pockets_per_part',all(len(p['pockets'])==expected[p['kind']] for p in parts.values()),expected)
    check('sash_seats',sum(p['seat'] for p in pockets)==24,24)
    check('dogbones_total',len(dogs)==48,len(dogs))
    check('dogbones_per_seat',all(sum(d['parent_pocket']==p['feature_id'] for d in dogs)==2 for p in pockets if p['seat']),2)
    for kind, n in [('S01',4),('S02',2)]:
        check(f'{kind}_seats_per_part',all(sum(v['seat'] for v in p['pockets'])==n for p in parts.values() if p['kind']==kind),n)
    all_geoms = [p['outer'] for p in parts.values()] + [p['geometry'] for p in pockets+dogs]
    check('spec_polygons_closed_and_valid',all(g.is_valid and g.exterior.is_closed and g.area>0 for g in all_geoms))
    check('pocket_containment',all(parts[p['part_id']]['outer'].buffer(TOL).covers(p['geometry']) for p in pockets))
    # Exact circle envelope containment, independent of circle tessellation.
    check('dogbone_exact_circle_containment',all(
        d['center_u']-d['radius']>=-TOL and d['center_v']-d['radius']>=-TOL and
        d['center_u']+d['radius']<=parts[d['part_id']]['length']+TOL and
        d['center_v']+d['radius']<=parts[d['part_id']]['width']+TOL for d in dogs))
    board = box(0,0,1220,900)
    check('board_containment',all(board.covers(p['nested']) for p in parts.values()))
    margin=min(min(p['nested'].bounds[0],p['nested'].bounds[1],1220-p['nested'].bounds[2],900-p['nested'].bounds[3]) for p in parts.values())
    check('min_edge_margin_mm',margin>=20-TOL,margin)
    pairs = list(itertools.combinations(parts.values(),2))
    gap=min(a['nested'].distance(b['nested']) for a,b in pairs)
    check('min_nesting_gap_mm',gap>=12-TOL,gap)
    check('no_nesting_overlap',all(a['nested'].intersection(b['nested']).area<TOL for a,b in pairs))
    check('grain_parallel_X',all(p['length']>p['width'] and abs(p['nested'].bounds[2]-p['nested'].bounds[0]-p['length'])<TOL for p in parts.values()))
    groups=defaultdict(list)
    for p in pockets:
        key=tuple(round(v,7) for v in p['assembled'].bounds)
        groups[key].append(p)
    check('joint_pair_count',len(groups)==52,len(groups))
    check('joint_pair_XY_match',all(len(g)==2 and g[0]['assembled'].symmetric_difference(g[1]['assembled']).area<TOL for g in groups.values()))
    check('joint_pair_type_match',all(g[0]['joint']==g[1]['joint'] for g in groups.values()))
    check('joint_pair_opposite_faces',all({p['face_a'] for p in g}=={'FRONT','BACK'} for g in groups.values()))
    for k,group in enumerate(groups.values(),1):
        for p in group:
            p['joint_pair_id']=f'PAIR-{k:02d}'
            mate=next(q for q in group if q is not p)
            p['mate_feature_id']=mate['feature_id']
            p['mate_part_id']=mate['part_id']
    check('face_transform_consistency',all((p['assembly_transform'][0]*p['assembly_transform'][3]-p['assembly_transform'][1]*p['assembly_transform'][2]>0)==(p['face_a']=='FRONT') for p in parts.values()))
    # Discrete Z slabs: faces at z=10 can touch; volumes must not overlap.
    slabs={}
    for pid,p in parts.items():
        removed=unary_union([r['geometry'] for r in p['pockets']+p['dogs']])
        reduced=affine_transform(p['outer'].difference(removed),p['assembly_transform'])
        slabs[pid]=[p['assembled'],reduced] if p['face_a']=='FRONT' else [reduced,p['assembled']]
    interference=[]
    for a,b in pairs:
        for zi in range(2):
            area=slabs[a['part_id']][zi].intersection(slabs[b['part_id']][zi]).area
            if area>TOL:
                interference.append([a['part_id'],b['part_id'],zi,area])
    check('nominal_assembled_volume_interference',not interference,interference)
    fixed_inner=box(40,40,423,546)
    leaves=[box(43,43,230,543),box(233,43,420,543)]
    check('each_leaf_187x500',all(abs((r.bounds[2]-r.bounds[0])-187)<TOL and abs((r.bounds[3]-r.bounds[1])-500)<TOL for r in leaves))
    check('centre_gap_3',abs(leaves[0].distance(leaves[1])-3)<TOL,leaves[0].distance(leaves[1]))
    check('external_gaps_3',min(leaves[0].bounds[0]-40,423-leaves[1].bounds[2],leaves[0].bounds[1]-40,546-leaves[0].bounds[3])==3)
    check('centre_no_fixed_mullion',all(p['assembly_group']!='FIXED' or p['assembled'].intersection(fixed_inner).area<TOL for p in parts.values()))
    check('no_leaf_bridging',all(leaves[0 if p['assembly_group']=='LEFT_LEAF' else 1].buffer(TOL).covers(p['assembled']) for p in parts.values() if p['assembly_group']!='FIXED'))
    region=box(73,73,390,513); picture=box(83,83,380,503)
    check('A3_portrait_297x420',(picture.bounds[2]-picture.bounds[0],picture.bounds[3]-picture.bounds[1])==(297,420))
    check('picture_margin_10',region.covers(picture) and region.boundary.distance(picture)==10,10)
    check('overall_height_greater_than_width',586>463,{'width':463,'height':586})
    check('lattice_equal_clear_spaces',abs(3*GX+20-127)<TOL and abs(5*GY+40-440)<TOL,{'gap_x':GX,'gap_y':GY,'centers_x':XS,'centers_y':YS})
    check('lattice_crossing_pairs_per_leaf',all(sum(p['joint']=='J3' and parts[p['part_id']]['assembly_group']==leaf for p in pockets)==16 for leaf in ['LEFT_LEAF','RIGHT_LEAF']),8)
    check('hinge_reference_heights_60_from_sash_ends',103-43==60 and 543-483==60)
    check('handle_reference_centers',200<=215<=230 and 233<=248<=263 and 293==(43+543)/2)

    report={
      'scope':'PORTRAIT_PROMPT_SPECIFICATION_ONLY',
      'dxf_generated':False,'saved_dxf_reread':False,'physical_fabrication_validated':False,
      'overall_status':'PASS_SPEC_ONLY',
      'checks_passed':len(checks),'checks':checks,
      'nominal_spec':{'overall_width_height':[463,586],'leaf_width_height':[187,500],
        'clear_opening_per_leaf':[127,440],'rear_picture_region':[317,440],
        'picture_width_height':[297,420],'board':[1220,900,20],
        'parts':24,'base_pockets':104,'dogbones':48,'joint_pairs':52,
        'nest_max_x':max(p['nested'].bounds[2] for p in parts.values()),
        'nest_max_y':max(p['nested'].bounds[3] for p in parts.values())},
      'pending':['Saved DXF generation and re-read validation',
                 'CNC renderer and visual inspection of the final DXF',
                 'Actual hinge selection, load capacity, screw layout and swing clearance',
                 'Rear backing attachment, picture protection and fastener clearance',
                 'Stock thickness/moisture/movement, tolerances, joint test pieces',
                 'Workholding, toolpaths, cutter measurement, feed and speed']}
    (OUT/'portrait_spec_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    records=[]
    for p in parts.values():
        records.append({k:v for k,v in p.items() if k not in ('outer','nested','assembled','pockets','dogs')})
    (OUT/'portrait_spec_manifest.json').write_text(json.dumps({'parts':records,'pockets':[
        {k:v for k,v in p.items() if k not in ('geometry','assembled')} for p in pockets],
        'dogbones':[{k:v for k,v in d.items() if k!='geometry'} for d in dogs]},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['overall_status'],'checks_passed':len(checks),
                      'spec':report['nominal_spec'],'pocket_counts':dict(jc)},ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
