#!/usr/bin/env python3
"""Create and re-read-validate the PORTRAIT double-leaf CNC design geometry.

Every dimension in this file comes from design_parameters.json through
generate_spec.derive, so the spec writer, the drawings and the validator all
read one set of numbers. Editing a parameter and re-running is the only
supported way to change the design; nothing here is hand-tuned to a size.

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
from numeric_policy import (POLICY_VERSION, LENGTH_TOL_MM, RATIO_TOL, AREA_TOL_MM2,
                            VOLUME_TOL_MM3, ARC_CHORD_TOL_MM, close, coordinates_match,
                            geometry_matches, polyline_arcs, policy_record)
from machining_checks import measure_machining
from generate_spec import (build as build_spec, derive, bar_offsets, leaf_bounds,
                           opening_bounds, group_name)

# Reproducible output. Without this, ezdxf stamps the save time into $TDCREATE
# and $TDUPDATE, issues fresh $VERSIONGUID and $FINGERPRINTGUID values, and dates
# its own written-by marker, so two builds of identical geometry hash
# differently and package_manifest.json cannot tell a rebuild from an edit. The
# option only substitutes constants for those provenance fields; no geometry,
# layer or metadata content is affected. The revision travels in document
# metadata and on the sheet instead - see pin_build_identity.
ezdxf.options.write_fixed_meta_data_for_testing=True

OUT=Path(__file__).resolve().parent
DXF=OUT/'hanok_window_A3_portrait_double_leaf_one_board_CNC.dxf'
SPEC=OUT/'design_spec.json'
TOL=LENGTH_TOL_MM
PARAMS=json.loads((OUT/'design_parameters.json').read_text(encoding='utf-8'))
D=derive(PARAMS)
ASSEMBLY_ORIGIN=(1350.,100.)
OPENING_ORIGIN=(1350.,-370.)

# Named shorthands for the derived design. No literal millimetre value appears
# below this block; change design_parameters.json instead.
W,H=D['board_w'],D['board_h']
FW,SM,BW,LAP=D['frame_member'],D['leaf_member'],D['bar_width'],D['end_lap']
LW,LH=D['leaf_w'],D['leaf_h']
MINR=PARAMS['leaf']['min_height_to_width_ratio']
LY0,LY1=D['leaf_y0'],D['leaf_y1']
OW,OH=D['open_w'],D['open_h']
PX,PY=D['picture_x0'],D['picture_y0']
PRW,PRH=D['picture_region_w'],D['picture_region_h']
A3W,A3H=PARAMS['picture']['sheet_width'],PARAMS['picture']['sheet_height']
PMG=PARAMS['picture']['region_margin']
DEPTH,THK,R=D['pocket_depth'],D['thickness'],D['relief_radius']
NLEAF,NV,NH=D['leaf_count'],D['n_vertical'],D['n_horizontal']
GAP_OUT,GAP_MID=PARAMS['clearance']['frame_to_leaf'],PARAMS['clearance']['leaf_to_leaf']
BL,BWD,BT=PARAMS['stock']['length'],PARAMS['stock']['width'],PARAMS['stock']['thickness']
MARGIN,PGAP=PARAMS['stock']['edge_margin'],PARAMS['stock']['part_gap']
LEAVES=[leaf_bounds(D,i) for i in range(NLEAF)]
OPENINGS=[opening_bounds(D,i) for i in range(NLEAF)]
SIZES={k:(D['part_lengths'][k],D['part_widths'][k],D['part_counts'][k]) for k in D['part_lengths']}
NPART=sum(D['part_counts'].values())
# J1 frame corners, J2 sash corners, J3 lattice crossings, J4 lattice ends and seats.
NPOCK={'J1':8,'J2':8*NLEAF,'J3':2*D['crossings_total'],'J4':4*NLEAF*(NV+NH)}
NPOCKT=sum(NPOCK.values())
NSEAT=2*NLEAF*(NV+NH)
NDOG=2*NSEAT
POCKET_LAYER=f'POCKET_{DEPTH:g}MM'
LAYERS={'BOARD_BOUNDARY':(8,35),'CUT_THROUGH':(7,35),POCKET_LAYER:(30,25),
        'DOGBONE':(6,25),'HINGE_REF':(4,18),'LATCH_REF':(4,18),
        'PART_ID':(7,18),'DIMENSIONS':(3,18),'GRAIN_DIRECTION':(3,35),
        'ASSEMBLY_REFERENCE':(8,18),'JOINT_DETAILS_REF':(8,18),'NOTES':(7,18)}


def load_spec():
    """Regenerate from the parameters so design_spec.json and the DXF cannot drift.

    Nothing is written here; build() replaces design_spec.json together with the
    DXF only after both validation phases pass.
    """
    s=build_spec(PARAMS)
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
             thickness_mm=THK,depth_mm=THK,nesting_origin=[x,y],
             assembly_map=p['assembly_transform'],assembly_face_A=p['face_a'],
             assembly_group=p['assembly_group'],machining_face='A')
    rect(m,x,y,L,B,'CUT_THROUGH',**dat)
    # IDs are annotations, not engraving operations. For wide members the text
    # occupies the untouched lower band; lattice labels sit between slots.
    text(m,pid,(x+(L*.4 if p['kind']=='S01' else L/2),y+(B/2 if B==BW else B*.31)),3.4 if B==BW else 4.5,
         'PART_ID','center',kind='part_id',part_id=pid,view='nest')
    for q in s['pockets']:
        if q['part_id']!=pid: continue
        u0,v0,u1,v1=q['u0'],q['v0'],q['u1'],q['v1']
        edges=[]
        if abs(u0)<TOL: edges.append('U_MIN')
        if abs(u1-L)<TOL: edges.append('U_MAX')
        if abs(v0)<TOL: edges.append('V_MIN')
        if abs(v1-B)<TOL: edges.append('V_MAX')
        rect(m,x+u0,y+v0,u1-u0,v1-v0,POCKET_LAYER,
             kind='pocket',part_id=pid,feature_id=q['feature_id'],joint=q['joint'],
             joint_id=q['joint_pair_id'],mate_part_id=q['mate_part_id'],
             mate_feature_id=q['mate_feature_id'],seat=q['seat'],depth_mm=DEPTH,
             local_rect=[u0,v0,u1-u0,v1-v0],open_edges=edges,machining_face='A')
    for d in s['dogbones']:
        if d['part_id']!=pid:continue
        circle_poly(m,x+d['center_u'],y+d['center_v'],d['radius'],'DOGBONE',
                    kind='dogbone',part_id=pid,feature_id=d['feature_id'],
                    parent_pocket=d['parent_pocket'],depth_mm=DEPTH,radius_mm=d['radius'],
                    local_center=[d['center_u'],d['center_v']],
                    operation='UNION_WITH_PARENT_POCKET',machining_face='A')


def add_board(m,spec):
    tot=spec['derived']['totals'];top=spec['derived']['nesting_bounds'][3]
    rect(m,0,0,BL,BWD,'BOARD_BOUNDARY',kind='board',view='nest',size_mm=[BL,BWD,BT])
    text(m,'A3 PORTRAIT / DOUBLE-LEAF HANOK WINDOW',(0,BWD+55),13,kind='title',view='nest')
    # The saved header carries constant timestamps so builds stay reproducible;
    # this line is where a reader finds which revision the sheet actually is.
    text(m,f"REVISION {PARAMS['revision']} / {PARAMS['build_date']} / GENERATED FROM design_parameters.json",
         (BL,BWD+55),6,align='right',kind='revision',view='nest')
    text(m,f"{W:g} W x {H:g} H / {tot['parts']} PARTS / {tot['pockets']} POCKETS / "
           f"{tot['reliefs']} RELIEFS / mm / MODEL SPACE 1:1",(0,BWD+30),5.5,view='nest')
    dimh(m,0,BL,BWD,BWD+14,f'{BL:g}',view='nest')
    dimv(m,0,BWD,0,-27,f'{BWD:g}',view='nest')
    # The grain arrow and offcut labels sit in the band left empty above the parts.
    gy=top+(BWD-top)*.32; oy=top+(BWD-top)*.65
    line(m,(BL*.115,gy),(BL*.885,gy),'GRAIN_DIRECTION',view='nest')
    for sg in (1,-1):
        line(m,(BL*.885,gy),(BL*.885-44,gy+sg*21),'GRAIN_DIRECTION',view='nest')
    text(m,'GRAIN DIRECTION  +X',(BL/2,gy+45),19,'GRAIN_DIRECTION','center',view='nest')
    text(m,'UNUSED OFFCUT / NOT ADDITIONAL PARTS',(BL/2,oy),13,align='center',view='nest')
    text(m,f'All {tot["parts"]} part lengths run parallel to the {BL:g} mm grain direction.',
         (BL/2,oy-34),8,align='center',view='nest')
    notes=[f'ONE BOARD {BL:g} x {BWD:g} x {BT:g} / ALL POCKETS MACHINED FROM COMMON FACE A',
           'ASSEMBLY: F01 + S01 + L01 A->FRONT. F02 + S02 + L02 FLIP A->BACK.',
           f'{POCKET_LAYER} + DOGBONE: UNION, REMOVE {DEPTH:g} mm. OPEN LAPS NEED WASTE-SIDE OVERRUN.',
           'HINGE_REF / LATCH_REF ARE POSITION REFERENCES ONLY. DO NOT MACHINE.',
           'NOMINAL FIT: VERIFY STOCK, TEST COUPONS, WORKHOLDING AND CAM BEFORE CUTTING.']
    for i,s in enumerate(notes):text(m,s,(30,BWD-48-i*20),6.6,view='nest')
    text(m,'No G-code, tabs, toolpaths, feeds or speeds are included. All hardware and backing remain PENDING.',
         (0,-35),5.3,view='nest')


def hinge_axes():
    """Provisional vertical swing axes, midway between frame and leaf edges."""
    return [(FW+LEAVES[0][0])/2,(LEAVES[-1][2]+W-FW)/2]


def hinge_heights():
    inset=PARAMS['hardware_reference']['hinge_inset_from_leaf_end']
    return [LY0+inset,LY1-inset]


def meeting_stile_centres():
    """Centre line of each leaf's handle-side stile, away from its hinges."""
    return [LEAVES[0][2]-SM/2,LEAVES[-1][0]+SM/2]


