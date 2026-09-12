#!/usr/bin/env python3
"""Create and re-read-validate PORTRAIT double-leaf CNC design geometry.

Run: python build_portrait_double_leaf.py
Validate an existing file without rebuilding:
    python build_portrait_double_leaf.py --validate-only
Dependencies: ezdxf, shapely, Pillow. All dimensions are millimetres.
No feeds, speeds, toolpaths, G-code, or physical hardware approval are generated.
"""
from __future__ import annotations
import argparse, csv, hashlib, itertools, json, math
from collections import Counter, defaultdict
from pathlib import Path
import ezdxf
from shapely.geometry import Polygon, Point, box
from shapely.affinity import affine_transform, translate, rotate
from shapely.ops import unary_union
from PIL import Image, ImageDraw
from cad_helpers import *

OUT=Path(__file__).resolve().parent
DXF=OUT/'hanok_window_A3_portrait_double_leaf_one_board_CNC.dxf'
TOL=1e-7
R=3.2
ASSEMBLY_ORIGIN=(1350.,100.)
OPENING_ORIGIN=(1350.,-370.)
SIZES={'F01':(586.,40.,2),'F02':(463.,40.,2),'S01':(500.,30.,4),
       'S02':(187.,30.,4),'L01':(460.,10.,4),'L02':(147.,10.,8)}
LAYERS={'BOARD_BOUNDARY':(8,35),'CUT_THROUGH':(7,35),'POCKET_10MM':(30,25),
        'DOGBONE':(6,25),'HINGE_REF':(4,18),'LATCH_REF':(4,18),
        'PART_ID':(7,18),'DIMENSIONS':(3,18),'GRAIN_DIRECTION':(3,35),
        'ASSEMBLY_REFERENCE':(8,18),'JOINT_DETAILS_REF':(8,18),'NOTES':(7,18)}


def load_spec():
    """Input is nominal geometry, not a toolpath or prior audit result."""
    s=json.loads((OUT/'design_spec.json').read_text(encoding='utf-8'))
    return s,{p['part_id']:p for p in s['parts']}


def local_to_assembly(p,g):
    return affine_transform(g,p['assembly_transform'])


def inverse_map(m):
    a,b,c,d,tx,ty=m
    det=a*d-b*c
    if abs(det)<1e-12: raise ValueError('Singular assembly transform')
    return [d/det,-b/det,-c/det,a/det,(b*ty-d*tx)/det,(c*tx-a*ty)/det]


def add_part_geometry(m,s,p):
    pid=p['part_id'];x=p['nest_x'];y=p['nest_y'];L=p['length'];B=p['width']
    dat=dict(kind='part',part_id=pid,family=p['kind'],length_mm=L,width_mm=B,
             thickness_mm=20,depth_mm=20,nesting_origin=[x,y],
             assembly_map=p['assembly_transform'],assembly_face_A=p['face_a'],
             assembly_group=p['assembly_group'],machining_face='A')
    rect(m,x,y,L,B,'CUT_THROUGH',**dat)
    # IDs are annotations, not engraving operations. For wide members the text
    # occupies the untouched lower band; lattice labels sit between slots.
    text(m,pid,(x+(L*.4 if p['kind']=='S01' else L/2),y+(B/2 if B==10 else B*.31)),3.4 if B==10 else 4.5,
         'PART_ID','center',kind='part_id',part_id=pid,view='nest')
    for q in s['pockets']:
        if q['part_id']!=pid: continue
        u0,v0,u1,v1=q['u0'],q['v0'],q['u1'],q['v1']
        edges=[]
        if abs(u0)<TOL: edges.append('U_MIN')
        if abs(u1-L)<TOL: edges.append('U_MAX')
        if abs(v0)<TOL: edges.append('V_MIN')
        if abs(v1-B)<TOL: edges.append('V_MAX')
        rect(m,x+u0,y+v0,u1-u0,v1-v0,'POCKET_10MM',
             kind='pocket',part_id=pid,feature_id=q['feature_id'],joint=q['joint'],
             joint_id=q['joint_pair_id'],mate_part_id=q['mate_part_id'],
             mate_feature_id=q['mate_feature_id'],seat=q['seat'],depth_mm=10,
             local_rect=[u0,v0,u1-u0,v1-v0],open_edges=edges,machining_face='A')
    for d in s['dogbones']:
        if d['part_id']!=pid:continue
        circle_poly(m,x+d['center_u'],y+d['center_v'],d['radius'],'DOGBONE',
                    kind='dogbone',part_id=pid,feature_id=d['feature_id'],
                    parent_pocket=d['parent_pocket'],depth_mm=10,radius_mm=d['radius'],
                    local_center=[d['center_u'],d['center_v']],
                    operation='UNION_WITH_PARENT_POCKET',machining_face='A')


def add_board(m):
    rect(m,0,0,1220,900,'BOARD_BOUNDARY',kind='board',view='nest',size_mm=[1220,900,20])
    text(m,'A3 PORTRAIT / DOUBLE-LEAF HANOK WINDOW',(0,955),13,kind='title',view='nest')
    text(m,'463 W x 586 H / 24 PARTS / 104 POCKETS / 48 RELIEFS / mm / MODEL SPACE 1:1',
         (0,930),5.5,view='nest')
    dimh(m,0,1220,900,914,'1220',view='nest')
    dimv(m,0,900,0,-27,'900',view='nest')
    line(m,(140,510),(1080,510),'GRAIN_DIRECTION',view='nest')
    line(m,(1080,510),(1036,531),'GRAIN_DIRECTION',view='nest')
    line(m,(1080,510),(1036,489),'GRAIN_DIRECTION',view='nest')
    text(m,'GRAIN DIRECTION  +X',(610,555),19,'GRAIN_DIRECTION','center',view='nest')
    text(m,'UNUSED OFFCUT / NOT ADDITIONAL PARTS',(610,700),13,align='center',view='nest')
    text(m,'All 24 part lengths run parallel to the 1220 mm grain direction.',(610,666),8,align='center',view='nest')
    notes=['ONE BOARD 1220 x 900 x 20 / ALL POCKETS MACHINED FROM COMMON FACE A',
           'ASSEMBLY: F01 + S01 + L01 A->FRONT. F02 + S02 + L02 FLIP A->BACK.',
           'POCKET_10MM + DOGBONE: UNION, REMOVE 10 mm. OPEN LAPS NEED WASTE-SIDE OVERRUN.',
           'HINGE_REF / LATCH_REF ARE POSITION REFERENCES ONLY. DO NOT MACHINE.',
           'NOMINAL FIT: VERIFY STOCK, TEST COUPONS, WORKHOLDING AND CAM BEFORE CUTTING.']
    for i,s in enumerate(notes):text(m,s,(30,852-i*20),6.6,view='nest')
    text(m,'No G-code, tabs, toolpaths, feeds or speeds are included. All hardware and backing remain PENDING.',
         (0,-35),5.3,view='nest')


def hardware_records():
    out=[]
    for side,pf,ps,xf,xs in [('LEFT','F01-1','S01-1',24,45),('RIGHT','F01-2','S01-4',425,404)]:
        for idx,y in enumerate([103,483],1):
            hid=f'H-{side}-{idx}'
            for pid,x,wing in [(pf,xf,'FIXED'),(ps,xs,'SASH')]:
                out.append(dict(hardware_id=hid,part_id=pid,layer='HINGE_REF',
                                box=[x,y-20,x+14,y+20],hardware_type='HINGE',wing=wing,
                                depth_ref_mm=2))
    for i,(x,pid) in enumerate([(215,'S01-2'),(248,'S01-3')],1):
        out.append(dict(hardware_id=f'HANDLE-{i}',part_id=pid,layer='LATCH_REF',
                        box=[x-5,283,x+5,303],hardware_type='HANDLE'))
    for i,(x,ps) in enumerate([(215,'S02-2'),(248,'S02-4')],1):
        for pid,cy in [(ps,531),('F02-2',557)]:
            out.append(dict(hardware_id=f'CATCH-{i}',part_id=pid,layer='LATCH_REF',
                            box=[x-5,cy-5,x+5,cy+5],hardware_type='CATCH'))
    return out


def add_hardware(m,parts):
    ox,oy=ASSEMBLY_ORIGIN
    for d in hardware_records():
        p=parts[d['part_id']];g=box(*d['box'])
        glocal=affine_transform(g,inverse_map(p['assembly_transform']))
        if not box(0,0,p['length'],p['width']).buffer(TOL).covers(glocal):
            raise ValueError('Hardware reference outside associated part')
        nested=translate(glocal,p['nest_x'],p['nest_y'])
        common={k:v for k,v in d.items() if k not in ('box','layer')}
        common.update(reference_only=True,production_machining=False,
                      assembly_face='FRONT',position_only=True)
        poly(m,list(nested.exterior.coords)[:-1],d['layer'],kind='hardware_ref',view='nest',**common)
        poly(m,list(translate(g,ox,oy).exterior.coords)[:-1],d['layer'],kind='hardware_ref',view='assembly',**common)
    for x in [41.5,421.5]:
        for y in [103,483]:
            line(m,(ox+x,oy+y-24),(ox+x,oy+y+24),'HINGE_REF',view='assembly',
                 kind='hinge_location_ref',reference_only=True)


def add_assembly(m,parts):
    ox,oy=ASSEMBLY_ORIGIN
    text(m,'PORTRAIT / W463 x H586',(ox,oy+670),10,view='assembly',kind='title')
    text(m,'LEFT-RIGHT DOUBLE LEAF / REFERENCE ONLY',(ox,oy+647),5,view='assembly')
    rect(m,ox+83,oy+83,297,420,'ASSEMBLY_REFERENCE',view='assembly',role='picture',
         nominal_size=[297,420],dxf_role='rear_picture')
    # This reflects the same parts and transformations as the machining layout.
    for p in sorted(parts.values(),key=lambda p:(p['face_a']=='BACK',p['part_id'])):
        g=translate(local_to_assembly(p,box(0,0,p['length'],p['width'])),ox,oy)
        poly(m,list(g.exterior.coords)[:-1],'ASSEMBLY_REFERENCE',view='assembly',role='body',
             part_id=p['part_id'],assembly_group=p['assembly_group'])
    rect(m,ox+73,oy+73,317,440,'ASSEMBLY_REFERENCE',view='assembly',role='picture_region',nominal_size=[317,440])
    for x in [73,263]:
        rect(m,ox+x,oy+73,127,440,'ASSEMBLY_REFERENCE',view='assembly',role='opening',nominal_size=[127,440])
    dimh(m,ox,ox+463,oy+586,oy+613,'463 OVERALL',view='assembly')
    dimv(m,oy,oy+586,ox+463,ox+499,'586 OVERALL',view='assembly')
    dimh(m,ox+43,ox+230,oy+43,oy-18,'187 LEFT LEAF',view='assembly')
    dimh(m,ox+233,ox+420,oy+43,oy-18,'187 RIGHT LEAF',view='assembly')
    dimv(m,oy+43,oy+543,ox,ox-29,'500 LEAF',view='assembly')
    for x in [73,263]:
        dimh(m,ox+x,ox+x+127,oy+513,oy+564,'127 OPENING',view='assembly')
    dimv(m,oy+73,oy+513,ox+390,ox+442,'440 OPENING',view='assembly')
    text(m,'A3 297 x 420',(ox+231.5,oy+97),6,'ASSEMBLY_REFERENCE','center',view='assembly',role='picture_label')
    for tx,s in [(136.5,'LEFT / 187 x 500'),(326.5,'RIGHT / 187 x 500')]:
        text(m,s,(ox+tx,oy+526),4,'ASSEMBLY_REFERENCE','center',view='assembly')
    for x,pid in [(20,'F01-1'),(443,'F01-2'),(58,'S01-1'),(215,'S01-2'),(248,'S01-3'),(405,'S01-4')]:
        text(m,pid,(ox+x,oy+340),3.6,'ASSEMBLY_REFERENCE','center',90,view='assembly')
    for x,y,pid in [(231.5,18,'F02-1'),(231.5,574,'F02-2'),(136.5,56,'S02-1'),(326.5,56,'S02-3')]:
        text(m,pid,(ox+x,oy+y),3.5,'ASSEMBLY_REFERENCE','center',view='assembly')
    text(m,'3 mm centre gap / 3 mm external clearances',(ox+231.5,oy-39),4.7,align='center',view='assembly')
    text(m,'Rear picture region 317 x 440 is NOT an unobstructed closed-front opening.',
         (ox+231.5,oy-53),3.8,align='center',view='assembly')


def add_opening(m):
    """Illustrative plan at 90 degrees; provisional axis only, not hardware approval."""
    ox,oy=OPENING_ORIGIN
    text(m,'OPENING REFERENCE / PLAN (LOOKING DOWN)',(ox,oy+310),8,view='opening',kind='title')
    text(m,'REFERENCE ONLY / AXES AND BACKING POSITION NOT FINAL',(ox,oy+290),4.7,view='opening')
    for g,role in [(box(0,0,40,20),'body'),(box(423,0,463,20),'body')]:
        poly(m,list(translate(g,ox,oy).exterior.coords)[:-1],'ASSEMBLY_REFERENCE',view='opening',role=role)
    for name,bounds,axis,deg in [('LEFT',[43,0,230,20],(41.5,24),90),
                                 ('RIGHT',[233,0,420,20],(421.5,24),-90)]:
        closed=box(*bounds)
        poly(m,list(translate(closed,ox,oy).exterior.coords)[:-1],'ASSEMBLY_REFERENCE',
             view='opening',role='opening',kind='closed_leaf_ghost',leaf=name)
        opened=rotate(closed,deg,origin=axis)
        poly(m,list(translate(opened,ox,oy).exterior.coords)[:-1],'ASSEMBLY_REFERENCE',
             view='opening',role='body',kind='opened_leaf_illustration',leaf=name,
             reference_only=True,illustrative_angle_deg=90,provisional_axis=list(axis))
        circle_poly(m,ox+axis[0],oy+axis[1],3,'HINGE_REF',view='opening',reference_only=True)
        text(m,f'{name} LEAF',(ox+(80 if name=='LEFT' else 382),oy+134),5,
             'ASSEMBLY_REFERENCE','center',90,view='opening')
        angles=[i*math.pi/36 for i in range(19)]
        if name=='RIGHT':angles=[math.pi-a for a in angles]
        points=[(ox+axis[0]+120*math.cos(a),oy+axis[1]+120*math.sin(a)) for a in angles]
        for a,b in zip(points,points[1:]):line(m,a,b,'ASSEMBLY_REFERENCE',view='opening',kind='direction')
        a,b=points[-2:];dx=b[0]-a[0];dy=b[1]-a[1];ln=math.hypot(dx,dy)
        for sg in [-1,1]:
            line(m,b,(b[0]-8*dx/ln+sg*3*dy/ln,b[1]-8*dy/ln-sg*3*dx/ln),
                 'ASSEMBLY_REFERENCE',view='opening',kind='direction')
        text(m,'90 deg REF',(ox+(180 if name=='LEFT' else 283),oy+188),4.8,
             'ASSEMBLY_REFERENCE','center',view='opening')
    # One continuous fixed artwork plane. Its rear setback is illustrative.
    rect(m,ox+83,oy-24,297,4,'ASSEMBLY_REFERENCE',view='opening',role='picture',reference_only=True)
    line(m,(ox+73,oy-29),(ox+390,oy-29),'ASSEMBLY_REFERENCE',view='opening',reference_only=True)
    text(m,'ONE A3 PICTURE / FIXED BEHIND BOTH LEAVES',(ox+231.5,oy-47),4.4,align='center',view='opening')
    text(m,'CENTRE MEMBERS MOVE WITH EACH LEAF',(ox+231.5,oy+247),5,align='center',view='opening')
    text(m,'NO FIXED CENTRE MULLION',(ox+231.5,oy+265),6,align='center',view='opening')
    text(m,'VIEWER / FRONT +Z',(ox+231.5,oy+222),5,align='center',view='opening')
    text(m,'Illustrative axes: (X,Z)=(41.5,24),(421.5,24). Recheck selected hardware.',
         (ox,oy-70),3.8,view='opening')
    text(m,'No actual hinge, screw, backing clearance or load capacity is verified here.',
         (ox,oy-83),3.8,view='opening')