def hardware_records():
    hw=PARAMS['hardware_reference'];out=[]
    ww,wi,hl=hw['wing_width'],hw['wing_inset'],hw['hinge_length']
    for side,pf,xf,ps,xs in [
            ('LEFT','F01-1',FW-wi-ww,'S01-1',LEAVES[0][0]+wi),
            ('RIGHT','F01-2',W-FW+wi,f'S01-{2*NLEAF}',LEAVES[-1][2]-wi-ww)]:
        for idx,y in enumerate(hinge_heights(),1):
            hid=f'H-{side}-{idx}'
            for pid,x,wing in [(pf,xf,'FIXED'),(ps,xs,'SASH')]:
                out.append(dict(hardware_id=hid,part_id=pid,layer='HINGE_REF',
                                box=[x,y-hl/2,x+ww,y+hl/2],hardware_type='HINGE',wing=wing,
                                depth_ref_mm=hw['hinge_depth_ref']))
    hx=meeting_stile_centres();hwd,hht=hw['handle_width'],hw['handle_height']
    cy=(LY0+LY1)/2
    for i,(x,pid) in enumerate(zip(hx,['S01-2',f'S01-{2*NLEAF-1}']),1):
        out.append(dict(hardware_id=f'HANDLE-{i}',part_id=pid,layer='LATCH_REF',
                        box=[x-hwd/2,cy-hht/2,x+hwd/2,cy+hht/2],hardware_type='HANDLE'))
    cs=hw['catch_size'];sy=LY1-hw['catch_inset_from_leaf_top']
    fy=H-FW+hw['catch_inset_from_frame_inner_top']
    for i,(x,ps) in enumerate(zip(hx,['S02-2',f'S02-{2*NLEAF}']),1):
        for pid,cc in [(ps,sy),('F02-2',fy)]:
            out.append(dict(hardware_id=f'CATCH-{i}',part_id=pid,layer='LATCH_REF',
                            box=[x-cs/2,cc-cs/2,x+cs/2,cc+cs/2],hardware_type='CATCH'))
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
    for x in hinge_axes():
        for y in hinge_heights():
            line(m,(ox+x,oy+y-THK-4),(ox+x,oy+y+THK+4),'HINGE_REF',view='assembly',
                 kind='hinge_location_ref',reference_only=True)


def add_assembly(m,parts):
    ox,oy=ASSEMBLY_ORIGIN
    text(m,f'PORTRAIT / W{W:g} x H{H:g}',(ox,oy+H+84),10,view='assembly',kind='title')
    text(m,f'{NLEAF}-LEAF LEFT-RIGHT DOUBLE LEAF / REFERENCE ONLY',(ox,oy+H+61),5,view='assembly')
    rect(m,ox+PX+PMG,oy+PY+PMG,A3W,A3H,'ASSEMBLY_REFERENCE',view='assembly',role='picture',
         nominal_size=[A3W,A3H],dxf_role='rear_picture')
    # This reflects the same parts and transformations as the machining layout.
    for p in sorted(parts.values(),key=lambda p:(p['face_a']=='BACK',p['part_id'])):
        g=translate(local_to_assembly(p,box(0,0,p['length'],p['width'])),ox,oy)
        poly(m,list(g.exterior.coords)[:-1],'ASSEMBLY_REFERENCE',view='assembly',role='body',
             part_id=p['part_id'],assembly_group=p['assembly_group'])
    rect(m,ox+PX,oy+PY,PRW,PRH,'ASSEMBLY_REFERENCE',view='assembly',role='picture_region',nominal_size=[PRW,PRH])
    for x0,y0,x1,y1 in OPENINGS:
        rect(m,ox+x0,oy+y0,x1-x0,y1-y0,'ASSEMBLY_REFERENCE',view='assembly',role='opening',nominal_size=[OW,OH])
    dimh(m,ox,ox+W,oy+H,oy+H+27,f'{W:g} OVERALL',view='assembly')
    dimv(m,oy,oy+H,ox+W,ox+W+36,f'{H:g} OVERALL',view='assembly')
    names=['LEFT','RIGHT'] if NLEAF==2 else [f'LEAF {i+1}' for i in range(NLEAF)]
    for (x0,y0,x1,y1),nm in zip(LEAVES,names):
        dimh(m,ox+x0,ox+x1,oy+y0,oy-18,f'{LW:g} {nm} LEAF',view='assembly')
    dimv(m,oy+LY0,oy+LY1,ox,ox-29,f'{LH:g} LEAF',view='assembly')
    for x0,y0,x1,y1 in OPENINGS:
        dimh(m,ox+x0,ox+x1,oy+y1,oy+y1+51,f'{OW:g} OPENING',view='assembly')
    dimv(m,oy+PY,oy+PY+OH,ox+OPENINGS[-1][2],ox+OPENINGS[-1][2]+52,f'{OH:g} OPENING',view='assembly')
    text(m,f'A3 {A3W:g} x {A3H:g}',(ox+W/2,oy+PY+24),6,'ASSEMBLY_REFERENCE','center',view='assembly',role='picture_label')
    for (x0,y0,x1,y1),nm in zip(LEAVES,names):
        text(m,f'{nm} / {LW:g} x {LH:g}',(ox+(x0+x1)/2,oy+LY1-17),4,'ASSEMBLY_REFERENCE','center',view='assembly')
    # Member labels are placed from the assembled geometry, not from fixed offsets.
    for p in parts.values():
        g=local_to_assembly(p,box(0,0,p['length'],p['width']))
        cx=(g.bounds[0]+g.bounds[2])/2;cy=(g.bounds[1]+g.bounds[3])/2
        if p['kind'] in ('F01','S01'):
            text(m,p['part_id'],(ox+cx,oy+H*.58),3.6,'ASSEMBLY_REFERENCE','center',90,view='assembly')
        elif p['kind']=='F02' or (p['kind']=='S02' and int(p['part_id'].split('-')[1])%2):
            text(m,p['part_id'],(ox+cx,oy+cy),3.5,'ASSEMBLY_REFERENCE','center',view='assembly')
    text(m,f'{GAP_MID:g} mm centre gap / {GAP_OUT:g} mm external clearances',(ox+W/2,oy-39),4.7,align='center',view='assembly')
    text(m,f'Rear picture region {PRW:g} x {PRH:g} is NOT an unobstructed closed-front opening.',
         (ox+W/2,oy-53),3.8,align='center',view='assembly')


def add_opening(m):
    """Illustrative plan at 90 degrees; provisional axis only, not hardware approval."""
    ox,oy=OPENING_ORIGIN;arc=120;axz=THK+4
    text(m,'OPENING REFERENCE / PLAN (LOOKING DOWN)',(ox,oy+310),8,view='opening',kind='title')
    text(m,'REFERENCE ONLY / AXES AND BACKING POSITION NOT FINAL',(ox,oy+290),4.7,view='opening')
    for g in [box(0,0,FW,THK),box(W-FW,0,W,THK)]:
        poly(m,list(translate(g,ox,oy).exterior.coords)[:-1],'ASSEMBLY_REFERENCE',view='opening',role='body')
    axes=hinge_axes()
    for name,(lx0,_,lx1,_),ax,deg,sg in [('LEFT',LEAVES[0],axes[0],90,1),
                                         ('RIGHT',LEAVES[-1],axes[-1],-90,-1)]:
        axis=(ax,axz)
        closed=box(lx0,0,lx1,THK)
        poly(m,list(translate(closed,ox,oy).exterior.coords)[:-1],'ASSEMBLY_REFERENCE',
             view='opening',role='opening',kind='closed_leaf_ghost',leaf=name)
        opened=rotate(closed,deg,origin=axis)
        poly(m,list(translate(opened,ox,oy).exterior.coords)[:-1],'ASSEMBLY_REFERENCE',
             view='opening',role='body',kind='opened_leaf_illustration',leaf=name,
             reference_only=True,illustrative_angle_deg=90,provisional_axis=list(axis))
        circle_poly(m,ox+axis[0],oy+axis[1],3,'HINGE_REF',view='opening',reference_only=True)
        text(m,f'{name} LEAF',(ox+ax+sg*LW*.2,oy+134),5,'ASSEMBLY_REFERENCE','center',90,view='opening')
        angles=[i*math.pi/36 for i in range(19)]
        if name=='RIGHT':angles=[math.pi-a for a in angles]
        points=[(ox+axis[0]+arc*math.cos(a),oy+axis[1]+arc*math.sin(a)) for a in angles]
        for a,b in zip(points,points[1:]):line(m,a,b,'ASSEMBLY_REFERENCE',view='opening',kind='direction')
        a,b=points[-2:];dx=b[0]-a[0];dy=b[1]-a[1];ln=math.hypot(dx,dy)
        for s2 in [-1,1]:
            line(m,b,(b[0]-8*dx/ln+s2*3*dy/ln,b[1]-8*dy/ln-s2*3*dx/ln),
                 'ASSEMBLY_REFERENCE',view='opening',kind='direction')
        text(m,'90 deg REF',(ox+ax+sg*(arc+18.5),oy+188),4.8,'ASSEMBLY_REFERENCE','center',view='opening')
    # One continuous fixed artwork plane. Its rear setback is illustrative.
    rect(m,ox+PX+PMG,oy-axz,A3W,4,'ASSEMBLY_REFERENCE',view='opening',role='picture',reference_only=True)
    line(m,(ox+PX,oy-axz-5),(ox+PX+PRW,oy-axz-5),'ASSEMBLY_REFERENCE',view='opening',reference_only=True)
    text(m,'ONE A3 PICTURE / FIXED BEHIND BOTH LEAVES',(ox+W/2,oy-47),4.4,align='center',view='opening')
    text(m,'CENTRE MEMBERS MOVE WITH EACH LEAF',(ox+W/2,oy+247),5,align='center',view='opening')
    text(m,'NO FIXED CENTRE MULLION',(ox+W/2,oy+265),6,align='center',view='opening')
    text(m,'VIEWER / FRONT +Z',(ox+W/2,oy+222),5,align='center',view='opening')
    text(m,f'Illustrative axes: (X,Z)=({axes[0]:g},{axz:g}),({axes[-1]:g},{axz:g}). Recheck selected hardware.',
         (ox,oy-70),3.8,view='opening')
    text(m,'No actual hinge, screw, backing clearance or load capacity is verified here.',
         (ox,oy-83),3.8,view='opening')


def pin_build_identity(doc):
    """Record the revision where both a reader and the validator can find it.

    ezdxf writes $TDCREATE, $TDUPDATE and both document GUIDs from the clock and
    a random source at save time, and it overwrites anything set here. The
    fixed-metadata option (enabled at import) replaces all of them with library
    constants, which is what makes the same parameters produce the same bytes.
    That option also erases per-revision identity, so the revision is carried by
    document metadata and by a NOTES annotation instead of by a GUID nobody
    reads. `revision_recorded_matches_parameters` checks it survived the save.
    """
    md=doc.ezdxf_metadata()
    md['HANOK_REVISION']=PARAMS['revision']
    md['HANOK_BUILD_DATE']=PARAMS['build_date']
    md['HANOK_SOURCE_OF_TRUTH']='design_parameters.json'
    md['HANOK_NUMERIC_POLICY']=POLICY_VERSION


def build():
    global MSP
    spec,parts=load_spec()
    doc=ezdxf.new('R2010');doc.units=ezdxf.units.MM
    doc.header['$MEASUREMENT']=1;doc.header['$LUNITS']=2;doc.header['$LUPREC']=3
    doc.header['$INSBASE']=(0,0,0);doc.header['$LWDISPLAY']=True
    pin_build_identity(doc)
    doc.appids.new(APP)
    for name,(c,lw) in LAYERS.items():doc.layers.new(name,dxfattribs={'color':c,'lineweight':lw})
    doc.linetypes.new('REF_DASH',dxfattribs={'description':'Reference dash 4-2','pattern':[6,4,-2]})
    doc.linetypes.new('A3_DASHDOT',dxfattribs={'description':'A3 picture dash-dot','pattern':[13,8,-2,1,-2]})
    for name in ['HINGE_REF','LATCH_REF']:doc.layers.get(name).dxf.linetype='REF_DASH'
    MSP=doc.modelspace()
    for p in parts.values():add_part_geometry(MSP,spec,p)
    add_board(MSP,spec);add_assembly(MSP,parts);add_hardware(MSP,parts)
    positions=add_details();add_opening(MSP)
    for e in MSP:
        role=meta(e).get('role')
        if role=='picture':e.dxf.linetype='A3_DASHDOT'
        elif role in ('opening','picture_region'):e.dxf.linetype='REF_DASH'
    # Default view opens on the stock and machining layout, not the reference sheets.
    doc.set_modelspace_vport(height=BWD+190,center=(BL/2,BWD/2-10))
    # Write candidates beside the outputs and swap them in only after both phases
    # pass, so a rejected build leaves the previous spec and DXF as they were
    # instead of pairing a new spec with an old drawing.
    tmp=OUT/'_validated_candidate.dxf';tmpspec=OUT/'_validated_candidate_spec.json'
    tmpspec.write_text(json.dumps(spec,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    try:
        pre=validate(doc,'IN_MEMORY_BEFORE_SAVE',tmpspec)
        doc.saveas(tmp)
        checkdoc=ezdxf.readfile(tmp)
        report=validate(checkdoc,'READ_BACK_FROM_SAVED_DXF',tmpspec)
    except BaseException:
        tmp.unlink(missing_ok=True);tmpspec.unlink(missing_ok=True)
        raise
    tmpspec.replace(SPEC);tmp.replace(DXF)
    report.update(file=DXF.name,sha256=hashlib.sha256(DXF.read_bytes()).hexdigest(),
                  pre_save_status=pre['status'],ezdxf_version=ezdxf.__version__)
    (OUT/'validation_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    write_manifests(checkdoc)
    return checkdoc,report,positions


class ValidationError(AssertionError):
    def __init__(self,phase,checks):
        self.report=dict(status='FAIL_NOMINAL_DXF_GEOMETRY',phase=phase,checks=checks,
                         failed_checks=[q['name'] for q in checks if q['status']=='FAIL'])
        super().__init__('DXF validation failed: '+', '.join(self.report['failed_checks']))


def validate(doc,phase,spec_path=None):
    """Inspect actual DXF geometry against expectations rebuilt from the parameters.

    The generator reaches pocket coordinates by intersecting assembled members
    and mapping the overlap back through each part's affine. The formula check
    below reaches them from the bar spacing instead, so a mistake in either path
    shows up as a disagreement rather than as a shared assumption.
    """
    checks=[];errors=[];ents=list(doc.modelspace())
    def check(name,ok,detail=None):
        checks.append(dict(name=name,status='PASS' if ok else 'FAIL',measured=detail))
        if not ok:errors.append(name)
    rawparts=[e for e in ents if e.dxf.layer=='CUT_THROUGH']
    pockets=[e for e in ents if e.dxf.layer==POCKET_LAYER]
    dogs=[e for e in ents if e.dxf.layer=='DOGBONE']
    partids=[meta(e).get('part_id') for e in rawparts]
    check('unique_part_ids_and_total',len(partids)==NPART and len(set(partids))==NPART,len(partids))
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
        geometry_matches(g,box(g.bounds[0],g.bounds[1],g.bounds[0]+SIZES[pid[:3]][0],g.bounds[1]+SIZES[pid[:3]][1]))
        for pid,g in partgeo.items()))
    boardents=[e for e in ents if e.dxf.layer=='BOARD_BOUNDARY']
    check(f'board_boundary_{BL:g}x{BWD:g}',len(boardents)==1 and geometry_matches(entity_polygon(boardents[0]),box(0,0,BL,BWD)))
    check('all_parts_within_board',all(box(0,0,BL,BWD).buffer(TOL).covers(g) for g in partgeo.values()))
    pairs=list(itertools.combinations(partgeo,2))
    overlap=max(partgeo[a].intersection(partgeo[b]).area for a,b in pairs)
    gap=min(partgeo[a].distance(partgeo[b]) for a,b in pairs)
    margin=min(min(g.bounds[0],g.bounds[1],BL-g.bounds[2],BWD-g.bounds[3]) for g in partgeo.values())
    check('no_nesting_overlap',overlap<AREA_TOL_MM2,overlap)
    check(f'minimum_nesting_gap_{PGAP:g}mm',gap>=PGAP-TOL,gap)
    check(f'minimum_board_edge_margin_{MARGIN:g}mm',margin>=MARGIN-TOL,margin)
    check('all_lengths_parallel_X_grain',all(g.bounds[2]-g.bounds[0]>g.bounds[3]-g.bounds[1] for g in partgeo.values()))
    bypart=defaultdict(list);byjoint=Counter();by_pair=defaultdict(list)
    for e in pockets:
        d=meta(e);bypart[d['part_id']].append(e);byjoint[d['joint']]+=1;by_pair[d['joint_id']].append(e)
    for j,n in NPOCK.items():check(f'{j}_pocket_count',byjoint[j]==n,byjoint[j])
    check(f'total_base_pockets_{NPOCKT}',len(pockets)==NPOCKT,len(pockets))
    expected={'F01':2,'F02':2,'S01':2+NH,'S02':2+NV,'L01':2+NH,'L02':2+NV}
    check('pockets_per_part',all(len(bypart[p])==expected[p[:3]] for p in partents))
    check(f'S01_{NH}_J4_seats_each',all(sum(meta(e)['joint']=='J4' and meta(e)['seat'] for e in bypart[p])==NH for p in partents if p.startswith('S01')))
    check(f'S02_{NV}_J4_seats_each',all(sum(meta(e)['joint']=='J4' and meta(e)['seat'] for e in bypart[p])==NV for p in partents if p.startswith('S02')))
    check('all_lattice_two_end_laps',all(sum(meta(e)['joint']=='J4' for e in bypart[p])==2 for p in partents if p.startswith('L')))
    check(f'all_L01_{NH}_and_L02_{NV}_crossing_pockets',all(sum(meta(e)['joint']=='J3' for e in bypart[p])==(NH if p.startswith('L01') else NV) for p in partents if p.startswith('L')))
    byleaf=Counter((meta(e)['assembly_group'],meta(e)['family']) for e in rawparts)
    check(f'lattice_{NV}_vertical_{NH}_horizontal_bars_per_leaf',all(
        byleaf[(group_name(D,i),'L01')]==NV and byleaf[(group_name(D,i),'L02')]==NH for i in range(NLEAF)),
        {'per_leaf':[NV,NH]})
    # Compare actual local rectangles to the spacing formula, not just counts.
    VX,HY=bar_offsets(D,'V'),bar_offsets(D,'H')
    actual_patterns={}
    formula_ok=True
    for pid,pe in partents.items():
        k=pid[:3];L,B,_=SIZES[k];x,y=meta(pe)['nesting_origin']
        got=sorted(translate(geom[e.dxf.handle],-x,-y).bounds for e in bypart[pid])
        lap=FW if k[0]=='F' else SM if k[0]=='S' else LAP
        want=[(0,0,lap,B),(L-lap,0,L,B)]
        if k[0]=='S':
            # A seat is as wide as the bar it receives and as deep as the bar's
            # insertion, so its v extent is set by end_lap, never by bar width.
            want += [(SM+c-BW/2,SM-LAP,SM+c+BW/2,SM) for c in (HY if k=='S01' else VX)]
        elif k[0]=='L':
            want += [(LAP+c-BW/2,0,LAP+c+BW/2,BW) for c in (HY if k=='L01' else VX)]
        want=sorted(want)
        formula_ok &= len(got)==len(want) and all(coordinates_match(a,b) for a,b in zip(got,want))
        actual_patterns[pid]=got
    check('all_pocket_coordinates_match_exact_formulas',formula_ok)
    seats=[e for e in pockets if meta(e).get('seat')]
    dbpar=defaultdict(list)
    for e in dogs:dbpar[meta(e)['parent_pocket']].append(e)
    dogok=len(dogs)==NDOG and len(seats)==NSEAT
    for e in seats:
        d=meta(e);items=dbpar[d['feature_id']];dogok &= len(items)==2
        u,v,w,h=d['local_rect'];wantcenters=sorted([(u,v),(u+w,v)])
        gotcenters=[]
        for de in items:
            dd=meta(de);pid=dd['part_id'];x,y=meta(partents[pid])['nesting_origin']
            verts=list(de.get_points('xyb'))
            dogok &= len(verts)==2 and all(abs(vt[2]-1)<TOL for vt in verts)
            if len(verts)!=2:continue
            cx=(verts[0][0]+verts[1][0])/2;cy=(verts[0][1]+verts[1][1])/2
            radius=math.hypot(verts[0][0]-cx,verts[0][1]-cy)
            gotcenters.append((cx-x,cy-y))
            dogok &= abs(radius-R)<TOL and dd['part_id']==d['part_id'] and close(dd['depth_mm'],DEPTH)
            dogok &= partgeo[pid].buffer(TOL).covers(box(cx-radius,cy-radius,cx+radius,cy+radius))
        dogok &= len(gotcenters)==len(wantcenters) and all(
            coordinates_match(a,b) for a,b in zip(sorted(gotcenters),wantcenters))
    check(f'{NDOG}_exact_R{R:g}_corner_reliefs_two_per_seat',bool(dogok),len(dogs))
    radii=[];tool_ok=len(dogs)==NDOG
    for de in dogs:
        arcs=polyline_arcs(de)
        tool_ok &= len(arcs)==2
        radii.extend(a[2] for a in arcs)
    tool_radius=PARAMS['machining']['tool_diameter']/2
    tool_ok &= all(r>=tool_radius-TOL for r in radii)
    check('machining_relief_radius_at_least_tool_radius',bool(tool_ok),
          dict(tool_radius_mm=tool_radius,minimum_actual_radius_mm=min(radii) if radii else None))
    machining=measure_machining(pockets,dogs,geom,partgeo,THK)
    check('distinct_machining_regions_separated',machining['separated'],machining['separation'])
    check('machining_preserves_non_open_edges',machining['non_open_edges_preserved'],machining['edges'])
    check('all_pockets_reliefs_inside_own_part',all(partgeo[meta(e)['part_id']].buffer(TOL).covers(geom[e.dxf.handle]) for e in pockets+dogs))
    check('layer_depth_and_face_separation',all(close(meta(e).get('depth_mm',-1),THK) for e in rawparts) and all(close(meta(e).get('depth_mm',-1),DEPTH) and meta(e).get('machining_face')=='A' for e in pockets+dogs))
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
    npair=NPOCKT//2
    pairgood=len(by_pair)==npair;maxmismatch=0.;mateok=True
    for jid,gg in by_pair.items():
        if len(gg)!=2:pairgood=False;continue
        a,b=gg;da,db=meta(a),meta(b)
        ga=assembled(da['part_id'],geom[a.dxf.handle]);gb=assembled(db['part_id'],geom[b.dxf.handle])
        mismatch=ga.symmetric_difference(gb).area;maxmismatch=max(mismatch,maxmismatch)
        pairgood &= geometry_matches(ga,gb) and da['joint']==db['joint']
        pairgood &= {meta(partents[d['part_id']])['assembly_face_A'] for d in [da,db]}=={'FRONT','BACK'}
        pairgood &= geometry_matches(ap[da['part_id']].intersection(ap[db['part_id']]),ga)
        mateok &= da['mate_feature_id']==db['feature_id'] and db['mate_feature_id']==da['feature_id']
    check(f'{npair}_joint_pairs_XY_match_opposite_faces',bool(pairgood),{'pairs':len(by_pair),'max_mismatch_area_mm2':maxmismatch})
    check('mate_feature_links_bidirectional',bool(mateok))
    # Each part becomes 2D regions carrying the Z range that survives machining:
    # untouched material keeps the full thickness, while a pocket cut from face A
    # leaves 0..THK-DEPTH on a FRONT part and DEPTH..THK on a flipped one. Deriving
    # the range from the actual depth is what makes a wrong depth measurable here;
    # assuming two complementary half-slabs would quietly accept any value.
    solids={}
    for pid,g in ap.items():
        cut=[e for e in pockets+dogs if meta(e)['part_id']==pid]
        removal=unary_union([assembled(pid,geom[e.dxf.handle]) for e in cut]) if cut else None
        front=meta(partents[pid])['assembly_face_A']=='FRONT'
        pieces=[(g if removal is None else g.difference(removal),0.,float(THK))]
        if removal is not None:
            pieces.append((removal.intersection(g),
                           0.,float(THK-DEPTH)) if front else
                          (removal.intersection(g),float(DEPTH),float(THK)))
        solids[pid]=[(r,z0,z1) for r,z0,z1 in pieces if not r.is_empty and r.area>AREA_TOL_MM2 and z1>z0]
    v_max=0.;worst=None
    for a,b in pairs:
        for ra,za0,za1 in solids[a]:
            for rb,zb0,zb1 in solids[b]:
                dz=min(za1,zb1)-max(za0,zb0)
                if dz<=0:continue
                vol=ra.intersection(rb).area*dz
                if vol>v_max:v_max=vol;worst=f'{a}/{b}'
    check('no_nominal_assembled_solid_interpenetration',v_max<VOLUME_TOL_MM3,
          {'max_volume_mm3':v_max,'worst_pair':worst,
           'method':f'per-region Z ranges from depth {DEPTH:g} in stock {THK:g}; '
                    f'actual circular bulges sampled with chord error <= {ARC_CHORD_TOL_MM:g} mm'})
    check(f'half_lap_depth_{DEPTH:g}_is_half_of_stock_{THK:g}',abs(2*DEPTH-THK)<TOL,
          {'retained_front':THK-DEPTH,'retained_back':THK-DEPTH,'stock':THK})
    fixed=unary_union([g for pid,g in ap.items() if pid.startswith('F')])
    leaves=[unary_union([g for pid,g in ap.items() if meta(partents[pid])['assembly_group']==group_name(D,i)]) for i in range(NLEAF)]
    check(f'frame_{W:g}x{H:g}_inner{D["inner_w"]:g}x{D["inner_h"]:g}',geometry_matches(fixed,box(0,0,W,H).difference(box(FW,FW,W-FW,H-FW))))
    check(f'all_leaf_envelopes{LW:g}x{LH:g}',all(
        coordinates_match(lf.bounds,LEAVES[i]) for i,lf in enumerate(leaves)))
    # Read the proportion off the assembled members rather than from LW/LH, so it
    # still holds if the leaf envelope itself were derived wrongly.
    ratios=[(lf.bounds[3]-lf.bounds[1])/(lf.bounds[2]-lf.bounds[0]) for lf in leaves]
    check(f'leaf_height_to_width_ratio_at_least_{MINR:g}',all(r>=MINR-RATIO_TOL for r in ratios),
          [round(r,6) for r in ratios])
    gapsok=all(abs(lf.distance(fixed)-GAP_OUT)<TOL for lf in leaves)
    gapsok &= all(abs(leaves[i].distance(leaves[i+1])-GAP_MID)<TOL for i in range(NLEAF-1))
    check(f'centre_gap{GAP_MID:g}_and_outer_gaps{GAP_OUT:g}',gapsok)
    # Measure lattice spacing off the assembled bars. The pocket formula check
    # calls bar_offsets(), the same helper the generator uses to place the bars,
    # so an error inside that helper cancels out there and cannot be caught. This
    # block asks nothing about where a bar should be: it reads the opening from
    # the sash members, reads the bar edges, and requires the resulting gaps to be
    # equal to each other and to the span left over once the bars are subtracted.
    spacing_ok=True;cells={}
    for i in range(NLEAF):
        grp=group_name(D,i)
        def members(kind,axis):
            got=[ap[p] for p,e in partents.items()
                 if meta(e)['assembly_group']==grp and p[:3]==kind]
            return sorted(got,key=lambda g:g.bounds[axis]+g.bounds[axis+2])
        for kind,edge,axis in (('L01','S01',0),('L02','S02',1)):
            frame_members=members(edge,axis);bars=members(kind,axis)
            if len(frame_members)!=2 or not bars:spacing_ok=False;continue
            span0=frame_members[0].bounds[axis+2];span1=frame_members[1].bounds[axis]
            widths=[g.bounds[axis+2]-g.bounds[axis] for g in bars]
            edges=[span0]+[c for g in bars for c in (g.bounds[axis],g.bounds[axis+2])]+[span1]
            gaps=[edges[j+1]-edges[j] for j in range(0,len(edges)-1,2)]
            want=(span1-span0-sum(widths))/(len(bars)+1)
            spacing_ok &= len(gaps)==len(bars)+1 and want>0
            spacing_ok &= max(widths)-min(widths)<TOL
            spacing_ok &= all(abs(g-want)<TOL for g in gaps)
            cells[f'{grp}/{kind}']=round(want,6)
    check('lattice_bars_evenly_spaced_in_measured_opening',spacing_ok,cells)
    check('no_fixed_centre_mullion',fixed.intersection(box(FW,FW,W-FW,H-FW)).area<AREA_TOL_MM2)
    leafbox={group_name(D,i):box(*LEAVES[i]) for i in range(NLEAF)}
    check('no_member_bridges_leaves',all(leafbox[meta(e)['assembly_group']].buffer(TOL).covers(ap[pid])
          for pid,e in partents.items() if meta(e)['assembly_group']!='FIXED'))
    ox,oy=ASSEMBLY_ORIGIN
    assemblies=[e for e in ents if meta(e).get('view')=='assembly']
    abodies=[e for e in assemblies if meta(e).get('role')=='body']
    check('assembly_reference_matches_all_cut_parts',len(abodies)==NPART and all(geometry_matches(translate(entity_polygon(e),-ox,-oy),ap[meta(e)['part_id']]) for e in abodies))
    pic=[e for e in assemblies if meta(e).get('role')=='picture'][0]
    reg=[e for e in assemblies if meta(e).get('role')=='picture_region'][0]
    pg=translate(entity_polygon(pic),-ox,-oy);rg=translate(entity_polygon(reg),-ox,-oy)
    check(f'A3_portrait{A3W:g}x{A3H:g}_in{PRW:g}x{PRH:g}_margin{PMG:g}',
          geometry_matches(pg,box(PX+PMG,PY+PMG,PX+PMG+A3W,PY+PMG+A3H)) and geometry_matches(rg,box(PX,PY,PX+PRW,PY+PRH))
          and abs(rg.boundary.distance(pg)-PMG)<TOL)
    px0,py0,px1,py1=pg.bounds;rx0,ry0,rx1,ry1=rg.bounds
    margins=dict(left=px0-rx0,right=rx1-px1,bottom=py0-ry0,top=ry1-py1)
    check('picture_margins_match_each_side',rg.buffer(TOL).covers(pg) and
          all(close(v,PMG,TOL) for v in margins.values()),dict(required_mm=PMG,measured_mm=margins))
    check('A3_and_picture_region_distinct_linetypes',pic.dxf.linetype!=reg.dxf.linetype,{'A3':pic.dxf.linetype,'region':reg.dxf.linetype})
    openings=[e for e in assemblies if meta(e).get('role')=='opening']
    opening_geometry=[entity_polygon(e) for e in openings]
    check(f'{NLEAF}_openings_{OW:g}x{OH:g}_reference',len(openings)==NLEAF and all(
        geometry_matches(g,box(g.bounds[0],g.bounds[1],g.bounds[0]+OW,g.bounds[1]+OH)) for g in opening_geometry))
    hws=[e for e in ents if meta(e).get('kind')=='hardware_ref' and meta(e).get('view')=='nest']
    hwtype=defaultdict(set)
    hwmatch=True
    for e in hws:
        d=meta(e);hwtype[d['hardware_type']].add(d['hardware_id'])
        hwmatch &= d['reference_only'] and not d['production_machining']
        g=assembled(d['part_id'],entity_polygon(e))
        matched=[q for q in assemblies if meta(q).get('kind')=='hardware_ref' and meta(q).get('part_id')==d['part_id'] and meta(q).get('hardware_id')==d['hardware_id']]
        hwmatch &= len(matched)==1 and geometry_matches(translate(entity_polygon(matched[0]),-ox,-oy),g)
    wanthw={'HINGE':2*NLEAF,'HANDLE':NLEAF,'CATCH':NLEAF}
    check(f'hardware_{2*NLEAF}hinges_{NLEAF}handles_{NLEAF}catches_reference_only',
          bool(hwmatch) and {k:len(v) for k,v in hwtype.items()}==wanthw,{k:len(v) for k,v in hwtype.items()})
    detailtypes={meta(e).get('detail') for e in ents if meta(e).get('view')=='detail'}
    check('J1_J2_J3_J4_reference_details_present',detailtypes=={'J1','J2','J3','J4'})
    check('references_never_on_machining_layers',not any(meta(e).get('view') in ['assembly','detail','opening'] for e in mach))
    opened=[e for e in ents if meta(e).get('kind')=='opened_leaf_illustration']
    check('two_sided_opening_illustration_reference_only',len(opened)==2 and all(meta(e).get('reference_only') for e in opened))
    check(f'all{NPOCKT}_pockets_have_open_edge_intent',all(bool(meta(e).get('open_edges')) for e in pockets))
    md=doc.ezdxf_metadata()
    check('revision_recorded_matches_parameters',
          md.get('HANOK_REVISION')==PARAMS['revision'] and md.get('HANOK_BUILD_DATE')==PARAMS['build_date'],
          {'revision':md.get('HANOK_REVISION'),'build_date':md.get('HANOK_BUILD_DATE')})
    check('numeric_policy_recorded',md.get('HANOK_NUMERIC_POLICY')==POLICY_VERSION,policy_record())
    spec_path=SPEC if spec_path is None else spec_path
    if spec_path.is_file():
        fresh=json.dumps(build_spec(PARAMS),sort_keys=True)
        check('design_spec_on_disk_matches_parameters',fresh==json.dumps(json.loads(spec_path.read_text(encoding='utf-8')),sort_keys=True))
    audit=doc.audit()
    check('DXF_audit_no_errors_no_fixes',not audit.has_errors and not audit.has_fixes,{'errors':len(audit.errors),'fixes':len(audit.fixes)})
    if errors:raise ValidationError(phase,checks)
    return dict(status='PASS_NOMINAL_DXF_GEOMETRY',phase=phase,saved_dxf_reread=phase=='READ_BACK_FROM_SAVED_DXF',
                revision=PARAMS['revision'],checks_passed=len(checks),checks=checks,
                numeric_policy=policy_record(),manufacturing_assessment=machining['manufacturing_assessment'],
                parts_total=NPART,part_counts=dict(count),
                nominal_pockets_total=len(pockets),pocket_counts=dict(byjoint),dogbone_reliefs_total=len(dogs),
                machining_profiles_total=len(mach),mated_joints_total=len(by_pair),
                minimum_part_gap_mm=gap,minimum_board_margin_mm=margin,
                nesting_bounds_mm=list(unary_union(list(partgeo.values())).bounds),
                lattice_per_leaf=dict(vertical=NV,horizontal=NH,crossings=D['crossings_total']//NLEAF),
                overall_width_height_mm=[W,H],leaf_width_height_mm=[LW,LH],board_mm=[BL,BWD,BT],
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
    emit('parts_manifest.csv',[dict(part_id=pid,length_mm=d['length_mm'],width_mm=d['width_mm'],thickness_mm=THK,
         nest_x_mm=d['nesting_origin'][0],nest_y_mm=d['nesting_origin'][1],assembly_group=d['assembly_group'],
         A_face_in_assembly=d['assembly_face_A'],grain_axis='X',assembly_affine=json.dumps(d['assembly_map']),
         pocket_count=sum(meta(e).get('part_id')==pid and e.dxf.layer==POCKET_LAYER for e in ents)) for pid,d in pmap.items()])
    emit('pocket_manifest.csv',[dict(part_id=d['part_id'],feature_id=d['feature_id'],joint=d['joint'],pair_id=d['joint_id'],
         u0_mm=d['local_rect'][0],v0_mm=d['local_rect'][1],length_mm=d['local_rect'][2],width_mm=d['local_rect'][3],
         depth_mm=DEPTH,seat=d['seat'],mate_part_id=d['mate_part_id'],mate_feature_id=d['mate_feature_id'],
         open_edges=';'.join(d['open_edges']),A_face_in_assembly=pmap[d['part_id']]['assembly_face_A'],dxf_handle=e.dxf.handle)
         for e in ents if e.dxf.layer==POCKET_LAYER for d in [meta(e)]])
    emit('dogbone_manifest.csv',[dict(part_id=d['part_id'],feature_id=d['feature_id'],parent_pocket=d['parent_pocket'],
         center_u_mm=d['local_center'][0],center_v_mm=d['local_center'][1],radius_mm=R,depth_mm=DEPTH,
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
        n=FW if j=='J1' else SM if j=='J2' else BW
        across=LAP if j=='J4' else n
        tx(f'{n:g} x {across:g} pocket / depth {DEPTH:g} / stock {THK:g}',10,164,4.7)
        if j in ('J1','J2'):
            fam1,fam2=('F01','F02') if j=='J1' else ('S01','S02')
            by=97 if j=='J1' else 107
            tx(f'{fam1} / A -> FRONT',15,148,4)
            tx(f'{fam2} / A -> BACK (flip)',135,148,3.6)
            rr(15,by,80,n); rr(135,by,80,n)
            rr(15,by,n,n,'pocket'); rr(135,by,n,n,'pocket')
            dimh(MSP,ox+15,ox+15+n,oy+by,oy+by-9,f'{n:g}',detail=j)
            dimv(MSP,oy+by,oy+by+n,ox+95,ox+104,f'{n:g}',detail=j)
            dimh(MSP,ox+135,ox+135+n,oy+by,oy+by-9,f'{n:g}',detail=j)
            # Section schematic: complementary retained halves at their overlap.
            sx=70; sy=36
            pp([(sx,sy),(sx+20+n,sy),(sx+20+n,sy+DEPTH),(sx+20,sy+DEPTH),
                (sx+20,sy+THK),(sx,sy+THK)],'section_back')
            pp([(sx+20,sy+DEPTH),(sx+20+n,sy+DEPTH),(sx+20+n,sy),
                (sx+40+n,sy),(sx+40+n,sy+THK),(sx+20,sy+THK)],'section_front')
            dimv(MSP,oy+sy,oy+sy+THK,ox+sx+40+n,ox+sx+50+n,f'{THK:g}',detail=j)
            dimv(MSP,oy+sy+DEPTH,oy+sy+THK,ox+sx+20+n,ox+sx+66+n,f'{DEPTH:g} depth',detail=j)
            tx('ASSEMBLED SECTION - complementary faces',15,69,4)
            tx('Local end regions only; open edges need cutter overrun in CAM.',10,18,3.3)
        elif j=='J3':
            tx('L01 / A -> FRONT',15,148,4)
            tx('L02 / A -> BACK (flip)',135,148,3.7)
            rr(15,125,80,BW);rr(135,125,80,BW)
            rr(50,125,BW,BW,'pocket');rr(170,125,BW,BW,'pocket')
            dimh(MSP,ox+50,ox+50+BW,oy+125,oy+112,f'{BW:g}',detail=j)
            dimv(MSP,oy+125,oy+125+BW,ox+95,ox+105,f'{BW:g}',detail=j)
            dimh(MSP,ox+170,ox+170+BW,oy+125,oy+112,f'{BW:g}',detail=j)
            tx(f'{D["crossings_total"]} crossings x 2 matching pockets = {NPOCK["J3"]} pockets',15,95,4.2)
            sx=85;sy=40
            rr(sx+20,sy,BW,BW,'section_back')
            pp([(sx,sy),(sx+20,sy),(sx+20,sy+DEPTH),(sx+20+BW,sy+DEPTH),
                (sx+20+BW,sy),(sx+50,sy),(sx+50,sy+THK),(sx,sy+THK)],'section_front')
            dimv(MSP,oy+sy,oy+sy+THK,ox+sx+50,ox+sx+60,f'{THK:g}',detail=j)
            dimv(MSP,oy+sy+DEPTH,oy+sy+THK,ox+sx+20+BW,ox+sx+76,f'{DEPTH:g} depth',detail=j)
            tx('ASSEMBLED SECTION - front and back remain flush',15,75,4)
            tx(f'Slots span the entire {BW:g} mm bar width. No closed-side dogbones.',10,18,3.3)
        else:
            tx('S02 receiver / A -> BACK',15,148,3.9)
            tx('L01 end / A -> FRONT',135,148,3.9)
            # The seat is BW wide along the rail and LAP deep into it; those are
            # two different parameters even though the default design shares 10.
            seat=107+SM-LAP
            rr(15,107,80,SM);rr(135,117,70,BW)
            rr(45,seat,BW,LAP,'pocket');rr(135,117,LAP,BW,'pocket')
            for cx in (45,45+BW):
                circle_poly(MSP,ox+cx,oy+seat,R,'JOINT_DETAILS_REF',
                            role='dogbone',**common,radius_mm=R)
            dimh(MSP,ox+45,ox+45+BW,oy+seat,oy+116,f'{BW:g}',detail=j)
            dimv(MSP,oy+seat,oy+107+SM,ox+95,ox+105,f'{LAP:g} lap',detail=j)
            dimh(MSP,ox+135,ox+135+LAP,oy+117,oy+105,f'{LAP:g}',detail=j)
            tx(f'2 x R{R:g} at closed corners; union with nominal pocket',15,82,3.7)
            # Sectioned along the insertion direction, so the stepped overlap runs
            # for LAP, not for the bar width. Depth stays a Z quantity.
            sx=83;sy=35
            pp([(sx,sy),(sx+20,sy),(sx+20,sy+DEPTH),(sx+20+LAP,sy+DEPTH),
                (sx+20+LAP,sy+THK),(sx,sy+THK)],'section_front')
            pp([(sx+20,sy),(sx+55,sy),(sx+55,sy+THK),(sx+20+LAP,sy+THK),
                (sx+20+LAP,sy+DEPTH),(sx+20,sy+DEPTH)],'section_back')
            dimv(MSP,oy+sy,oy+sy+THK,ox+sx+55,ox+sx+65,f'{THK:g}',detail=j)
            dimv(MSP,oy+sy+DEPTH,oy+sy+THK,ox+sx+20+LAP,ox+sx+81,f'{DEPTH:g} depth',detail=j)
            dimh(MSP,ox+sx+20,ox+sx+20+LAP,oy+sy,oy+sy-12,f'{LAP:g} lap',detail=j)
            tx(f'ASSEMBLED SECTION / {LAP:g} mm seat depth, {DEPTH:g} mm in Z',15,67,4)
            tx(f'S01 + L02 is the face-reversed equivalent. {NSEAT} end joints total.',10,18,3.4)
        tx('REFERENCE ONLY / DXF 1:1 / PNG enlarged',10,7,3.2)
    return positions


def render_details(doc,positions):
    im=Image.new('RGB',(4400,3840),COL['white']);d=ImageDraw.Draw(im)
    label(d,(120,65),'02  JOINERY DETAILS',65,bold=True)
    label(d,(120,153),f'Closed pocket geometry  |  All wood {THK:g} mm thick  |  Pocket depth {DEPTH:g} mm  |  Exact R{R:g} relief arcs',31,fill=COL['muted'])
    d.line((120,220,4280,220),fill=COL['border'],width=3)
    viewports={'J1':(100,280,2040,1615),'J2':(2260,280,2040,1615),
               'J3':(100,1960,2040,1615),'J4':(2260,1960,2040,1615)}
    for j,(ox,oy) in positions.items():
        vp=viewports[j];r=Renderer(im,(ox,oy,ox+240,oy+190),vp)
        ents=[e for e in doc.modelspace() if meta(e).get('detail')==j]
        # All geometry is read from the reference detail regions in the final DXF.
        r.entities(ents)
    y=3650
    legend=[(COL['pocket'],f'{DEPTH:g} mm pocket'),(COL['dog'],f'R{R:g} relief'),
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
    for lay in ['CUT_THROUGH',POCKET_LAYER,'DOGBONE','HINGE_REF','LATCH_REF','PART_ID']:
        out += [e for e in ents if e.dxf.layer==lay and (lay in ['CUT_THROUGH',POCKET_LAYER,'DOGBONE'] or meta(e).get('view')=='nest')]
    if full:out += [e for e in ents if meta(e).get('view')=='nest' and e.dxf.layer in ['GRAIN_DIRECTION','NOTES','DIMENSIONS'] and meta(e).get('kind')!='title']
    return out


def cutzone(report):
    """Framing box for the enlarged views, taken from the measured nesting bounds."""
    nb=report['nesting_bounds_mm']
    return (0,0,nb[2]+MARGIN,nb[3]+MARGIN)


def render_nesting(doc,report):
    im=Image.new('RGB',(4400,4280),COL['white']);d=ImageDraw.Draw(im)
    nb=report['nesting_bounds_mm']
    label(d,(120,65),'01  ONE-BOARD NESTING / PORTRAIT DOUBLE LEAF',61,bold=True)
    label(d,(120,155),f'{BL:g} x {BWD:g} x {BT:g} mm  |  CNC face A  |  {W:g} W x {H:g} H assembled  |  All part lengths parallel to +X grain',28,fill=COL['muted'])
    d.line((120,225,4280,225),fill=COL['border'],width=3)
    r=Renderer(im,(-45,-52,BL+20,BWD+46),(90,280,3000,2370));r.entities(nest_entities(doc,True))
    x,y,w=3190,310,980
    label(d,(x,y),'SAVED DXF CHECKED',33,bold=True);y+=75
    for value,desc in [(report['parts_total'],'independent wooden parts'),
                       (report['nominal_pockets_total'],'closed nominal pocket contours'),
                       (report['dogbone_reliefs_total'],f'exact R{R:g} relief contours'),
                       (report['mated_joints_total'],'matching half-lap joint pairs')]:
        label(d,(x,y),str(value),66,bold=True);label(d,(x+165,y+25),desc,25);y+=118
    y+=20;d.line((x,y,x+w,y),fill=COL['border'],width=3);y+=43
    label(d,(x,y),'LAYER / MACHINING INTENT',30,bold=True);y+=70
    for col,ttl,sub in [(COL['wood'],'CUT_THROUGH',f'{THK:g} mm nominal full-depth outer profile'),
                        (COL['pocket'],POCKET_LAYER,f'{DEPTH:g} mm deep from common A face'),
                        (COL['dog'],'DOGBONE',f'{DEPTH:g} mm deep; union with parent seat'),
                        (COL['hardware'],'HINGE_REF / LATCH_REF','Reference only. EXCLUDE FROM CAM.')]:
        d.rectangle((x,y,x+40,y+40),fill=col,outline=COL['line'],width=2)
        label(d,(x+62,y),ttl,27,bold=True)
        label(d,(x+62,y+44),sub,24,fill=COL['muted']);y+=116
    y+=25;label(d,(x,y),'ASSEMBLY FACE ORIENTATION',29,bold=True);y+=62
    for s in ['F01 / S01 / L01: A faces FRONT.',
              'F02 / S02 / L02: flip after cutting; A faces BACK.',
              f'Minimum stock edge margin: {MARGIN:g} mm.',
              f'Minimum between-part gap: {PGAP:g} mm.',
              f'Cut-zone envelope: X{nb[0]:g}-{nb[2]:g} / Y{nb[1]:g}-{nb[3]:g}.',
              'Open-edge laps need waste-side cutter overrun.',
              'No tabs, toolpaths, feeds or speeds included.']:
        y=wrapped(d,s,(x,y),w,26);y+=20
    label(d,(120,2760),f'CUT-ZONE ENLARGEMENT / SAME {report["parts_total"]} PARTS',45,bold=True)
    label(d,(120,2830),'A second viewport of the saved DXF, not additional parts. Pocket and relief positions are taken from CAD entities.',27,fill=COL['muted'])
    d.rounded_rectangle((95,2900,4300,4140),radius=18,fill=COL['panel'],outline=COL['border'],width=2)
    rr=Renderer(im,cutzone(report),(130,2920,4120,1200));rr.entities(nest_entities(doc,False))
    label(d,(120,4180),'NOMINAL GEOMETRY ONLY  |  Fit coupons, actual hardware and CAM setup require approval before production.',27,fill=COL['muted'])
    im.save(OUT/'01_one_board_nesting.png',dpi=(220,220))


def render_closeup(doc,report):
    im=Image.new('RGB',(4400,1850),COL['white']);d=ImageDraw.Draw(im)
    label(d,(110,60),'05  ALL POCKETS / CUT-ZONE CLOSEUP',58,bold=True)
    label(d,(110,145),f'Same {report["parts_total"]} parts at increased viewing scale  |  {report["nominal_pockets_total"]} nominal pockets + {report["dogbone_reliefs_total"]} reliefs  |  Closed DXF contours',28,fill=COL['muted'])
    Renderer(im,cutzone(report),(100,245,4200,1400)).entities(nest_entities(doc,False))
    label(d,(110,1720),'Part labels are annotations, not engraving. Dashed hardware outlines are references, not approved machining.',28,fill=COL['muted'])
    im.save(OUT/'05_all_pockets_closeup.png',dpi=(220,220))


def render_assembly(doc):
    im=Image.new('RGB',(3600,3950),COL['white']);d=ImageDraw.Draw(im)
    label(d,(105,62),'03  ASSEMBLY / PORTRAIT DOUBLE LEAF',59,bold=True)
    label(d,(105,151),f'{W:g} W x {H:g} H overall  |  Two {LW:g} W x {LH:g} H leaves  |  One A3 portrait picture behind both leaves',27,fill=COL['muted'])
    d.line((105,225,3495,225),fill=COL['border'],width=3)
    ox,oy=ASSEMBLY_ORIGIN
    r=Renderer(im,(ox-48,oy-63,ox+W+56,oy+H+44),(70,290,2590,2980))
    ents=[e for e in doc.modelspace() if meta(e).get('view')=='assembly' and meta(e).get('kind')!='title'
          and not (e.dxftype()=='TEXT' and 'DOUBLE LEAF / REFERENCE' in e.dxf.text)]
    r.entities([e for e in ents if meta(e).get('role')=='picture'])
    r.entities([e for e in ents if meta(e).get('role')=='body'])
    r.entities([e for e in ents if meta(e).get('role') not in ['body','picture']])
    x,y,w=2760,360,700
    label(d,(x,y),'DESIGN SCHEDULE',30,bold=True);y+=72
    centre=SM+GAP_MID+SM
    for ttl,body in [('A3 PORTRAIT',f'{A3W:g} W x {A3H:g} H mm. A single picture stays on the fixed rear support.'),
                     ('PICTURE REGION',f'{PRW:g} W x {PRH:g} H mm. {PMG:g} mm allowance around the artwork.'),
                     ('EACH LEAF OPENING',f'{OW:g} W x {OH:g} H before lattice subdivision.'),
                     ('LATTICE',f'Per leaf: {NV} vertical + {NH} horizontal bars, making {D["crossings_total"]//NLEAF} flush crossings.'),
                     ('CENTRE MEETING',f'{SM:g} + {GAP_MID:g} + {SM:g} = {centre:g} mm. The two centre stiles move with their own leaves.'),
                     ('NO FIXED MULLION','Opening both leaves removes the centre stiles from the picture front.')]:
        label(d,(x,y),ttl,25,bold=True);y+=43
        y=wrapped(d,body,(x,y),w,27);y+=41
    d.line((x,y,x+w,y),fill=COL['border'],width=3);y+=44
    label(d,(x,y),'REFERENCE HARDWARE',28,bold=True);y+=62
    hh=hinge_heights()
    for s in [f'{2*NLEAF} hinges: 2 on each outside edge. Height centres Y={hh[0]:g} and {hh[1]:g} mm.',
              f'{NLEAF} handles and {NLEAF} independent catches. No centre-post latch required.',
              'Hinge geometry, fasteners, rear backing and actual swing remain unapproved.']:
        y=wrapped(d,s,(x,y),w,26);y+=29
    d.rounded_rectangle((110,3420,3490,3800),radius=18,fill=COL['panel'],outline=COL['border'],width=2)
    label(d,(160,3460),'IMPORTANT DISTINCTION',32,bold=True)
    label(d,(160,3525),f'{PRW:g} x {PRH:g} is the rear picture region, NOT one unobstructed opening when the leaves are closed.',28)
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
    r=Renderer(im,(ox-20,oy-94,ox+W+22,oy+321),(110,285,2720,2190))
    r.entities([e for e in doc.modelspace() if meta(e).get('view')=='opening'])
    x,y,w=2970,365,875
    for ttl,s in [('ILLUSTRATION ONLY','The 90-degree plan uses provisional front-projecting axes to explain the opening direction. It is not a selected hinge model.'),
                  ('VERTICAL HINGE AXES','Two hinges on the LEFT outside edge, two on the RIGHT. Not top/bottom hinges and not a folding door.'),
                  ('FIXED PICTURE',f'One {A3W:g} x {A3H:g} mm portrait picture remains on a separate rear support. The setback shown is illustrative.'),
                  ('BEFORE PRODUCTION','Check actual hinge pin offsets, leaf thickness, fasteners, load capacity, backing clearance and both leaves moving together.')]:
        label(d,(x,y),ttl,29,bold=True);y+=57
        y=wrapped(d,s,(x,y),w,29);y+=66
    label(d,(115,2580),'REFERENCE ONLY / Actual hinge dimensions, screws, loads and dynamic collision checks remain PENDING.',29,bold=True)
    label(d,(115,2650),'No illustration on this sheet is a production pocket or a CNC toolpath.',27,fill=COL['muted'])
    im.save(OUT/'04_opening_reference.png',dpi=(220,220))


def write_readme(report):
    nb=report['nesting_bounds_mm']
    vg,hg=D['vertical_gap'],D['horizontal_gap']
    centre=SM+GAP_MID+SM
    parts='\n'.join(
        f"{k} {r} {D['part_lengths'][k]:g} x {D['part_widths'][k]:g} x {THK:g} : {D['part_counts'][k]}개"
        for k,r in [('F01','고정틀 세로재'),('F02','고정틀 가로재'),('S01','창짝 세로재'),
                    ('S02','창짝 가로재'),('L01','세로 창살'),('L02','가로 창살')])
    textout=f'''A3 세로형 한식 양개 창호 — 통합 CNC 패키지 / {PARAMS['revision']}
================================================================
이 폴더가 유일한 최신 제작 기준입니다. from_claude/from_codex와 혼합하지 마십시오.
모든 치수는 design_parameters.json에서 유도됩니다. design_spec.json을 직접 수정하지 마십시오.
정면은 폭 W x 높이 H, 부품은 길이 L x 폭 B x 두께 T입니다. 단위 mm.
실제 저장 DXF 재읽기: {report['status']} / {report['checks_passed']}개 검사 PASS.
이 PASS는 명목 CAD geometry 검사이지 실제 제작·하중·개폐 승인서가 아닙니다.

1. 규격
- 완성 외곽 W{W:g} x H{H:g}; 고정틀 폭{FW:g}, 내부{D['inner_w']:g} x{D['inner_h']:g}.
- 좌우 창짝 각각 W{LW:g} x H{LH:g}; 창짝 테두리 폭{SM:g}.
- 바깥 고정틀 간극{GAP_OUT:g}, 중앙 간극{GAP_MID:g}. 중앙 고정 기둥 없음.
- 각 창짝 창살 설치 개구부{OW:g} x{OH:g}, 세로살{NV}/가로살{NH}.
- 창살 빈칸 {vg:.2f} x {hg:.2f}, 창짝당 교차점{D['crossings_total']//NLEAF}개.
- 후면 그림 배치 기준영역{PRW:g} x{PRH:g}, A3 세로형{A3W:g} x{A3H:g}, 사방{PMG:g} 여유.
- 닫힌 정면의 연속 개구부가{PRW:g} x{PRH:g}이라는 뜻이 아님.
- 중앙 폭{centre:g}=세로재{SM:g}+틈{GAP_MID:g}+세로재{SM:g}. 양쪽을 열면 중앙 세로재도 이동.
- 원판{BL:g} x{BWD:g} x{BT:g}. 원판의{BL:g}방향(+X)이 목리, 모든 긴 부품이 X평행.
- 공구 기준 Ø{PARAMS['machining']['tool_diameter']:g}, 명목 pocket깊이{DEPTH:g}, 도그본R{R:g}, 관통 명목깊이{THK:g}.

2. 부품표 / L x B x T
{parts}
합계{NPART}개. 모든 부품에 별도의 ID annotation과 XDATA 메타데이터가 존재합니다.
최소 원판 여유{MARGIN:g}, 최소 부품 간격{PGAP:g}. 부품 외접범위 X{nb[0]:g}~{nb[2]:g}/Y{nb[1]:g}~{nb[3]:g}.

3. 가공 layer
BOARD_BOUNDARY : 원판 외곽, 절삭 금지.
CUT_THROUGH : {NPART}개 closed LWPOLYLINE, {THK:g}두께 관통 외곽.
{POCKET_LAYER} : {NPOCKT}개 closed LWPOLYLINE, A면에서 깊이{DEPTH:g}.
DOGBONE : {NDOG}개 exact circular-bulge closed LWPOLYLINE, 깊이{DEPTH:g}.
HINGE_REF : 경첩{2*NLEAF}개, 각 고정틀/창짝 날개 위치만 참고. 생산 가공 제외.
LATCH_REF : 손잡이{NLEAF}개/캐치{NLEAF}개 위치만 참고. 생산 가공 제외.
PART_ID : 부품ID. 새김가공 아님.
DIMENSIONS : 치수. 가공 금지.
GRAIN_DIRECTION : 목리방향. 가공 금지.
ASSEMBLY_REFERENCE : 조립/열림 참고. 가공 금지.
JOINT_DETAILS_REF : J1/J2/J3/J4 상세. 가공 금지.
NOTES : 제작 주석. 가공 금지.
DXF Model Space1:1, INSUNITS=mm. 모든 생산 contour의 Z=0이며 깊이는 layer/metadata에서 구분합니다.
CAM에서는 CUT_THROUGH, {POCKET_LAYER}, DOGBONE만 명시적으로 선택하십시오.

4. 홈 수량과 실제 결합
J1 고정틀{FW:g} x{FW:g} x깊이{DEPTH:g}: {NPOCK['J1']}홈, {NPOCK['J1']//2}쌍.
J2 창짝{SM:g} x{SM:g} x깊이{DEPTH:g}: {NPOCK['J2']}홈, {NPOCK['J2']//2}쌍.
J3 창살{BW:g} x{BW:g} x깊이{DEPTH:g}: {NPOCK['J3']}홈, {D['crossings_total']}개 교차점.
J4 끝단/안착{BW:g} x{LAP:g} x깊이{DEPTH:g}: {NPOCK['J4']}홈(끝단{NSEAT}+안착{NSEAT}), {NSEAT}쌍.
J4는 창살 폭{BW:g}과 삽입 길이{LAP:g}가 각각 다른 변이며 깊이{DEPTH:g}는 Z방향입니다.
총{NPOCKT}개 기본 pocket / {NPOCKT//2}쌍의 결합. 도그본{NDOG}개는 별도 집계.
S01 각각 안착{NH}개; S02 각각 안착{NV}개. 모든 창살 양 끝에 끝단 반턱2개.

5. A면 가공과 조립 시 뒤집기 — 매우 중요
원판의 공통 위쪽을 가공면A로 하여 pocket/도그본을 모두 한 면에서 가공합니다.
F01/S01/L01: 완성품에서 A면은 FRONT.
F02/S02/L02: 가공 후 뒤집어 완성품에서 A면은 BACK.
완성품 뒤z=0, 앞z={THK:g}. FRONT부품은 앞쪽z{DEPTH:g}~{THK:g}을 제거,
BACK부품은 뒤쪽z0~{DEPTH:g}을 제거하여 잔존{DEPTH:g}씩이 상보적으로 맞물립니다.
모든 부품의 A면을 앞쪽으로 향하게 조립하면 안 됩니다.
좌우/상하의 정확한 조립 변환은 parts_manifest.csv의 affine에 기록됩니다.
XY 미러 그림만을 실제 뒤집기라고 오해하지 마십시오.

6. 도그본 및 개방 경계 CAM intent
모든 S01/S02 안착 pocket은 로컬 v={SM-LAP:g}~{SM:g}이며 v={SM:g}쪽으로 개방됩니다.
안착 폭은 창살 폭{BW:g}, 안착 깊이는 삽입 길이{LAP:g}로 서로 다른 값입니다.
닫힌 코너(u_min,{SM-LAP:g}),(u_max,{SM-LAP:g})에 R{R:g}원2개를 사용합니다.
{POCKET_LAYER} 사각형과 해당 DOGBONE 2개의 합집합을 같은 깊이{DEPTH:g}로 제거합니다.
도그본을 관통구멍이나 남겨둘 island로 처리하지 마십시오.
원은 true semicircle bulge2개를 가진 폐곡선이며 단순 참조 원이 아닙니다.
이 설계의 J1/J2/J3 및 끝단 pocket들은 전폭 또는 끝단 개방형 반턱입니다.
사각 pocket이 부품 경계에 닿는 면에서는 Ø{PARAMS['machining']['tool_diameter']:g}공구가 폐기재 쪽으로 넘어가며
어깨까지 가공할 수 있도록 CAM의 개방 경계/진입/연장 조건을 설정해야 합니다.
일반 닫힌 내부pocket 경로만 쓰면 일부 모서리에 잔재가 남을 수 있습니다.
{NPOCKT}개 홈의 open_edges는 pocket_manifest.csv에 기록했습니다.
CAD 사각형은 부품 내부에 두고 실제 연장 toolpath는 CAM 담당자가 확정합니다.
관통컷과 pocket의 의도된 경계 공유는 중복 contour가 아닙니다.

7. 하드웨어와 후판
경첩{2*NLEAF}개: LEFT S01-1/F01-1, RIGHT S01-{2*NLEAF}/F01-2 각각2개.
기준 높이Y={hinge_heights()[0]:g},{hinge_heights()[1]:g}. 약{PARAMS['hardware_reference']['hinge_length']:g}길이/약{PARAMS['hardware_reference']['hinge_depth_ref']:g}깊이, 예시날개폭{PARAMS['hardware_reference']['wing_width']:g}는 REFERENCE ONLY.
폭{PARAMS['hardware_reference']['wing_width']:g}는 참고 위치를 보이기 위한 도형이며 실제 경첩 폭·구멍 치수가 아닙니다.
손잡이 참고중심({meeting_stile_centres()[0]:g},{(LY0+LY1)/2:g}),({meeting_stile_centres()[1]:g},{(LY0+LY1)/2:g}). 캐치 각창짝/고정틀에 독립1개씩.
그림 한 장과 별도 비목재 후판은 고정틀 뒤에 고정하며 창짝에 붙이지 않습니다.
그림이 창살에 닿지 않도록 실제 후방 이격과 지지방식을 확정하십시오.
현재 목재{NPART}개만으로 그림을 고정하거나 벽에 안전하게 설치할 수 있다는 뜻이 아닙니다.
후판/마운트/클립/벽고정/접착제/나사/경첩/캐치 등 별도 자재가 필요합니다.
열림 참고도의 (X,Z)=({hinge_axes()[0]:g},{THK+4:g}),({hinge_axes()[1]:g},{THK+4:g})는 방향설명용 가상축입니다.
실제 경첩/후판/나사/두창짝의 동시회전 간섭, 하중, 90도열림은 검증미완(PENDING).
HINGE_REF/LATCH_REF를 현재 A면 가공프로그램에 포함하지 마십시오.
특히 BACK조립 부품의 하드웨어 앞면 위치가 A면 가공허용을 뜻하지 않습니다.

8. 가공·조립 순서
(1) 실제 원판 평탄도/두께/결함/목리/함수율/공구경을 확인하고 시험편으로 끼움공차 확정.
(2) 목리+X 유지, A면표시. 좁은{BW:g}폭 창살이 흔들리지 않는 고정/지그/CAM방식 확정.
(3) 고정상태에서 pocket과 도그본 합집합을 먼저 깊이{DEPTH:g} 가공.
(4) 관통컷은 마지막에 실행하여 부품을 분리. 탭/얇은잔존층 등은 CAM에서 정함.
(5) 실제 부품에 ID/A면/좌우소속을 임시표시. PART_ID는 자동새김 경로가 아님.
(6) 고정틀 반턱{NPOCK['J1']//2}쌍을 가조립. 수평·직각·대각·두께를 확인.
(7) 각창짝의 L01/L02격자를 반턱으로 가조립하고 테두리안착에 넣어 맞춤 확인.
(8) 격자를 넣기 전에 테두리를 영구고정하지 말 것. 모든 홈방향/앞뒤를 맞출 것.
(9) 적합한 접착/체결방식을 작업자가 확정하여 고정틀과 각창짝을 고정.
(10) 실물경첩·캐치·손잡이를 선정하고 제품치수로 hardware별도도면을 수정한 뒤 설치.
(11) 기본{GAP_OUT:g}간극, 뒤틀림, 두창짝의 개폐순서/간섭/처짐을 실제확인.
(12) 별도 후판/그림/보호층/벽고정을 설치하고 나사 및 창살과의 간섭을 확인.
반턱은 위치를 기계적으로 안착시키지만 접착/체결 없이 분리되지 않는 잠금조인트는 아닙니다.
실내용 장식/그림보호용 명목설계입니다. 외기밀/수밀/유리받침/구조인증 창호가 아닙니다.

9. 검증과 한계
실제로 생성한 DXF를 저장한 뒤 ezdxf로 다시 읽어 {report['checks_passed']}개 검사 PASS.
검사: 부품{NPART}, pocket{NPOCKT}, 도그본{NDOG}, 크기/위치/폐곡선/층/목리/{PGAP:g}간격/{MARGIN:g}여유,
{NPOCKT//2}쌍XY와앞뒤면/Z잔존영역, 의도치않은 재료겹침, 각부품의 조립참고 일치,
창살{NV}/{NH} 배치, 경첩{2*NLEAF}/손잡이{NLEAF}/캐치{NLEAF} 위치참고, DXF audit.
검사 기대값은 design_parameters.json에서 다시 유도하며 design_spec.json을 그대로 믿지 않습니다.
검증을 통과한 파일의 SHA256은 validation_report.json에 기록됩니다.
곡선포함 재료검사는 실제 원호의 현 오차를 {ARC_CHORD_TOL_MM:g} mm 이하로 제한한 다각형 계산이며
반경/원호/bulge/내부포함은 별도로 DXF 원데이터에서도 확인합니다.
수치 정책 {POLICY_VERSION}: 치수 관계식 오차 1e-9 mm, 경계·좌표 편차 {TOL:g} mm.
면적 차만으로 도형 동등성을 판정하지 않고 양쪽 경계 전체의 거리도 확인합니다.
실제 그림의 좌·우·하·상 여유를 각각 {PMG:g} mm와 비교합니다.
실제 도그본 원호 반경을 공구 반경과 비교합니다.
홈과 자신의 도그본을 합친 뒤 동일 부재·겹치는 깊이의 서로 다른 가공 영역을 비교합니다.
의도하지 않은 겹침·접촉 및 원호·좌표 오차 범위 안의 연결 가능성은 거부합니다.
열도록 지정하지 않은 부품 가장자리에도 잔존 재료가 있어야 합니다.
현재 실측 최소 홈 사이 폭: {report['manufacturing_assessment']['machined_web']['measured_mm']:.6f} mm.
현재 실측 최소 비개방 가장자리 폭: {report['manufacturing_assessment']['edge_web']['measured_mm']:.6f} mm.
제작용 최소 폭·잔존 두께 하한은 미확정(null / PENDING)입니다. 수치 허용 오차와 다릅니다.
삽입 길이와 도그본 반경의 합은 창짝 테두리 폭보다 작아야 하며, 삽입 길이는 개구부 길이보다 클 수 있습니다.
이 패키지는 양문(창짝 2)과 방향별 창살 1개 이상만 생성합니다. 단문과 창살 0개는 파라미터 단계에서 거부합니다.
이 허용은 절삭 영역 분리·가장자리 검사와 함께 적용되며 제작 강도 승인을 뜻하지 않습니다.
실제 가공맞춤·목재강도·동적개폐·벽고정·CAM시뮬레이션·기계운전은 승인하지 않았습니다.
기본{DEPTH:.2f}홈/{DEPTH:.2f}부품은 명목 무공차이며 시험편 후 공차보정이 필요합니다.

10. 파일 — 패키지 구성
패키지 루트/00_START_HERE.txt : 진입 안내
패키지 루트/package_manifest.json : 전체 파일의 경로·크기·SHA-256
패키지 루트/01_plan/MERGED_PLAN.md : 병합 계획서. 단독 재생성 사양
패키지 루트/01_plan/PLAN_RECONCILIATION.md : 선행 계획서 2건 대조와 채택 근거
패키지 루트/01_plan/SPEC_UNIFICATION.md : 구조 통일과 결함 수정 이력
이 폴더(02_cnc)의 파일:
design_parameters.json : 유일한 규격 원본. 여기만 수정합니다.
generate_spec.py : 파라미터에서 부품/홈/도그본/네스팅을 유도. design_spec.json 생성.
design_spec.json : 생성물. 직접 수정 금지.
{DXF.name} : 최신 실제 DXF
01_one_board_nesting.png : 원판 전체 및 동일부품확대
02_joinery_details.png : J1/J2/J3/J4 및 깊이단면
03_assembly_reference.png : 세로형 양개 닫힘정면
04_opening_reference.png : 좌우열림 설명용 평면도 (REFERENCE ONLY)
05_all_pockets_closeup.png : {NPOCKT}홈/{NDOG}도그본 위치 확대
validation_report.json : 실제저장DXF 재읽기검증
parts_manifest.csv / pocket_manifest.csv / dogbone_manifest.csv : 치수·좌표·대응표
hardware_reference_manifest.csv : 참고하드웨어만 분리집계
build_portrait_double_leaf.py / cad_helpers.py : DXF 생성·검증·도면 렌더링
numeric_policy.py / machining_checks.py : 수치 오차 정책, 실제 원호·절삭 영역·가장자리 검증
verify_package.py : 파일 무결성 대조(기본 읽기전용). package_manifest.json 생성은 --write
requirements.txt : 검증에 사용한 Python 버전과 라이브러리

재실행: 이폴더에서 python build_portrait_double_leaf.py
검증에 실패하면 기존 DXF·design_spec.json·PNG·CSV·검증 리포트를 바꾸지 않습니다.
기존DXF 검사만: python build_portrait_double_leaf.py --validate-only
규격 대조만: python generate_spec.py --compare <다른 design_spec.json>
무결성 대조: python verify_package.py           (읽기전용. 불일치 시 종료코드1)
매니페스트 재작성: python verify_package.py --write
회귀 시험(임시 폴더에서 실행): python ../03_tests/test_regressions.py
최적화 실행에서도 같은 시험: PYTHONOPTIMIZE=1 python ../03_tests/test_regressions.py
두 실행을 묶은 기록: python ../03_tests/test_regressions.py --record ../03_tests/regression_results.json

재현 범위: 빌드는 PYTHONHASHSEED=0으로 스스로 재실행하고 DXF 메타데이터를 고정합니다.
- DXF는 같은 파라미터·코드·라이브러리 버전에서 같은 바이트입니다. 폰트 환경과 무관합니다.
- PNG는 같은 폰트 파일과 같은 Pillow 버전이 잡힐 때만 같습니다.
  HANOK_FONT를 바꾸면 검사는 그대로 통과하지만 PNG 해시 5개가 전부 달라집니다.
  실제 사용된 폰트는 validation_report.json의 render_environment에 기록됩니다.
따라서 DXF 해시가 달라졌다면 파라미터나 코드가 바뀐 것이고,
PNG 해시만 달라졌다면 먼저 폰트 환경을 확인하십시오.
검사전용 결과는 validation_report_recheck.json이며 기존 PNG를 다시 만들지 않습니다.
필요폰트가 없으면 시스템DejaVu/Arial을 사용하며, HANOK_FONT 환경변수로 대체가능.
이패키지에는 폰트파일을 포함하지 않습니다.
'''
    (OUT/'README.txt').write_text(textout,encoding='utf-8')
    import sys,shapely,PIL
    fonts=' / '.join(f'{k}={v}' for k,v in sorted(FONTS_USED.items())) or 'not recorded'
    (OUT/'requirements.txt').write_text(
        f'# Verified on Python {sys.version_info.major}.{sys.version_info.minor}.'
        f'{sys.version_info.micro} ({PARAMS["revision"]}).\n'
        f'# Versions below record this verification environment; upgrade in a separate tested environment.\n'
        f'# No font is bundled. The DXF does not depend on one, but reproducing the PNG\n'
        f'# bytes needs the same faces this build resolved:\n'
        f'#   {fonts}\n'
        f'# Override with the HANOK_FONT environment variable.\n'
        f'ezdxf=={ezdxf.__version__}\nshapely=={shapely.__version__}\nPillow=={PIL.__version__}\n',
        encoding='utf-8')


def reexec_with_fixed_hash_seed():
    """Restart once under PYTHONHASHSEED=0 so the output is byte-reproducible.

    ezdxf walks a few string-keyed collections while writing the CLASSES section,
    and Python randomises string hashing per process, so two runs otherwise order
    the LAYOUT and ACDBPLACEHOLDER classes differently. Everything else is already fixed, so
    this one variable is the difference between a manifest that proves a rebuild
    matches and one that reports a change on every run. Set the variable yourself
    to skip the restart; if the restart is refused the build still succeeds, just
    without the byte guarantee.
    """
    import os,sys
    if os.environ.get('PYTHONHASHSEED')=='0':return
    try:
        os.execve(sys.executable,[sys.executable,*sys.argv],{**os.environ,'PYTHONHASHSEED':'0'})
    except OSError as exc:
        print(f'warning: could not re-exec with PYTHONHASHSEED=0 ({exc}); '
              'output stays valid but is not byte-reproducible')


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
        reexec_with_fixed_hash_seed()
        doc,rep,positions=build()
        render_nesting(doc,rep);render_details(doc,positions);render_assembly(doc)
        render_opening(doc);render_closeup(doc,rep)
        write_readme(rep)
        # The DXF is byte-reproducible on its own, but the PNGs are rasterised
        # with whatever font files this machine resolves, so record them: a PNG
        # hash that moves without a parameter change is almost always this.
        import os
        rep['render_environment']=dict(fonts=dict(FONTS_USED),
                                       hanok_font_env=os.environ.get('HANOK_FONT',''),
                                       note='PNG bytes depend on these fonts; the DXF does not.')
        (OUT/'validation_report.json').write_text(json.dumps(rep,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        # Written last so the manifest always describes the files just produced.
        import verify_package;verify_package.write_manifest()
    print(json.dumps({k:rep[k] for k in ['status','revision','checks_passed','saved_dxf_reread','parts_total',
                                         'nominal_pockets_total','dogbone_reliefs_total','mated_joints_total',
                                         'lattice_per_leaf','minimum_part_gap_mm','minimum_board_margin_mm']},indent=2))

if __name__=='__main__':main()