def build():
    global MSP
    spec,parts=load_spec()
    doc=ezdxf.new('R2010');doc.units=ezdxf.units.MM
    doc.header['$MEASUREMENT']=1;doc.header['$LUNITS']=2;doc.header['$LUPREC']=3
    doc.header['$INSBASE']=(0,0,0);doc.header['$LWDISPLAY']=True
    doc.appids.new(APP)
    for name,(c,lw) in LAYERS.items():doc.layers.new(name,dxfattribs={'color':c,'lineweight':lw})
    doc.linetypes.new('REF_DASH',dxfattribs={'description':'Reference dash 4-2','pattern':[6,4,-2]})
    doc.linetypes.new('A3_DASHDOT',dxfattribs={'description':'A3 picture dash-dot','pattern':[13,8,-2,1,-2]})
    for name in ['HINGE_REF','LATCH_REF']:doc.layers.get(name).dxf.linetype='REF_DASH'
    MSP=doc.modelspace()
    for p in parts.values():add_part_geometry(MSP,spec,p)
    add_board(MSP);add_assembly(MSP,parts);add_hardware(MSP,parts)
    positions=add_details();add_opening(MSP)
    for e in MSP:
        role=meta(e).get('role')
        if role=='picture':e.dxf.linetype='A3_DASHDOT'
        elif role in ('opening','picture_region'):e.dxf.linetype='REF_DASH'
    # Default view opens on the stock and machining layout, not the reference sheets.
    doc.set_modelspace_vport(height=1090,center=(600,440))
    pre=validate(doc,'IN_MEMORY_BEFORE_SAVE')
    tmp=OUT/'_validated_candidate.dxf';doc.saveas(tmp)
    checkdoc=ezdxf.readfile(tmp)
    report=validate(checkdoc,'READ_BACK_FROM_SAVED_DXF')
    tmp.replace(DXF)
    report.update(file=DXF.name,sha256=hashlib.sha256(DXF.read_bytes()).hexdigest(),
                  pre_save_status=pre['status'],ezdxf_version=ezdxf.__version__)
    (OUT/'validation_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    write_manifests(checkdoc)
    return checkdoc,report,positions


def validate(doc,phase):
    """Inspect actual DXF geometry; do not reuse the old spec-only PASS record."""
    checks=[];errors=[];ents=list(doc.modelspace())
    def check(name,ok,detail=None):
        checks.append(dict(name=name,status='PASS' if ok else 'FAIL',measured=detail))
        if not ok:errors.append(name)
    rawparts=[e for e in ents if e.dxf.layer=='CUT_THROUGH']
    pockets=[e for e in ents if e.dxf.layer=='POCKET_10MM']
    dogs=[e for e in ents if e.dxf.layer=='DOGBONE']
    partids=[meta(e).get('part_id') for e in rawparts]
    check('unique_part_ids_and_total',len(partids)==24 and len(set(partids))==24,len(partids))
    partents={meta(e)['part_id']:e for e in rawparts}
    count=Counter(meta(e).get('family') for e in rawparts)
    for k,(_,_,n) in SIZES.items():check(f'{k}_part_count',count[k]==n,{'actual':count[k],'required':n})
    mach=rawparts+pockets+dogs
    check('all_machining_entities_closed_lwpolyline',all(e.dxftype()=='LWPOLYLINE' and e.closed for e in mach),len(mach))
    geom={e.dxf.handle:entity_polygon(e) for e in mach}
    check('valid_positive_area_no_self_intersection',all(g.is_valid and g.area>0 for g in geom.values()))
    keys=[(e.dxf.layer,geom[e.dxf.handle].normalize().wkb) for e in mach]
    check('no_duplicate_complete_machining_contours',len(keys)==len(set(keys)),len(keys)-len(set(keys)))
    partgeo={pid:geom[e.dxf.handle] for pid,e in partents.items()}
    check('all_part_sizes_match_portrait_spec',all(
        abs(g.bounds[2]-g.bounds[0]-SIZES[pid[:3]][0])<TOL and
        abs(g.bounds[3]-g.bounds[1]-SIZES[pid[:3]][1])<TOL and
        abs(g.area-SIZES[pid[:3]][0]*SIZES[pid[:3]][1])<TOL
        for pid,g in partgeo.items()))
    boardents=[e for e in ents if e.dxf.layer=='BOARD_BOUNDARY']
    check('board_boundary_1220x900',len(boardents)==1 and entity_polygon(boardents[0]).equals(box(0,0,1220,900)))
    check('all_parts_within_board',all(box(0,0,1220,900).covers(g) for g in partgeo.values()))
    pairs=list(itertools.combinations(partgeo,2))
    overlap=max(partgeo[a].intersection(partgeo[b]).area for a,b in pairs)
    gap=min(partgeo[a].distance(partgeo[b]) for a,b in pairs)
    margin=min(min(g.bounds[0],g.bounds[1],1220-g.bounds[2],900-g.bounds[3]) for g in partgeo.values())
    check('no_nesting_overlap',overlap<TOL,overlap)
    check('minimum_nesting_gap_12mm',gap>=12-TOL,gap)
    check('minimum_board_edge_margin_20mm',margin>=20-TOL,margin)
    check('all_lengths_parallel_X_grain',all(g.bounds[2]-g.bounds[0]>g.bounds[3]-g.bounds[1] for g in partgeo.values()))
    bypart=defaultdict(list);byjoint=Counter();by_pair=defaultdict(list)
    for e in pockets:
        d=meta(e);bypart[d['part_id']].append(e);byjoint[d['joint']]+=1;by_pair[d['joint_id']].append(e)
    for j,n in [('J1',8),('J2',16),('J3',32),('J4',48)]:check(f'{j}_pocket_count',byjoint[j]==n,byjoint[j])
    check('total_base_pockets_104',len(pockets)==104,len(pockets))
    expected={'F01':2,'F02':2,'S01':6,'S02':4,'L01':6,'L02':4}
    check('pockets_per_part',all(len(bypart[p])==expected[p[:3]] for p in partents))
    check('S01_four_J4_seats_each',all(sum(meta(e)['joint']=='J4' and meta(e)['seat'] for e in bypart[p])==4 for p in partents if p.startswith('S01')))
    check('S02_two_J4_seats_each',all(sum(meta(e)['joint']=='J4' and meta(e)['seat'] for e in bypart[p])==2 for p in partents if p.startswith('S02')))
    check('all_lattice_two_end_laps',all(sum(meta(e)['joint']=='J4' for e in bypart[p])==2 for p in partents if p.startswith('L')))
    check('all_L01_four_and_L02_two_crossing_pockets',all(sum(meta(e)['joint']=='J3' for e in bypart[p])==(4 if p.startswith('L01') else 2) for p in partents if p.startswith('L')))
    # Compare actual local rectangles to the mandated formula, not just counts.
    X=[(127-20)/3+5,2*(127-20)/3+15];Y=[85,175,265,355]
    actual_patterns={}
    formula_ok=True
    for pid,pe in partents.items():
        k=pid[:3];L,B,_=SIZES[k];x,y=meta(pe)['nesting_origin']
        got=sorted(tuple(round(v,7) for v in translate(geom[e.dxf.handle],-x,-y).bounds) for e in bypart[pid])
        size=40 if k.startswith('F') else 30 if k.startswith('S') else 10
        want=[(0,0,size,size),(L-size,0,L,size)]
        if k.startswith('S'):
            want += [(30+c-5,20,30+c+5,30) for c in (Y if k=='S01' else X)]
        elif k.startswith('L'):
            want += [(10+c-5,0,10+c+5,10) for c in (Y if k=='L01' else X)]
        want=sorted(tuple(round(v,7) for v in r) for r in want)
        formula_ok &= got==want
        actual_patterns[pid]=got
    check('all_pocket_coordinates_match_exact_formulas',formula_ok)
    seats=[e for e in pockets if meta(e).get('seat')]
    dbpar=defaultdict(list)
    for e in dogs:dbpar[meta(e)['parent_pocket']].append(e)
    dogok=len(dogs)==48
    for e in seats:
        d=meta(e);items=dbpar[d['feature_id']];dogok &= len(items)==2
        u,v,w,h=d['local_rect'];wantcenters={(round(u,7),20.),(round(u+w,7),20.)}
        gotcenters=set()
        for de in items:
            dd=meta(de);pid=dd['part_id'];x,y=meta(partents[pid])['nesting_origin']
            verts=list(de.get_points('xyb'))
            dogok &= len(verts)==2 and all(abs(vt[2]-1)<TOL for vt in verts)
            if len(verts)!=2:continue
            cx=(verts[0][0]+verts[1][0])/2;cy=(verts[0][1]+verts[1][1])/2
            radius=math.hypot(verts[0][0]-cx,verts[0][1]-cy)
            gotcenters.add((round(cx-x,7),round(cy-y,7)))
            dogok &= abs(radius-3.2)<TOL and dd['part_id']==d['part_id'] and dd['depth_mm']==10
            dogok &= partgeo[pid].buffer(TOL).covers(box(cx-radius,cy-radius,cx+radius,cy+radius))
        dogok &= gotcenters==wantcenters
    check('48_exact_R3_2_corner_reliefs_two_per_seat',bool(dogok),len(dogs))
    check('all_pockets_reliefs_inside_own_part',all(partgeo[meta(e)['part_id']].buffer(TOL).covers(geom[e.dxf.handle]) for e in pockets+dogs))
    check('layer_depth_and_face_separation',all(meta(e).get('depth_mm')==20 for e in rawparts) and all(meta(e).get('depth_mm')==10 and meta(e).get('machining_face')=='A' for e in pockets+dogs))
    check('all_required_layers_exist',all(name in doc.layers for name in LAYERS))
    check('mm_modelspace_flat_geometry',doc.units==4 and len(doc.paperspace())==0 and all(e.dxf.elevation==0 for e in mach))
    check('part_annotations_separate_and_unique',Counter(meta(e).get('part_id') for e in ents if e.dxf.layer=='PART_ID')==Counter({p:1 for p in partents}))
    def assembled(pid,g):
        d=meta(partents[pid]);x,y=d['nesting_origin']
        return affine_transform(translate(g,-x,-y),d['assembly_map'])
    ap={p:assembled(p,g) for p,g in partgeo.items()}
    check('assembly_transform_faces_consistent',all(
        ((d['assembly_map'][0]*d['assembly_map'][3]-d['assembly_map'][1]*d['assembly_map'][2])>0)==(d['assembly_face_A']=='FRONT')
        for d in map(meta,rawparts)))
    pairgood=len(by_pair)==52;maxmismatch=0.;mateok=True
    for jid,gg in by_pair.items():
        if len(gg)!=2:pairgood=False;continue
        a,b=gg;da,db=meta(a),meta(b)
        ga=assembled(da['part_id'],geom[a.dxf.handle]);gb=assembled(db['part_id'],geom[b.dxf.handle])
        mismatch=ga.symmetric_difference(gb).area;maxmismatch=max(mismatch,maxmismatch)
        pairgood &= mismatch<1e-6 and da['joint']==db['joint']
        pairgood &= {meta(partents[d['part_id']])['assembly_face_A'] for d in [da,db]}=={'FRONT','BACK'}
        pairgood &= ap[da['part_id']].intersection(ap[db['part_id']]).symmetric_difference(ga).area<1e-6
        mateok &= da['mate_feature_id']==db['feature_id'] and db['mate_feature_id']==da['feature_id']
    check('52_joint_pairs_XY_match_opposite_faces',bool(pairgood),{'pairs':len(by_pair),'max_mismatch_area_mm2':maxmismatch})
    check('mate_feature_links_bidirectional',bool(mateok))
    slabs={}
    for pid,g in ap.items():
        removal=unary_union([assembled(pid,geom[e.dxf.handle]) for e in pockets+dogs if meta(e)['part_id']==pid])
        small=g.difference(removal)
        slabs[pid]=[g,small] if meta(partents[pid])['assembly_face_A']=='FRONT' else [small,g]
    v_max=max(sum(slabs[a][i].intersection(slabs[b][i]).area*10 for i in [0,1]) for a,b in pairs)
    check('no_nominal_assembled_solid_interpenetration',v_max<1e-5,{'max_volume_mm3':v_max,'method':'Z slabs 0..10 and 10..20; arcs flattened with <=0.00001 mm tolerance'})
    fixed=unary_union([g for pid,g in ap.items() if pid.startswith('F')])
    left=unary_union([g for pid,g in ap.items() if meta(partents[pid])['assembly_group']=='LEFT_LEAF'])
    right=unary_union([g for pid,g in ap.items() if meta(partents[pid])['assembly_group']=='RIGHT_LEAF'])
    check('frame_463x586_inner383x506',fixed.equals(box(0,0,463,586).difference(box(40,40,423,546))))
    check('both_leaf_envelopes187x500',left.bounds==(43,43,230,543) and right.bounds==(233,43,420,543))
    check('centre_gap3_and_outer_gaps3',abs(left.distance(right)-3)<TOL and abs(left.distance(fixed)-3)<TOL and abs(right.distance(fixed)-3)<TOL)
    check('no_fixed_centre_mullion',fixed.intersection(box(40,40,423,546)).area<TOL)
    check('no_member_bridges_leaves',all(box(43,43,230,543).buffer(TOL).covers(ap[pid]) if meta(e)['assembly_group']=='LEFT_LEAF' else box(233,43,420,543).buffer(TOL).covers(ap[pid]) for pid,e in partents.items() if meta(e)['assembly_group']!='FIXED'))
    ox,oy=ASSEMBLY_ORIGIN
    assemblies=[e for e in ents if meta(e).get('view')=='assembly']
    abodies=[e for e in assemblies if meta(e).get('role')=='body']
    check('assembly_reference_matches_all24_cut_parts',len(abodies)==24 and all(translate(entity_polygon(e),-ox,-oy).symmetric_difference(ap[meta(e)['part_id']]).area<1e-6 for e in abodies))
    pic=[e for e in assemblies if meta(e).get('role')=='picture'][0]
    reg=[e for e in assemblies if meta(e).get('role')=='picture_region'][0]
    pg=translate(entity_polygon(pic),-ox,-oy);rg=translate(entity_polygon(reg),-ox,-oy)
    check('A3_portrait297x420_in317x440_margin10',pg.equals(box(83,83,380,503)) and rg.equals(box(73,73,390,513)) and abs(rg.boundary.distance(pg)-10)<TOL)
    check('A3_and_picture_region_distinct_linetypes',pic.dxf.linetype!=reg.dxf.linetype,{'A3':pic.dxf.linetype,'region':reg.dxf.linetype})
    openings=[e for e in assemblies if meta(e).get('role')=='opening']
    check('two127x440_opening_references',len(openings)==2 and all(abs(entity_polygon(e).area-127*440)<TOL for e in openings))
    hws=[e for e in ents if meta(e).get('kind')=='hardware_ref' and meta(e).get('view')=='nest']
    hwtype=defaultdict(set)
    hwmatch=True
    for e in hws:
        d=meta(e);hwtype[d['hardware_type']].add(d['hardware_id'])
        hwmatch &= d['reference_only'] and not d['production_machining']
        g=assembled(d['part_id'],entity_polygon(e))
        matched=[q for q in assemblies if meta(q).get('kind')=='hardware_ref' and meta(q).get('part_id')==d['part_id'] and meta(q).get('hardware_id')==d['hardware_id']]
        hwmatch &= len(matched)==1 and translate(entity_polygon(matched[0]),-ox,-oy).symmetric_difference(g).area<1e-6
    check('hardware4hinges2handles2catches_reference_only',bool(hwmatch) and {k:len(v) for k,v in hwtype.items()}=={'HINGE':4,'HANDLE':2,'CATCH':2},{k:len(v) for k,v in hwtype.items()})
    detailtypes={meta(e).get('detail') for e in ents if meta(e).get('view')=='detail'}
    check('J1_J2_J3_J4_reference_details_present',detailtypes=={'J1','J2','J3','J4'})
    check('references_never_on_machining_layers',not any(meta(e).get('view') in ['assembly','detail','opening'] for e in mach))
    opened=[e for e in ents if meta(e).get('kind')=='opened_leaf_illustration']
    check('two_sided_opening_illustration_reference_only',len(opened)==2 and all(meta(e).get('reference_only') for e in opened))
    check('all104_pockets_have_open_edge_intent',all(bool(meta(e).get('open_edges')) for e in pockets))
    audit=doc.audit()
    check('DXF_audit_no_errors_no_fixes',not audit.has_errors and not audit.has_fixes,{'errors':len(audit.errors),'fixes':len(audit.fixes)})
    if errors:raise AssertionError('DXF validation failed: '+', '.join(errors))
    return dict(status='PASS_NOMINAL_DXF_GEOMETRY',phase=phase,saved_dxf_reread=phase=='READ_BACK_FROM_SAVED_DXF',
                checks_passed=len(checks),checks=checks,parts_total=24,part_counts=dict(count),
                nominal_pockets_total=len(pockets),pocket_counts=dict(byjoint),dogbone_reliefs_total=len(dogs),
                machining_profiles_total=len(mach),mated_joints_total=len(by_pair),
                minimum_part_gap_mm=gap,minimum_board_margin_mm=margin,
                nesting_bounds_mm=list(unary_union(list(partgeo.values())).bounds),
                overall_width_height_mm=[463,586],leaf_width_height_mm=[187,500],board_mm=[1220,900,20],
                physical_fabrication_validated=False,visual_inspection_status='PENDING',
                pending=['Actual hinges, screws, load capacity and swing interference',
                         'Rear backing, mounting, picture protection and fastener clearance',
                         'Stock species, grain integrity, thickness, moisture and movement',
                         'Fit coupons and nominal zero-clearance joint tolerances',
                         'CAM pocket union, open-edge overrun and cutter compensation',
                         'Workholding, tabs/onion skin, feeds/speeds and final manufacturing approval'])


def write_manifests(doc):
    ents=list(doc.modelspace());pmap={meta(e)['part_id']:meta(e) for e in ents if e.dxf.layer=='CUT_THROUGH'}
    def emit(name,rows):
        with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    emit('parts_manifest.csv',[dict(part_id=pid,length_mm=d['length_mm'],width_mm=d['width_mm'],thickness_mm=20,
         nest_x_mm=d['nesting_origin'][0],nest_y_mm=d['nesting_origin'][1],assembly_group=d['assembly_group'],
         A_face_in_assembly=d['assembly_face_A'],grain_axis='X',assembly_affine=json.dumps(d['assembly_map']),
         pocket_count=sum(meta(e).get('part_id')==pid and e.dxf.layer=='POCKET_10MM' for e in ents)) for pid,d in pmap.items()])
    emit('pocket_manifest.csv',[dict(part_id=d['part_id'],feature_id=d['feature_id'],joint=d['joint'],pair_id=d['joint_id'],
         u0_mm=d['local_rect'][0],v0_mm=d['local_rect'][1],length_mm=d['local_rect'][2],width_mm=d['local_rect'][3],
         depth_mm=10,seat=d['seat'],mate_part_id=d['mate_part_id'],mate_feature_id=d['mate_feature_id'],
         open_edges=';'.join(d['open_edges']),A_face_in_assembly=pmap[d['part_id']]['assembly_face_A'],dxf_handle=e.dxf.handle)
         for e in ents if e.dxf.layer=='POCKET_10MM' for d in [meta(e)]])
    emit('dogbone_manifest.csv',[dict(part_id=d['part_id'],feature_id=d['feature_id'],parent_pocket=d['parent_pocket'],
         center_u_mm=d['local_center'][0],center_v_mm=d['local_center'][1],radius_mm=3.2,depth_mm=10,
         intent='UNION_WITH_PARENT_POCKET',dxf_handle=e.dxf.handle)
         for e in ents if e.dxf.layer=='DOGBONE' for d in [meta(e)]])
    emit('hardware_reference_manifest.csv',[dict(hardware_id=d['hardware_id'],hardware_type=d['hardware_type'],part_id=d['part_id'],
         layer=e.dxf.layer,production_machining=False,front_face_position_only=True,depth_ref_mm=d.get('depth_ref_mm','UNSPECIFIED'),
         dxf_handle=e.dxf.handle) for e in ents if meta(e).get('kind')=='hardware_ref' and meta(e).get('view')=='nest' for d in [meta(e)]])

def add_details():
    positions={'J1':(1900,490),'J2':(2170,490),'J3':(1900,280),'J4':(2170,280)}
    for j,(ox,oy) in positions.items():
        common={'detail':j,'view':'detail'}
        def tx(s,x,y,h=3.8,align='left',layer='NOTES'):
            return text(MSP,s,(ox+x,oy+y),h,layer,align,**common)
        def rr(x,y,w,h,role='body',**kw):
            return rect(MSP,ox+x,oy+y,w,h,'JOINT_DETAILS_REF',role=role,**common,**kw)
        def pp(pts,role='body',**kw):
            return poly(MSP,[(ox+x,oy+y) for x,y in pts],'JOINT_DETAILS_REF',role=role,**common,**kw)
        rect(MSP,ox,oy,240,190,'NOTES',kind='detail_border',**common)
        names={'J1':'FIXED FRAME HALF-LAP','J2':'SASH HALF-LAP',
               'J3':'LATTICE CROSSING HALF-LAP','J4':'LATTICE-TO-SASH SEAT'}
        tx(f'{j}  {names[j]}',10,178,7)
        n=40 if j=='J1' else 30 if j=='J2' else 10
        tx(f'{n} x {n} pocket / depth 10 / stock 20',10,164,4.7)
        if j in ('J1','J2'):
            fam1,fam2=('F01','F02') if j=='J1' else ('S01','S02')
            by=97 if j=='J1' else 107
            tx(f'{fam1} / A -> FRONT',15,148,4)
            tx(f'{fam2} / A -> BACK (flip)',135,148,3.6)
            rr(15,by,80,n); rr(135,by,80,n)
            rr(15,by,n,n,'pocket'); rr(135,by,n,n,'pocket')
            dimh(MSP,ox+15,ox+15+n,oy+by,oy+by-9,str(n),detail=j)
            dimv(MSP,oy+by,oy+by+n,ox+95,ox+104,str(n),detail=j)
            dimh(MSP,ox+135,ox+135+n,oy+by,oy+by-9,str(n),detail=j)
            # Section schematic: complementary retained halves at their overlap.
            sx=70; sy=36
            pp([(sx,sy),(sx+20+n,sy),(sx+20+n,sy+10),(sx+20,sy+10),
                (sx+20,sy+20),(sx,sy+20)],'section_back')
            pp([(sx+20,sy+10),(sx+20+n,sy+10),(sx+20+n,sy),
                (sx+40+n,sy),(sx+40+n,sy+20),(sx+20,sy+20)],'section_front')
            dimv(MSP,oy+sy,oy+sy+20,ox+sx+40+n,ox+sx+50+n,'20',detail=j)
            dimv(MSP,oy+sy+10,oy+sy+20,ox+sx+20+n,ox+sx+66+n,'10 depth',detail=j)
            tx('ASSEMBLED SECTION - complementary faces',15,69,4)
            tx('Local end regions only; open edges need cutter overrun in CAM.',10,18,3.3)
        elif j=='J3':
            tx('L01 / A -> FRONT',15,148,4)
            tx('L02 / A -> BACK (flip)',135,148,3.7)
            rr(15,125,80,10);rr(135,125,80,10)
            rr(50,125,10,10,'pocket');rr(170,125,10,10,'pocket')
            dimh(MSP,ox+50,ox+60,oy+125,oy+112,'10',detail=j)
            dimv(MSP,oy+125,oy+135,ox+95,ox+105,'10',detail=j)
            dimh(MSP,ox+170,ox+180,oy+125,oy+112,'10',detail=j)
            tx('16 crossings x 2 matching pockets = 32 pockets',15,95,4.2)
            sx=85;sy=40
            rr(sx+20,sy,10,10,'section_back')
            pp([(sx,sy),(sx+20,sy),(sx+20,sy+10),(sx+30,sy+10),
                (sx+30,sy),(sx+50,sy),(sx+50,sy+20),(sx,sy+20)],'section_front')
            dimv(MSP,oy+sy,oy+sy+20,ox+sx+50,ox+sx+60,'20',detail=j)
            dimv(MSP,oy+sy+10,oy+sy+20,ox+sx+30,ox+sx+76,'10 depth',detail=j)
            tx('ASSEMBLED SECTION - front and back remain flush',15,75,4)
            tx('Slots span the entire 10 mm bar width. No closed-side dogbones.',10,18,3.3)
        else:
            tx('S02 receiver / A -> BACK',15,148,3.9)
            tx('L01 end / A -> FRONT',135,148,3.9)
            rr(15,107,80,30);rr(135,117,70,10)
            rr(45,127,10,10,'pocket');rr(135,117,10,10,'pocket')
            for cx in (45,55):
                circle_poly(MSP,ox+cx,oy+127,R,'JOINT_DETAILS_REF',
                            role='dogbone',**common,radius_mm=R)
            dimh(MSP,ox+45,ox+55,oy+127,oy+116,'10',detail=j)
            dimv(MSP,oy+127,oy+137,ox+95,ox+105,'10',detail=j)
            dimh(MSP,ox+135,ox+145,oy+117,oy+105,'10',detail=j)
            tx('2 x R3.2 at closed corners; union with nominal pocket',15,82,3.7)
            sx=83;sy=35
            pp([(sx,sy),(sx+20,sy),(sx+20,sy+10),(sx+30,sy+10),
                (sx+30,sy+20),(sx,sy+20)],'section_front')
            pp([(sx+20,sy),(sx+55,sy),(sx+55,sy+20),(sx+30,sy+20),
                (sx+30,sy+10),(sx+20,sy+10)],'section_back')
            dimv(MSP,oy+sy,oy+sy+20,ox+sx+55,ox+sx+65,'20',detail=j)
            dimv(MSP,oy+sy+10,oy+sy+20,ox+sx+30,ox+sx+81,'10 depth',detail=j)
            tx('ASSEMBLED SECTION / 10 mm engagement',15,67,4)
            tx('S01 + L02 is the face-reversed equivalent. 24 end joints total.',10,18,3.4)
        tx('REFERENCE ONLY / DXF 1:1 / PNG enlarged',10,7,3.2)
    return positions



def render_details(doc,positions):
    im=Image.new('RGB',(4400,3840),COL['white']);d=ImageDraw.Draw(im)
    label(d,(120,65),'02  JOINERY DETAILS',65,bold=True)
    label(d,(120,153),'Closed pocket geometry  |  All wood 20 mm thick  |  Pocket depth 10 mm  |  Exact R3.2 relief arcs',31,fill=COL['muted'])
    d.line((120,220,4280,220),fill=COL['border'],width=3)
    viewports={'J1':(100,280,2040,1615),'J2':(2260,280,2040,1615),
               'J3':(100,1960,2040,1615),'J4':(2260,1960,2040,1615)}
    for j,(ox,oy) in positions.items():
        vp=viewports[j];r=Renderer(im,(ox,oy,ox+240,oy+190),vp)
        ents=[e for e in doc.modelspace() if meta(e).get('detail')==j]
        # All geometry is read from the reference detail regions in the final DXF.
        r.entities(ents)
    y=3650
    legend=[(COL['pocket'],'10 mm pocket'),(COL['dog'],'R3.2 relief'),
            (COL['front'],'retained front half'),(COL['back'],'retained back half')]
    x=160
    for c,s in legend:
        d.rectangle((x,y,x+43,y+43),fill=c,outline=COL['line'],width=2)
        label(d,(x+65,y+3),s,29);x+=1015
    label(d,(120,3750),'Detail geometry stays 1:1 in DXF Model Space. Only this PNG view is enlarged. Dimensions are millimetres.',27,fill=COL['muted'])
    im.save(OUT/'02_joinery_details.png',dpi=(220,220));return im



def nest_entities(doc,full=True):
    ents=list(doc.modelspace());out=[]
    if full:out += [e for e in ents if e.dxf.layer=='BOARD_BOUNDARY']
    for lay in ['CUT_THROUGH','POCKET_10MM','DOGBONE','HINGE_REF','LATCH_REF','PART_ID']:
        out += [e for e in ents if e.dxf.layer==lay and (lay in ['CUT_THROUGH','POCKET_10MM','DOGBONE'] or meta(e).get('view')=='nest')]
    if full:out += [e for e in ents if meta(e).get('view')=='nest' and e.dxf.layer in ['GRAIN_DIRECTION','NOTES','DIMENSIONS'] and meta(e).get('kind')!='title']
    return out


def render_nesting(doc,report):
    im=Image.new('RGB',(4400,4280),COL['white']);d=ImageDraw.Draw(im)
    label(d,(120,65),'01  ONE-BOARD NESTING / PORTRAIT DOUBLE LEAF',61,bold=True)
    label(d,(120,155),'1220 x 900 x 20 mm  |  CNC face A  |  463 W x 586 H assembled  |  All part lengths parallel to +X grain',28,fill=COL['muted'])
    d.line((120,225,4280,225),fill=COL['border'],width=3)
    r=Renderer(im,(-45,-52,1240,946),(90,280,3000,2370));r.entities(nest_entities(doc,True))
    x,y,w=3190,310,980
    label(d,(x,y),'SAVED DXF CHECKED',33,bold=True);y+=75
    for value,desc in [('24','independent wooden parts'),('104','closed nominal pocket contours'),('48','exact R3.2 relief contours'),('52','matching half-lap joint pairs')]:
        label(d,(x,y),value,66,bold=True);label(d,(x+165,y+25),desc,25);y+=118
    y+=20;d.line((x,y,x+w,y),fill=COL['border'],width=3);y+=43
    label(d,(x,y),'LAYER / MACHINING INTENT',30,bold=True);y+=70
    for col,ttl,sub in [(COL['wood'],'CUT_THROUGH','20 mm nominal full-depth outer profile'),
                        (COL['pocket'],'POCKET_10MM','10 mm deep from common A face'),
                        (COL['dog'],'DOGBONE','10 mm deep; union with parent seat'),
                        (COL['hardware'],'HINGE_REF / LATCH_REF','Reference only. EXCLUDE FROM CAM.')]:
        d.rectangle((x,y,x+40,y+40),fill=col,outline=COL['line'],width=2)
        label(d,(x+62,y),ttl,27,bold=True)
        label(d,(x+62,y+44),sub,24,fill=COL['muted']);y+=116
    y+=25;label(d,(x,y),'ASSEMBLY FACE ORIENTATION',29,bold=True);y+=62
    for s in ['F01 / S01 / L01: A faces FRONT.',
              'F02 / S02 / L02: flip after cutting; A faces BACK.',
              'Minimum stock edge margin: 20 mm.',
              'Minimum between-part gap: 12 mm.',
              'Cut-zone envelope: X20-1081 / Y20-326.',
              'Open-edge laps need waste-side cutter overrun.',
              'No tabs, toolpaths, feeds or speeds included.']:
        y=wrapped(d,s,(x,y),w,26);y+=20
    label(d,(120,2760),'CUT-ZONE ENLARGEMENT / SAME 24 PARTS',45,bold=True)
    label(d,(120,2830),'A second viewport of the saved DXF, not additional parts. Pocket and relief positions are taken from CAD entities.',27,fill=COL['muted'])
    d.rounded_rectangle((95,2900,4300,4140),radius=18,fill=COL['panel'],outline=COL['border'],width=2)
    rr=Renderer(im,(0,0,1110,345),(130,2920,4120,1200));rr.entities(nest_entities(doc,False))
    label(d,(120,4180),'NOMINAL GEOMETRY ONLY  |  Fit coupons, actual hardware and CAM setup require approval before production.',27,fill=COL['muted'])
    im.save(OUT/'01_one_board_nesting.png',dpi=(220,220))


def render_closeup(doc):
    im=Image.new('RGB',(4400,1850),COL['white']);d=ImageDraw.Draw(im)
    label(d,(110,60),'05  ALL POCKETS / CUT-ZONE CLOSEUP',58,bold=True)
    label(d,(110,145),'Same 24 parts at increased viewing scale  |  104 nominal pockets + 48 reliefs  |  Closed DXF contours',28,fill=COL['muted'])
    Renderer(im,(0,0,1110,346),(100,245,4200,1400)).entities(nest_entities(doc,False))
    label(d,(110,1720),'Part labels are annotations, not engraving. Dashed hardware outlines are references, not approved machining.',28,fill=COL['muted'])
    im.save(OUT/'05_all_pockets_closeup.png',dpi=(220,220))


def render_assembly(doc):
    im=Image.new('RGB',(3600,3950),COL['white']);d=ImageDraw.Draw(im)
    label(d,(105,62),'03  ASSEMBLY / PORTRAIT DOUBLE LEAF',59,bold=True)
    label(d,(105,151),'463 W x 586 H overall  |  Two 187 W x 500 H leaves  |  One A3 portrait picture behind both leaves',27,fill=COL['muted'])
    d.line((105,225,3495,225),fill=COL['border'],width=3)
    ox,oy=ASSEMBLY_ORIGIN
    r=Renderer(im,(ox-48,oy-63,ox+519,oy+630),(70,290,2590,2980))
    ents=[e for e in doc.modelspace() if meta(e).get('view')=='assembly' and meta(e).get('kind')!='title'
          and not (e.dxftype()=='TEXT' and e.dxf.text.startswith('LEFT-RIGHT DOUBLE'))]
    r.entities([e for e in ents if meta(e).get('role')=='picture'])
    r.entities([e for e in ents if meta(e).get('role')=='body'])
    r.entities([e for e in ents if meta(e).get('role') not in ['body','picture']])
    x,y,w=2760,360,700
    label(d,(x,y),'DESIGN SCHEDULE',30,bold=True);y+=72
    for ttl,body in [('A3 PORTRAIT','297 W x 420 H mm. A single picture stays on the fixed rear support.'),
                     ('PICTURE REGION','317 W x 440 H mm. 10 mm allowance around the artwork.'),
                     ('EACH LEAF OPENING','127 W x 440 H before lattice subdivision.'),
                     ('LATTICE','Per leaf: 2 vertical + 4 horizontal bars, making 8 flush crossings.'),
                     ('CENTRE MEETING','30 + 3 + 30 = 63 mm. The two centre stiles move with their own leaves.'),
                     ('NO FIXED MULLION','Opening both leaves removes the centre stiles from the picture front.')]:
        label(d,(x,y),ttl,25,bold=True);y+=43
        y=wrapped(d,body,(x,y),w,27);y+=41
    d.line((x,y,x+w,y),fill=COL['border'],width=3);y+=44
    label(d,(x,y),'REFERENCE HARDWARE',28,bold=True);y+=62
    for s in ['4 hinges: 2 on each outside edge. Height centres Y=103 and 483 mm.',
              '2 handles and 2 independent catches. No centre-post latch required.',
              'Hinge geometry, fasteners, rear backing and actual swing remain unapproved.']:
        y=wrapped(d,s,(x,y),w,26);y+=29
    d.rounded_rectangle((110,3420,3490,3800),radius=18,fill=COL['panel'],outline=COL['border'],width=2)
    label(d,(160,3460),'IMPORTANT DISTINCTION',32,bold=True)
    label(d,(160,3525),'317 x 440 is the rear picture region, NOT one unobstructed opening when the leaves are closed.',28)
    label(d,(160,3585),'F01 / S01 / L01: A -> FRONT     |     F02 / S02 / L02: FLIP A -> BACK',29,bold=True)
    label(d,(160,3650),'A3 outline: dash-dot. Picture region and leaf openings: dashed. All are non-machining references.',27,fill=COL['muted'])
    label(d,(160,3710),'The picture and a separate non-wood backing are not attached to the moving leaves.',27,fill=COL['muted'])
    label(d,(110,3850),'Wooden members are transformed from the verified DXF cut geometry. Hardware models are not selected.',26,fill=COL['muted'])
    im.save(OUT/'03_assembly_reference.png',dpi=(220,220))


def render_opening(doc):
    im=Image.new('RGB',(4000,2750),COL['white']);d=ImageDraw.Draw(im)
    label(d,(110,60),'04  LEFT-RIGHT OPENING / PLAN REFERENCE',61,bold=True)
    label(d,(110,152),'Looking down from above  |  Both leaves open toward the viewer  |  Fixed rear picture  |  No centre mullion',28,fill=COL['muted'])
    d.line((110,225,3890,225),fill=COL['border'],width=3)
    ox,oy=OPENING_ORIGIN
    r=Renderer(im,(ox-20,oy-94,ox+485,oy+321),(110,285,2720,2190))
    r.entities([e for e in doc.modelspace() if meta(e).get('view')=='opening'])
    x,y,w=2970,365,875
    for ttl,s in [('ILLUSTRATION ONLY','The 90-degree plan uses provisional front-projecting axes to explain the opening direction. It is not a selected hinge model.'),
                  ('VERTICAL HINGE AXES','Two hinges on the LEFT outside edge, two on the RIGHT. Not top/bottom hinges and not a folding door.'),
                  ('FIXED PICTURE','One 297 x 420 mm portrait picture remains on a separate rear support. The setback shown is illustrative.'),
                  ('BEFORE PRODUCTION','Check actual hinge pin offsets, leaf thickness, fasteners, load capacity, backing clearance and both leaves moving together.')]:
        label(d,(x,y),ttl,29,bold=True);y+=57
        y=wrapped(d,s,(x,y),w,29);y+=66
    label(d,(115,2580),'REFERENCE ONLY / Actual hinge dimensions, screws, loads and dynamic collision checks remain PENDING.',29,bold=True)
    label(d,(115,2650),'No illustration on this sheet is a production pocket or a CNC toolpath.',27,fill=COL['muted'])
    im.save(OUT/'04_opening_reference.png',dpi=(220,220))


def write_readme(report):
    textout=f'''A3 세로형 한식 양개 창호 — 최신 CNC 패키지 / PORTRAIT_DL_R1
================================================================
이 폴더만 최신 제작 기준입니다. 03_reference_history와 혼합하지 마십시오.
정면은 폭 W x 높이 H, 부품은 길이 L x 폭 B x 두께 T입니다. 단위 mm.
실제 저장 DXF 재읽기: {report['status']} / {report['checks_passed']}개 검사 PASS.
이 PASS는 명목 CAD geometry 검사이지 실제 제작·하중·개폐 승인서가 아닙니다.

1. 규격
- 완성 외곽 W463 x H586; 고정틀 폭40, 내부383 x506.
- 좌우 창짝 각각 W187 x H500; 창짝 테두리 폭30.
- 바깥 고정틀 간극3, 중앙 간극3. 중앙 고정 기둥 없음.
- 각 창짝 창살 설치 개구부127 x440, 세로살2/가로살4.
- 후면 그림 배치 기준영역317 x440, A3 세로형297 x420, 사방10 여유.
- 닫힌 정면의 연속 개구부가317 x440이라는 뜻이 아님.
- 중앙 폭63=세로재30+틈3+세로재30. 양쪽을 열면 중앙 세로재도 이동.
- 원판1220 x900 x20. 원판의1220방향(+X)이 목리, 모든 긴 부품이 X평행.
- 공구 기준 Ø6, 명목 pocket깊이10, 도그본R3.2, 관통 명목깊이20.

2. 부품표 / L x B x T
F01 고정틀 세로재 586 x40 x20 : 2개
F02 고정틀 가로재 463 x40 x20 : 2개
S01 창짝 세로재   500 x30 x20 : 4개
S02 창짝 가로재   187 x30 x20 : 4개
L01 세로 창살     460 x10 x20 : 4개
L02 가로 창살     147 x10 x20 : 8개
합계24개. 모든 부품에 별도의 ID annotation과 XDATA 메타데이터가 존재합니다.
최소 원판 여유20, 최소 부품 간격12. 부품 외접범위 X20~1081/Y20~326.

3. 가공 layer
BOARD_BOUNDARY : 원판 외곽, 절삭 금지.
CUT_THROUGH : 24개 closed LWPOLYLINE, 20두께 관통 외곽.
POCKET_10MM : 104개 closed LWPOLYLINE, A면에서 깊이10.
DOGBONE : 48개 exact circular-bulge closed LWPOLYLINE, 깊이10.
HINGE_REF : 경첩4개, 각 고정틀/창짝 날개 위치만 참고. 생산 가공 제외.
LATCH_REF : 손잡이2개/캐치2개 위치만 참고. 생산 가공 제외.
PART_ID : 부품ID. 새김가공 아님.
DIMENSIONS : 치수. 가공 금지.
GRAIN_DIRECTION : 목리방향. 가공 금지.
ASSEMBLY_REFERENCE : 조립/열림 참고. 가공 금지.
JOINT_DETAILS_REF : J1/J2/J3/J4 상세. 가공 금지.
NOTES : 제작 주석. 가공 금지.
DXF Model Space1:1, INSUNITS=mm. 모든 생산 contour의 Z=0이며 깊이는 layer/metadata에서 구분합니다.
CAM에서는 CUT_THROUGH, POCKET_10MM, DOGBONE만 명시적으로 선택하십시오.

4. 홈 수량과 실제 결합
J1 고정틀40 x40 x깊이10: 8홈, 4쌍.
J2 창짝30 x30 x깊이10: 16홈, 8쌍.
J3 창살10 x10 x깊이10: 32홈, 16개 교차점.
J4 끝단/안착10 x10 x깊이10: 48홈(끝단24+안착24), 24쌍.
총104개 기본 pocket / 52쌍의 결합. 도그본48개는 별도 집계.
S01 각각 안착4개; S02 각각 안착2개. 모든 창살 양 끝에 끝단 반턱2개.

5. A면 가공과 조립 시 뒤집기 — 매우 중요
원판의 공통 위쪽을 가공면A로 하여 pocket/도그본을 모두 한 면에서 가공합니다.
F01/S01/L01: 완성품에서 A면은 FRONT.
F02/S02/L02: 가공 후 뒤집어 완성품에서 A면은 BACK.
완성품 뒤z=0, 앞z=20. FRONT부품은 앞쪽z10~20을 제거,
BACK부품은 뒤쪽z0~10을 제거하여 잔존10씩이 상보적으로 맞물립니다.
모든 부품의 A면을 앞쪽으로 향하게 조립하면 안 됩니다.
좌우/상하의 정확한 조립 변환은 parts_manifest.csv의 affine에 기록됩니다.
XY 미러 그림만을 실제 뒤집기라고 오해하지 마십시오.

6. 도그본 및 개방 경계 CAM intent
모든 S01/S02 안착 pocket은 로컬 v=20~30이며 v=30쪽으로 개방됩니다.
닫힌 코너(u_min,20),(u_max,20)에 R3.2원2개를 사용합니다.
POCKET_10MM 사각형과 해당 DOGBONE 2개의 합집합을 같은 깊이10으로 제거합니다.
도그본을 관통구멍이나 남겨둘 island로 처리하지 마십시오.
원은 true semicircle bulge2개를 가진 폐곡선이며 단순 참조 원이 아닙니다.
이 설계의 J1/J2/J3 및 끝단 pocket들은 전폭 또는 끝단 개방형 반턱입니다.
사각 pocket이 부품 경계에 닿는 면에서는 Ø6공구가 폐기재 쪽으로 넘어가며
어깨까지 가공할 수 있도록 CAM의 개방 경계/진입/연장 조건을 설정해야 합니다.
일반 닫힌 내부pocket 경로만 쓰면 일부 모서리에 잔재가 남을 수 있습니다.
104개 홈의 open_edges는 pocket_manifest.csv에 기록했습니다.
CAD 사각형은 부품 내부에 두고 실제 연장 toolpath는 CAM 담당자가 확정합니다.
관통컷과 pocket의 의도된 경계 공유는 중복 contour가 아닙니다.

7. 하드웨어와 후판
경첩4개: LEFT S01-1/F01-1, RIGHT S01-4/F01-2 각각2개.
기준 높이Y=103,483. 약40길이/약2깊이, 예시날개폭14는 REFERENCE ONLY.
폭14는 참고 위치를 보이기 위한 도형이며 실제 경첩 폭·구멍 치수가 아닙니다.
손잡이 참고중심(215,293),(248,293). 캐치 각창짝/고정틀에 독립1개씩.
그림 한 장과 별도 비목재 후판은 고정틀 뒤에 고정하며 창짝에 붙이지 않습니다.
그림이 창살에 닿지 않도록 실제 후방 이격과 지지방식을 확정하십시오.
현재 목재24개만으로 그림을 고정하거나 벽에 안전하게 설치할 수 있다는 뜻이 아닙니다.
후판/마운트/클립/벽고정/접착제/나사/경첩/캐치 등 별도 자재가 필요합니다.
열림 참고도의 (X,Z)=(41.5,24),(421.5,24)는 방향설명용 가상축입니다.
실제 경첩/후판/나사/두창짝의 동시회전 간섭, 하중, 90도열림은 검증미완(PENDING).
HINGE_REF/LATCH_REF를 현재 A면 가공프로그램에 포함하지 마십시오.
특히 BACK조립 부품의 하드웨어 앞면 위치가 A면 가공허용을 뜻하지 않습니다.

8. 가공·조립 순서
(1) 실제 원판 평탄도/두께/결함/목리/함수율/공구경을 확인하고 시험편으로 끼움공차 확정.
(2) 목리+X 유지, A면표시. 좁은10폭 창살이 흔들리지 않는 고정/지그/CAM방식 확정.
(3) 고정상태에서 pocket과 도그본 합집합을 먼저 깊이10 가공.
(4) 관통컷은 마지막에 실행하여 부품을 분리. 탭/얇은잔존층 등은 CAM에서 정함.
(5) 실제 부품에 ID/A면/좌우소속을 임시표시. PART_ID는 자동새김 경로가 아님.
(6) 고정틀 반턱4쌍을 가조립. 수평·직각·대각·두께를 확인.
(7) 각창짝의 L01/L02격자를 반턱으로 가조립하고 테두리안착에 넣어 맞춤 확인.
(8) 격자를 넣기 전에 테두리를 영구고정하지 말 것. 모든 홈방향/앞뒤를 맞출 것.
(9) 적합한 접착/체결방식을 작업자가 확정하여 고정틀과 각창짝을 고정.
(10) 실물경첩·캐치·손잡이를 선정하고 제품치수로 hardware별도도면을 수정한 뒤 설치.
(11) 기본3간극, 뒤틀림, 두창짝의 개폐순서/간섭/처짐을 실제확인.
(12) 별도 후판/그림/보호층/벽고정을 설치하고 나사 및 창살과의 간섭을 확인.
반턱은 위치를 기계적으로 안착시키지만 접착/체결 없이 분리되지 않는 잠금조인트는 아닙니다.
실내용 장식/그림보호용 명목설계입니다. 외기밀/수밀/유리받침/구조인증 창호가 아닙니다.

9. 검증과 한계
실제로 생성한 DXF를 저장한 뒤 ezdxf로 다시 읽어 {report['checks_passed']}개 검사 PASS.
검사: 부품24, pocket104, 도그본48, 크기/위치/폐곡선/층/목리/12간격/20여유,
52쌍XY와앞뒤면/Z잔존영역, 의도치않은 재료겹침, 각부품의 조립참고 일치,
경첩4/손잡이2/캐치2 위치참고, DXF audit.
검증을 통과한 파일의 SHA256은 validation_report.json에 기록됩니다.
곡선포함 재료검사는 0.00001 mm 이하허용값으로 평탄화한 다각형 계산이며
반경/원호/bulge/내부포함은 별도로 DXF 원데이터에서도 확인합니다.
실제 가공맞춤·목재강도·동적개폐·벽고정·CAM시뮬레이션·기계운전은 승인하지 않았습니다.
기본10.00홈/10.00부품은 명목 무공차이며 시험편 후 공차보정이 필요합니다.

10. 파일
hanok_window_A3_portrait_double_leaf_one_board_CNC.dxf : 최신 실제 DXF
01_one_board_nesting.png : 원판 전체 및 동일부품확대
02_joinery_details.png : J1/J2/J3/J4 및 깊이단면
03_assembly_reference.png : 세로형 양개 닫힘정면
04_opening_reference.png : 좌우열림 설명용 평면도 (REFERENCE ONLY)
05_all_pockets_closeup.png : 104홈/48도그본 위치 확대
validation_report.json : 실제저장DXF 재읽기검증
parts_manifest.csv / pocket_manifest.csv / dogbone_manifest.csv : 치수·좌표·대응표
hardware_reference_manifest.csv : 참고하드웨어만 분리집계
build_portrait_double_leaf.py / cad_helpers.py / design_spec.json : 재생성·검증소스
requirements.txt : 사용한Python라이브러리 버전

재실행: 이폴더에서 python build_portrait_double_leaf.py
기존DXF 검사만: python build_portrait_double_leaf.py --validate-only
검사전용 결과는 validation_report_recheck.json이며 기존 PNG를 다시 만들지 않습니다.
필요폰트가 없으면 시스템DejaVu/Arial을 사용하며, HANOK_FONT 환경변수로 대체가능.
이패키지에는 폰트파일을 포함하지 않습니다.
'''
    (OUT/'README.txt').write_text(textout,encoding='utf-8')
    import shapely,PIL
    (OUT/'requirements.txt').write_text(f'ezdxf=={ezdxf.__version__}\nshapely=={shapely.__version__}\nPillow=={PIL.__version__}\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validate-only',action='store_true')
    args=parser.parse_args()
    if args.validate_only:
        if not DXF.is_file():raise FileNotFoundError(DXF)
        doc=ezdxf.readfile(DXF);rep=validate(doc,'READ_BACK_FROM_SAVED_DXF')
        rep.update(file=DXF.name,sha256=hashlib.sha256(DXF.read_bytes()).hexdigest())
        (OUT/'validation_report_recheck.json').write_text(json.dumps(rep,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    else:
        doc,rep,positions=build()
        render_nesting(doc,rep);render_details(doc,positions);render_assembly(doc);render_opening(doc);render_closeup(doc)
        write_readme(rep)
    print(json.dumps({k:rep[k] for k in ['status','checks_passed','saved_dxf_reread','parts_total','nominal_pockets_total','dogbone_reliefs_total','mated_joints_total','minimum_part_gap_mm','minimum_board_margin_mm']},indent=2))

if __name__=='__main__':main()
