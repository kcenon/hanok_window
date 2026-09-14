"""Create and re-read-validate one nominal design in a dedicated worker process."""
from __future__ import annotations
import argparse, csv, hashlib, itertools, json, math
from collections import Counter, defaultdict
from pathlib import Path
import ezdxf
from shapely.geometry import Polygon, Point, box
from shapely.affinity import affine_transform, translate, rotate
from shapely.ops import unary_union
from PIL import Image, ImageDraw
from .cad_helpers import *
from .numeric_policy import (POLICY_VERSION, LENGTH_TOL_MM, RATIO_TOL, AREA_TOL_MM2,
                            VOLUME_TOL_MM3, ARC_CHORD_TOL_MM, close, coordinates_match,
                            geometry_matches, polyline_arcs, policy_record)
from .machining_checks import measure_machining
from .. import formats
from .generate_spec import (build as build_spec, derive, bar_offsets, leaf_bounds,
                           opening_bounds, group_name)

# Reproducible output. Without this, ezdxf stamps the save time into $TDCREATE
# and $TDUPDATE, issues fresh $VERSIONGUID and $FINGERPRINTGUID values, and dates
# its own written-by marker, so two builds of identical geometry hash
# differently and package_manifest.json cannot tell a rebuild from an edit. The
# option only substitutes constants for those provenance fields; no geometry,
# layer or metadata content is affected. The revision travels in document
# metadata and on the sheet instead - see pin_build_identity.
ezdxf.options.write_fixed_meta_data_for_testing=True

def configure(parameters, output):
    """Configure once inside a dedicated job process; no input is read on import."""
    global A3H, A3W, ASSEMBLY_ORIGIN, BL, BT, BW, BWD, D, DEPTH, DXF, FORMAT, FW, GAP_MID, GAP_OUT, H, IH, IW, LAP, LAYERS, LEAVES, LH, LW, LY0, LY1, MARGIN, MINR, NDOG, NH, NLEAF, NPART, NPOCK, NPOCKT, NSEAT, NV, OH, OPENINGS, OPENING_ORIGIN, OUT, OW, PARAMS, PGAP, PICTURE, PICX, PICY, PMG, POCKET_LAYER, PRH, PRW, PX, PY, R, SIZE, SIZES, SM, SPEC, THK, TITLE, TOL, W, i
    OUT=Path(output)
    DXF=OUT/'window.dxf'
    SPEC=OUT/'design_spec.json'
    TOL=LENGTH_TOL_MM
    PARAMS=parameters
    D=derive(PARAMS)
    ASSEMBLY_ORIGIN=(1350.,100.)
    OPENING_ORIGIN=(1350.,-370.)
    
    # Named shorthands for the derived design. No literal millimetre value appears
    # below this block; change design_parameters.json instead.
    W,H=D['board_w'],D['board_h']
    IW,IH=D['inner_w'],D['inner_h']
    # 0.1.0 parameter files carry no size record; those were always outer-based.
    SIZE=PARAMS.get('size') or dict(basis='outer',requested_mm=[W,H])
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
    
    FORMAT=formats.leaves(PARAMS)
    TITLE=formats.title(PARAMS)
    PICTURE=PARAMS["picture"]["enabled"]
    PICX=PX+(PRW-A3W)/2
    PICY=PY+(PRH-A3H)/2


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


def face_note():
    front=' / '.join(k for k,(_,_,count) in SIZES.items() if count and k in ('F01','S01','L01'))
    back=' / '.join(k for k,(_,_,count) in SIZES.items() if count and k in ('F02','S02','L02'))
    return f'{front}: A -> FRONT. {back}: flip A -> BACK.'


def add_board(m,spec):
    tot=spec['derived']['totals'];top=spec['derived']['nesting_bounds'][3]
    rect(m,0,0,BL,BWD,'BOARD_BOUNDARY',kind='board',view='nest',size_mm=[BL,BWD,BT])
    text(m,f'HANOK WINDOW / {TITLE}',(0,BWD+55),13,kind='title',view='nest')
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
           face_note(),
           f'{POCKET_LAYER} + DOGBONE: UNION, REMOVE {DEPTH:g} mm. OPEN LAPS NEED WASTE-SIDE OVERRUN.',
           'HINGE_REF / LATCH_REF ARE POSITION REFERENCES ONLY. DO NOT MACHINE.',
           'NOMINAL FIT: VERIFY STOCK, TEST COUPONS, WORKHOLDING AND CAM BEFORE CUTTING.']
    for i,s in enumerate(notes):text(m,s,(30,BWD-48-i*20),6.6,view='nest')
    text(m,'No G-code, tabs, toolpaths, feeds or speeds are included. All hardware and backing remain PENDING.',
         (0,-35),5.3,view='nest')


def hinge_axes():
    """Provisional vertical swing axes, midway between frame and leaf edges."""
    return [(FW+LEAVES[f.index][0])/2 if f.side=='left'
            else (LEAVES[f.index][2]+W-FW)/2 for f in FORMAT]


def hinge_heights():
    inset=PARAMS['hardware_reference']['hinge_inset_from_leaf_end']
    return [LY0+inset,LY1-inset]


def meeting_stile_centres():
    """Centre line of each leaf's handle-side stile, away from its hinges."""
    return [LEAVES[f.index][2]-SM/2 if f.side=='left' else LEAVES[f.index][0]+SM/2 for f in FORMAT]


def hardware_records():
    hw=PARAMS['hardware_reference'];out=[]
    ww,wi,hl=hw['wing_width'],hw['wing_inset'],hw['hinge_length']
    for form in FORMAT:
        side,pf,ps=form.side.upper(),form.fixed_stile,form.hinge_stile
        xf=FW-wi-ww if form.side=='left' else W-FW+wi
        xs=LEAVES[form.index][0]+wi if form.side=='left' else LEAVES[form.index][2]-wi-ww
        for idx,y in enumerate(hinge_heights(),1):
            hid=f'H-{side}-{idx}'
            for pid,x,wing in [(pf,xf,'FIXED'),(ps,xs,'SASH')]:
                out.append(dict(hardware_id=hid,part_id=pid,layer='HINGE_REF',
                                box=[x,y-hl/2,x+ww,y+hl/2],hardware_type='HINGE',wing=wing,
                                depth_ref_mm=hw['hinge_depth_ref']))
    hx=meeting_stile_centres();hwd,hht=hw['handle_width'],hw['handle_height']
    cy=(LY0+LY1)/2
    for i,(x,form) in enumerate(zip(hx,FORMAT),1):
        pid=form.handle_stile
        out.append(dict(hardware_id=f'HANDLE-{i}',part_id=pid,layer='LATCH_REF',
                        box=[x-hwd/2,cy-hht/2,x+hwd/2,cy+hht/2],hardware_type='HANDLE'))
    cs=hw['catch_size'];sy=LY1-hw['catch_inset_from_leaf_top']
    fy=H-FW+hw['catch_inset_from_frame_inner_top']
    for i,(x,form) in enumerate(zip(hx,FORMAT),1):
        if NLEAF==1:
            # Provisional catch above the handle on its opposite-hinge stile.
            fx=W-FW/2 if form.side=='left' else FW/2
            placements=[(form.handle_stile,x,cy+hht+cs),
                        ('F01-2' if form.side=='left' else 'F01-1',fx,cy+hht+cs)]
        else:
            placements=[(form.top_rail,x,sy),('F02-2',x,fy)]
        for pid,cx,cc in placements:
            out.append(dict(hardware_id=f'CATCH-{i}',part_id=pid,layer='LATCH_REF',
                            box=[cx-cs/2,cc-cs/2,cx+cs/2,cc+cs/2],hardware_type='CATCH'))
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
    text(m,f'{TITLE} / W{W:g} x H{H:g}',(ox,oy+H+84),10,view='assembly',kind='title')
    text(m,f'{NLEAF} LEAF / REFERENCE ONLY',(ox,oy+H+61),5,view='assembly')
    if PICTURE:
        rect(m,ox+PICX,oy+PICY,A3W,A3H,'ASSEMBLY_REFERENCE',view='assembly',role='picture',
             nominal_size=[A3W,A3H],dxf_role='rear_picture')
    # This reflects the same parts and transformations as the machining layout.
    for p in sorted(parts.values(),key=lambda p:(p['face_a']=='BACK',p['part_id'])):
        g=translate(local_to_assembly(p,box(0,0,p['length'],p['width'])),ox,oy)
        poly(m,list(g.exterior.coords)[:-1],'ASSEMBLY_REFERENCE',view='assembly',role='body',
             part_id=p['part_id'],assembly_group=p['assembly_group'])
    if PICTURE:
        rect(m,ox+PX,oy+PY,PRW,PRH,'ASSEMBLY_REFERENCE',view='assembly',role='picture_region',nominal_size=[PRW,PRH])
    for x0,y0,x1,y1 in OPENINGS:
        rect(m,ox+x0,oy+y0,x1-x0,y1-y0,'ASSEMBLY_REFERENCE',view='assembly',role='opening',nominal_size=[OW,OH])
    # Outer (외경) and fixed-frame inner (내경) are both dimensioned; the basis the
    # size was requested in carries an INPUT mark.
    mark={b:(' (INPUT)' if SIZE['basis']==b else '') for b in ('outer','inner')}
    dimh(m,ox,ox+W,oy+H,oy+H+27,f'{W:g} OVERALL'+mark['outer'],view='assembly')
    dimv(m,oy,oy+H,ox+W,ox+W+36,f'{H:g} OVERALL'+mark['outer'],view='assembly')
    dimh(m,ox+FW,ox+W-FW,oy+FW,oy-72,f'{IW:g} FRAME INNER'+mark['inner'],view='assembly')
    dimv(m,oy+FW,oy+H-FW,ox+FW,ox-58,f'{IH:g} FRAME INNER'+mark['inner'],view='assembly')
    names=['LEFT','RIGHT'] if NLEAF==2 else ['SINGLE']
    for (x0,y0,x1,y1),nm in zip(LEAVES,names):
        dimh(m,ox+x0,ox+x1,oy+y0,oy-18,f'{LW:g} {nm} LEAF',view='assembly')
    dimv(m,oy+LY0,oy+LY1,ox,ox-29,f'{LH:g} LEAF',view='assembly')
    for x0,y0,x1,y1 in OPENINGS:
        dimh(m,ox+x0,ox+x1,oy+y1,oy+y1+51,f'{OW:g} OPENING',view='assembly')
    dimv(m,oy+PY,oy+PY+OH,ox+OPENINGS[-1][2],ox+OPENINGS[-1][2]+52,f'{OH:g} OPENING',view='assembly')
    if PICTURE:
        text(m,f'PICTURE {A3W:g} x {A3H:g}',(ox+W/2,oy+PY+24),6,'ASSEMBLY_REFERENCE','center',view='assembly',role='picture_label')
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
    gaptext=f'{GAP_MID:g} mm centre gap / ' if NLEAF==2 else ''
    text(m,gaptext+f'{GAP_OUT:g} mm external clearances',(ox+W/2,oy-39),4.7,align='center',view='assembly')
    if PICTURE:
        text(m,f'Fixed rear picture region {PRW:g} x {PRH:g}; leaf members obscure the closed front.',
             (ox+W/2,oy-53),3.8,align='center',view='assembly')


def add_opening(m):
    """Illustrative plan at 90 degrees; provisional axis only, not hardware approval."""
    ox,oy=OPENING_ORIGIN;arc=min(120,LW*.65);axz=THK+4
    heading=max(330,LW+THK+80)
    text(m,'OPENING REFERENCE / PLAN (LOOKING DOWN)',(ox,oy+heading),8,view='opening',kind='title')
    text(m,'REFERENCE ONLY / AXES AND BACKING POSITION NOT FINAL',(ox,oy+heading-20),4.7,view='opening')
    for g in [box(0,0,FW,THK),box(W-FW,0,W,THK)]:
        poly(m,list(translate(g,ox,oy).exterior.coords)[:-1],'ASSEMBLY_REFERENCE',view='opening',role='body')
    axes=hinge_axes()
    for form,ax in zip(FORMAT,axes):
        name=form.side.upper();lx0,_,lx1,_=LEAVES[form.index]
        deg=form.angle;sg=1 if form.side=='left' else -1
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
    if PICTURE:
        rect(m,ox+PICX,oy-axz,A3W,4,'ASSEMBLY_REFERENCE',view='opening',role='picture',reference_only=True)
        line(m,(ox+PX,oy-axz-5),(ox+PX+PRW,oy-axz-5),'ASSEMBLY_REFERENCE',view='opening',reference_only=True)
        text(m,'PICTURE FIXED ON SEPARATE REAR SUPPORT',(ox+W/2,oy-47),4.4,align='center',view='opening')
    if NLEAF==2:
        text(m,'CENTRE MEMBERS MOVE WITH EACH LEAF',(ox+W/2,oy+247),5,align='center',view='opening')
    text(m,'NO FIXED CENTRE MULLION',(ox+W/2,oy+265),6,align='center',view='opening')
    text(m,'VIEWER / FRONT +Z',(ox+W/2,oy+222),5,align='center',view='opening')
    axes_label=', '.join(f'({ax:g},{axz:g})' for ax in axes)
    text(m,f'Illustrative axes: (X,Z)={axes_label}. Recheck selected hardware.',
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
    tmpspec.write_bytes((json.dumps(spec,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    try:
        pre=validate(doc,'IN_MEMORY_BEFORE_SAVE',tmpspec)
        with open(tmp,'wt',encoding=doc.output_encoding,errors='dxfreplace',newline='\n') as fp:doc.write(fp)
        checkdoc=ezdxf.readfile(tmp)
        report=validate(checkdoc,'READ_BACK_FROM_SAVED_DXF',tmpspec)
    except BaseException:
        tmp.unlink(missing_ok=True);tmpspec.unlink(missing_ok=True)
        raise
    tmpspec.replace(SPEC);tmp.replace(DXF)
    report.update(file=DXF.name,sha256=hashlib.sha256(DXF.read_bytes()).hexdigest(),
                  pre_save_status=pre['status'],ezdxf_version=ezdxf.__version__)
    (OUT/'validation_report.json').write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
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
    expectations={
        'unique_part_ids_and_total':NPART, 'board_boundary':dict(count=1,bounds=[0,0,BL,BWD]),
        'minimum_nesting_gap':PGAP, 'minimum_board_edge_margin':MARGIN,
        'total_base_pockets':NPOCKT, 'S01_J4_seats_each':NH,'S02_J4_seats_each':NV,
        'lattice_bars_per_leaf':[NV,NH], 'corner_reliefs':dict(count=NDOG,radius_mm=R),
        'half_lap_depth':dict(retained_front=THK/2,retained_back=THK/2,stock=THK),
        'frame_geometry':dict(bounds=[0,0,W,H],area_mm2=W*H-D['inner_w']*D['inner_h']),
        'leaf_envelopes':[[LW,LH]]*NLEAF, 'leaf_height_to_width_ratio':MINR,
        'leaf_clearances':dict(external=GAP_OUT,meeting=GAP_MID if NLEAF==2 else None),
        'picture_geometry':dict(enabled=PICTURE,size_mm=[A3W,A3H]),
        'picture_margins_match_each_side':dict(minimum_mm=PMG,centred=True),
        'leaf_opening_references':dict(count=NLEAF,size_mm=[OW,OH]),
        'hardware_counts_and_references':dict(HINGE=2*NLEAF,HANDLE=NLEAF,CATCH=NLEAF),
        'reference_details_match_existing_joints':sorted(formats.detail_variants(PARAMS)),
        'opening_illustration_matches_leaves':NLEAF,
        **{f'{joint}_pocket_count':quantity for joint,quantity in NPOCK.items()},
    }
    def check(name,ok,detail=None,target=None):
        expected=expectations.get(name,True)
        # Predicate checks report the observed truth value; contextual measurements
        # remain separate. Quantitative checks report the actual measured data.
        actual=detail if name in expectations and detail is not None else bool(ok)
        if isinstance(detail,dict) and 'actual' in detail and 'required' in detail:
            expected=detail['required'];actual=detail['actual']
        target=target or ('lattice_per_leaf' if 'lattice' in name or 'pocket' in name or name.startswith(('S01_','S02_')) else 'picture' if 'picture' in name else 'stock_mm' if 'board' in name else 'saved_dxf')
        count_check=name.endswith('_count') or name in ('unique_part_ids_and_total','total_base_pockets','hardware_counts_and_references')
        tolerance=dict(absolute=0,unit='count') if count_check else dict(policy=POLICY_VERSION,length_mm=TOL)
        checks.append(dict(rule_id=name,name=name,message=name.replace('_',' '),
                           status='PASS' if ok else 'FAIL',expected=expected,actual=actual,
                           measured=detail,tolerance=tolerance,targets=[target]))
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
    check('all_part_sizes_match_spec',all(
        abs(g.bounds[2]-g.bounds[0]-SIZES[pid[:3]][0])<TOL and
        abs(g.bounds[3]-g.bounds[1]-SIZES[pid[:3]][1])<TOL and
        geometry_matches(g,box(g.bounds[0],g.bounds[1],g.bounds[0]+SIZES[pid[:3]][0],g.bounds[1]+SIZES[pid[:3]][1]))
        for pid,g in partgeo.items()))
    boardents=[e for e in ents if e.dxf.layer=='BOARD_BOUNDARY']
    check('board_boundary',len(boardents)==1 and geometry_matches(entity_polygon(boardents[0]),box(0,0,BL,BWD)),
          dict(count=len(boardents),bounds=list(entity_polygon(boardents[0]).bounds) if boardents else None))
    check('all_parts_within_board',all(box(0,0,BL,BWD).buffer(TOL).covers(g) for g in partgeo.values()))
    pairs=list(itertools.combinations(partgeo,2))
    overlap=max(partgeo[a].intersection(partgeo[b]).area for a,b in pairs)
    gap=min(partgeo[a].distance(partgeo[b]) for a,b in pairs)
    margin=min(min(g.bounds[0],g.bounds[1],BL-g.bounds[2],BWD-g.bounds[3]) for g in partgeo.values())
    check('no_nesting_overlap',overlap<AREA_TOL_MM2,overlap)
    check('minimum_nesting_gap',gap>=PGAP-TOL,gap)
    check('minimum_board_edge_margin',margin>=MARGIN-TOL,margin)
    check('all_lengths_parallel_X_grain',all(g.bounds[2]-g.bounds[0]>g.bounds[3]-g.bounds[1] for g in partgeo.values()))
    bypart=defaultdict(list);byjoint=Counter();by_pair=defaultdict(list)
    for e in pockets:
        d=meta(e);bypart[d['part_id']].append(e);byjoint[d['joint']]+=1;by_pair[d['joint_id']].append(e)
    for j,n in NPOCK.items():check(f'{j}_pocket_count',byjoint[j]==n,byjoint[j])
    check('total_base_pockets',len(pockets)==NPOCKT,len(pockets))
    expected={'F01':2,'F02':2,'S01':2+NH,'S02':2+NV,'L01':2+NH,'L02':2+NV}
    check('pockets_per_part',all(len(bypart[p])==expected[p[:3]] for p in partents))
    check('S01_J4_seats_each',all(sum(meta(e)['joint']=='J4' and meta(e)['seat'] for e in bypart[p])==NH for p in partents if p.startswith('S01')),
          {p:sum(meta(e)['joint']=='J4' and meta(e)['seat'] for e in bypart[p]) for p in partents if p.startswith('S01')})
    check('S02_J4_seats_each',all(sum(meta(e)['joint']=='J4' and meta(e)['seat'] for e in bypart[p])==NV for p in partents if p.startswith('S02')),
          {p:sum(meta(e)['joint']=='J4' and meta(e)['seat'] for e in bypart[p]) for p in partents if p.startswith('S02')})
    check('all_lattice_two_end_laps',all(sum(meta(e)['joint']=='J4' for e in bypart[p])==2 for p in partents if p.startswith('L')))
    check('lattice_crossing_pockets',all(sum(meta(e)['joint']=='J3' for e in bypart[p])==(NH if p.startswith('L01') else NV) for p in partents if p.startswith('L')))
    byleaf=Counter((meta(e)['assembly_group'],meta(e)['family']) for e in rawparts)
    check('lattice_bars_per_leaf',all(
        byleaf[(group_name(D,i),'L01')]==NV and byleaf[(group_name(D,i),'L02')]==NH for i in range(NLEAF)),
        {group_name(D,i):[byleaf[(group_name(D,i),'L01')],byleaf[(group_name(D,i),'L02')]] for i in range(NLEAF)})
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
    check('corner_reliefs',bool(dogok),dict(count=len(dogs),radii_mm=sorted({arc[2] for e in dogs for arc in polyline_arcs(e)})))
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
    check('joint_pairs_XY_match_opposite_faces',bool(pairgood),{'pairs':len(by_pair),'max_mismatch_area_mm2':maxmismatch})
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
    check('half_lap_depth',abs(2*DEPTH-THK)<TOL,
          {'retained_front':THK-DEPTH,'retained_back':THK-DEPTH,'stock':THK})
    fixed=unary_union([g for pid,g in ap.items() if pid.startswith('F')])
    leaves=[unary_union([g for pid,g in ap.items() if meta(partents[pid])['assembly_group']==group_name(D,i)]) for i in range(NLEAF)]
    check('frame_geometry',geometry_matches(fixed,box(0,0,W,H).difference(box(FW,FW,W-FW,H-FW))),
          dict(bounds=list(fixed.bounds),area_mm2=fixed.area))
    # Re-measure the size in the basis it was requested in: the outer boundary of
    # the assembled fixed frame, or the clear opening that frame encloses.
    holes=[box(*ring.bounds) for ring in getattr(fixed,'interiors',[])]
    hole=max(holes,key=lambda g:g.area).bounds if holes else None
    measured=dict(outer=[fixed.bounds[2]-fixed.bounds[0],fixed.bounds[3]-fixed.bounds[1]],
                  inner=[hole[2]-hole[0],hole[3]-hole[1]] if hole else None)
    got=measured[SIZE['basis']]
    check('requested_size_matches_measured_frame',
          got is not None and all(abs(a-b)<TOL for a,b in zip(got,SIZE['requested_mm'])),
          dict(actual=got,required=SIZE['requested_mm'],basis=SIZE['basis'],measured_mm=measured),
          target='inner_mm' if SIZE['basis']=='inner' else 'outer_mm')
    check('leaf_envelopes',all(
        coordinates_match(lf.bounds,LEAVES[i]) for i,lf in enumerate(leaves)),
        [[lf.bounds[2]-lf.bounds[0],lf.bounds[3]-lf.bounds[1]] for lf in leaves])
    # Read the proportion off the assembled members rather than from LW/LH, so it
    # still holds if the leaf envelope itself were derived wrongly.
    ratios=[(lf.bounds[3]-lf.bounds[1])/(lf.bounds[2]-lf.bounds[0]) for lf in leaves]
    check('leaf_height_to_width_ratio',all(r>=MINR-RATIO_TOL for r in ratios),
          [round(r,6) for r in ratios])
    gapsok=all(abs(lf.distance(fixed)-GAP_OUT)<TOL for lf in leaves)
    gapsok &= all(abs(leaves[i].distance(leaves[i+1])-GAP_MID)<TOL for i in range(NLEAF-1))
    check('leaf_clearances',gapsok,dict(external=[lf.distance(fixed) for lf in leaves],
          meeting=[leaves[i].distance(leaves[i+1]) for i in range(NLEAF-1)]))
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
            if len(frame_members)!=2:spacing_ok=False;continue
            span0=frame_members[0].bounds[axis+2];span1=frame_members[1].bounds[axis]
            widths=[g.bounds[axis+2]-g.bounds[axis] for g in bars]
            edges=[span0]+[c for g in bars for c in (g.bounds[axis],g.bounds[axis+2])]+[span1]
            gaps=[edges[j+1]-edges[j] for j in range(0,len(edges)-1,2)]
            want=(span1-span0-sum(widths))/(len(bars)+1)
            spacing_ok &= len(gaps)==len(bars)+1 and want>0
            spacing_ok &= not widths or max(widths)-min(widths)<TOL
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
    pictures=[e for e in assemblies if meta(e).get('role')=='picture']
    regions=[e for e in assemblies if meta(e).get('role')=='picture_region']
    margins={};picture_ok=not pictures and not regions;line_ok=picture_ok;margin_ok=picture_ok
    if PICTURE:
        picture_ok=len(pictures)==len(regions)==1;line_ok=margin_ok=False
        if picture_ok:
            pic,reg=pictures[0],regions[0]
            pg=translate(entity_polygon(pic),-ox,-oy);rg=translate(entity_polygon(reg),-ox,-oy)
            picture_ok=geometry_matches(pg,box(PICX,PICY,PICX+A3W,PICY+A3H)) and geometry_matches(rg,box(PX,PY,PX+PRW,PY+PRH))
            px0,py0,px1,py1=pg.bounds;rx0,ry0,rx1,ry1=rg.bounds
            margins=dict(left=px0-rx0,right=rx1-px1,bottom=py0-ry0,top=ry1-py1)
            margin_ok=rg.buffer(TOL).covers(pg) and all(v>=PMG-TOL for v in margins.values()) and close(margins['left'],margins['right'],TOL) and close(margins['top'],margins['bottom'],TOL)
            line_ok=pic.dxf.linetype!=reg.dxf.linetype
    check('picture_geometry',picture_ok,dict(enabled=PICTURE,pictures=len(pictures),regions=len(regions)))
    check('picture_margins_match_each_side',margin_ok,dict(required_minimum_mm=PMG,measured_mm=margins))
    check('picture_reference_linetypes',line_ok)
    openings=[e for e in assemblies if meta(e).get('role')=='opening']
    opening_geometry=[entity_polygon(e) for e in openings]
    check('leaf_opening_references',len(openings)==NLEAF and all(
        geometry_matches(g,box(g.bounds[0],g.bounds[1],g.bounds[0]+OW,g.bounds[1]+OH)) for g in opening_geometry),
        dict(count=len(openings),sizes_mm=[[g.bounds[2]-g.bounds[0],g.bounds[3]-g.bounds[1]] for g in opening_geometry]))
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
    check('hardware_counts_and_references',
          bool(hwmatch) and {k:len(v) for k,v in hwtype.items()}==wanthw,{k:len(v) for k,v in hwtype.items()})
    expected_hw={(r['hardware_id'],r['part_id']):box(*r['box']) for r in hardware_records()}
    actual_hw={(meta(e)['hardware_id'],meta(e)['part_id']):assembled(meta(e)['part_id'],entity_polygon(e)) for e in hws}
    check('hardware_attachment_geometry',set(actual_hw)==set(expected_hw) and all(geometry_matches(g,expected_hw[k]) for k,g in actual_hw.items() if k in expected_hw),
          dict(attachments=[list(k) for k in actual_hw]))
    detailtypes={meta(e).get('detail') for e in ents if meta(e).get('view')=='detail'}
    check('reference_details_match_existing_joints',detailtypes==({'J1','J2'} | ({'J3'} if byjoint['J3'] else set()) | ({'J4V'} if count['L01'] else set()) | ({'J4H'} if count['L02'] else set())),sorted(detailtypes))
    detailborders=[e for e in ents if meta(e).get('kind')=='detail_border']
    check('reference_detail_members_exist',all(all(count[k]>0 for k in meta(e)['detail_part_kinds']) for e in detailborders),[meta(e)['detail_part_kinds'] for e in detailborders])
    check('references_never_on_machining_layers',not any(meta(e).get('view') in ['assembly','detail','opening'] for e in mach))
    opened=[e for e in ents if meta(e).get('kind')=='opened_leaf_illustration']
    check('opening_illustration_matches_leaves',len(opened)==NLEAF and {meta(e).get('leaf') for e in opened}=={f.side.upper() for f in FORMAT} and all(meta(e).get('reference_only') for e in opened),len(opened))
    check('pockets_open_edge_intent',all(bool(meta(e).get('open_edges')) for e in pockets))
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
            fields=list(rows[0]) if rows else ['part_id','feature_id','parent_pocket','center_u_mm','center_v_mm','radius_mm','depth_mm','intent','dxf_handle']
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
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
    variants=formats.detail_variants(PARAMS)
    positions={key:(ASSEMBLY_ORIGIN[0]+W+160+(i%2)*270,100+(2-i//2)*210) for i,key in enumerate(variants)}
    for key,(ox,oy) in positions.items():
        j='J4' if key.startswith('J4') else key
        kinds={'J1':['F01','F02'],'J2':['S01','S02'],'J3':['L01','L02'],'J4V':['S02','L01'],'J4H':['S01','L02']}[key]
        common={'detail':key,'view':'detail','detail_part_kinds':kinds,'joint_type':j}
        def tx(s,x,y,h=3.8,align='left',layer='NOTES'):
            return text(MSP,s,(ox+x,oy+y),h,layer,align,**common)
        def rr(x,y,w,h,role='body',**kw):
            return rect(MSP,ox+x,oy+y,w,h,'JOINT_DETAILS_REF',role=role,**common,**kw)
        def pp(pts,role='body',**kw):
            if key=='J4H':role={'section_front':'section_back','section_back':'section_front'}.get(role,role)
            return poly(MSP,[(ox+x,oy+y) for x,y in pts],'JOINT_DETAILS_REF',role=role,**common,**kw)
        rect(MSP,ox,oy,240,190,'NOTES',kind='detail_border',**common)
        names={'J1':'FIXED FRAME HALF-LAP','J2':'SASH HALF-LAP',
               'J3':'LATTICE CROSSING HALF-LAP','J4':'LATTICE-TO-SASH SEAT'}
        tx(f'{key}  {names[j]}',10,178,7)
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
            dimh(MSP,ox+15,ox+15+n,oy+by,oy+by-9,f'{n:g}',detail=key)
            dimv(MSP,oy+by,oy+by+n,ox+95,ox+104,f'{n:g}',detail=key)
            dimh(MSP,ox+135,ox+135+n,oy+by,oy+by-9,f'{n:g}',detail=key)
            # Section schematic: complementary retained halves at their overlap.
            sx=70; sy=36
            pp([(sx,sy),(sx+20+n,sy),(sx+20+n,sy+DEPTH),(sx+20,sy+DEPTH),
                (sx+20,sy+THK),(sx,sy+THK)],'section_back')
            pp([(sx+20,sy+DEPTH),(sx+20+n,sy+DEPTH),(sx+20+n,sy),
                (sx+40+n,sy),(sx+40+n,sy+THK),(sx+20,sy+THK)],'section_front')
            dimv(MSP,oy+sy,oy+sy+THK,ox+sx+40+n,ox+sx+50+n,f'{THK:g}',detail=key)
            dimv(MSP,oy+sy+DEPTH,oy+sy+THK,ox+sx+20+n,ox+sx+66+n,f'{DEPTH:g} depth',detail=key)
            tx('ASSEMBLED SECTION - complementary faces',15,69,4)
            tx('Local end regions only; open edges need cutter overrun in CAM.',10,18,3.3)
        elif j=='J3':
            tx('L01 / A -> FRONT',15,148,4)
            tx('L02 / A -> BACK (flip)',135,148,3.7)
            rr(15,125,80,BW);rr(135,125,80,BW)
            rr(50,125,BW,BW,'pocket');rr(170,125,BW,BW,'pocket')
            dimh(MSP,ox+50,ox+50+BW,oy+125,oy+112,f'{BW:g}',detail=key)
            dimv(MSP,oy+125,oy+125+BW,ox+95,ox+105,f'{BW:g}',detail=key)
            dimh(MSP,ox+170,ox+170+BW,oy+125,oy+112,f'{BW:g}',detail=key)
            tx(f'{D["crossings_total"]} crossings x 2 matching pockets = {NPOCK["J3"]} pockets',15,95,4.2)
            sx=85;sy=40
            rr(sx+20,sy,BW,DEPTH,'section_back')
            pp([(sx,sy),(sx+20,sy),(sx+20,sy+DEPTH),(sx+20+BW,sy+DEPTH),
                (sx+20+BW,sy),(sx+50,sy),(sx+50,sy+THK),(sx,sy+THK)],'section_front')
            dimv(MSP,oy+sy,oy+sy+THK,ox+sx+50,ox+sx+60,f'{THK:g}',detail=key)
            dimv(MSP,oy+sy+DEPTH,oy+sy+THK,ox+sx+20+BW,ox+sx+76,f'{DEPTH:g} depth',detail=key)
            tx('ASSEMBLED SECTION - front and back remain flush',15,75,4)
            tx(f'Slots span the entire {BW:g} mm bar width. No closed-side dogbones.',10,18,3.3)
        else:
            tx('S02 receiver / A -> BACK' if key=='J4V' else 'S01 receiver / A -> FRONT',15,148,3.9)
            tx('L01 end / A -> FRONT' if key=='J4V' else 'L02 end / A -> BACK',135,148,3.9)
            # The seat is BW wide along the rail and LAP deep into it; those are
            # two different parameters even though the default design shares 10.
            seat=107+SM-LAP
            rr(15,107,80,SM);rr(135,117,70,BW)
            rr(45,seat,BW,LAP,'pocket');rr(135,117,LAP,BW,'pocket')
            for cx in (45,45+BW):
                circle_poly(MSP,ox+cx,oy+seat,R,'JOINT_DETAILS_REF',
                            role='dogbone',**common,radius_mm=R)
            dimh(MSP,ox+45,ox+45+BW,oy+seat,oy+116,f'{BW:g}',detail=key)
            dimv(MSP,oy+seat,oy+107+SM,ox+95,ox+105,f'{LAP:g} lap',detail=key)
            dimh(MSP,ox+135,ox+135+LAP,oy+117,oy+105,f'{LAP:g}',detail=key)
            tx(f'2 x R{R:g} at closed corners; union with nominal pocket',15,82,3.7)
            # Sectioned along the insertion direction, so the stepped overlap runs
            # for LAP, not for the bar width. Depth stays a Z quantity.
            sx=83;sy=35
            pp([(sx,sy),(sx+20,sy),(sx+20,sy+DEPTH),(sx+20+LAP,sy+DEPTH),
                (sx+20+LAP,sy+THK),(sx,sy+THK)],'section_front')
            pp([(sx+20,sy),(sx+55,sy),(sx+55,sy+THK),(sx+20+LAP,sy+THK),
                (sx+20+LAP,sy+DEPTH),(sx+20,sy+DEPTH)],'section_back')
            dimv(MSP,oy+sy,oy+sy+THK,ox+sx+55,ox+sx+65,f'{THK:g}',detail=key)
            dimv(MSP,oy+sy+DEPTH,oy+sy+THK,ox+sx+20+LAP,ox+sx+81,f'{DEPTH:g} depth',detail=key)
            dimh(MSP,ox+sx+20,ox+sx+20+LAP,oy+sy,oy+sy-12,f'{LAP:g} lap',detail=key)
            tx(f'ASSEMBLED SECTION / {LAP:g} mm seat depth, {DEPTH:g} mm in Z',15,67,4)
            tx(f'{kinds[0]} + {kinds[1]}: {2*NLEAF*(NV if key=="J4V" else NH)} end joints in this design.',10,18,3.4)
        tx('REFERENCE ONLY / DXF 1:1 / PNG enlarged',10,7,3.2)
    return positions


def render_details(doc,positions):
    rows=math.ceil(len(positions)/2);height=280+rows*1680+220
    im=Image.new('RGB',(4400,height),COL['white']);d=ImageDraw.Draw(im)
    label(d,(120,65),'02  JOINERY DETAILS',65,bold=True)
    label(d,(120,153),f'Closed pocket geometry  |  All wood {THK:g} mm thick  |  Pocket depth {DEPTH:g} mm  |  Exact R{R:g} relief arcs',31,fill=COL['muted'])
    d.line((120,220,4280,220),fill=COL['border'],width=3)
    viewports={key:(100+(i%2)*2160,280+(i//2)*1680,2040,1615) for i,key in enumerate(positions)}
    for j,(ox,oy) in positions.items():
        vp=viewports[j];r=Renderer(im,(ox,oy,ox+240,oy+190),vp)
        ents=[e for e in doc.modelspace() if meta(e).get('detail')==j]
        # All geometry is read from the reference detail regions in the final DXF.
        r.entities(ents)
    y=height-190
    legend=[(COL['pocket'],f'{DEPTH:g} mm pocket'),(COL['dog'],f'R{R:g} relief'),
            (COL['front'],'retained front half'),(COL['back'],'retained back half')]
    x=160
    for c,s in legend:
        d.rectangle((x,y,x+43,y+43),fill=c,outline=COL['line'],width=2)
        label(d,(x+65,y+3),s,29);x+=1015
    label(d,(120,height-85),'Detail geometry stays 1:1 in DXF Model Space. Only this PNG view is enlarged. Dimensions are millimetres.',27,fill=COL['muted'])
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
    label(d,(120,65),f'01  ONE-BOARD NESTING / {TITLE}',61,bold=True)
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
    for s in [face_note(),
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
    label(d,(105,62),f'03  ASSEMBLY / {TITLE}',54,bold=True)
    label(d,(105,151),f'{W:g} x {H:g} mm frame | {NLEAF} leaf, each {LW:g} x {LH:g} mm | Lattice {NV} vertical + {NH} horizontal',27,fill=COL['muted'])
    d.line((105,225,3495,225),fill=COL['border'],width=3)
    ox,oy=ASSEMBLY_ORIGIN
    r=Renderer(im,(ox-78,oy-92,ox+W+75,oy+H+80),(70,290,2590,2980))
    ents=[e for e in doc.modelspace() if meta(e).get('view')=='assembly' and meta(e).get('kind')!='title']
    for role in ('picture','body','other'):
        r.entities([e for e in ents if (meta(e).get('role')==role if role!='other' else meta(e).get('role') not in ('picture','body'))])
    x,y,w=2760,360,700
    basis='Outer frame' if SIZE['basis']=='outer' else 'Fixed-frame inner opening'
    schedule=[('WINDOW',TITLE),
              ('SIZE BASIS',f'{basis} {SIZE["requested_mm"][0]:g} x {SIZE["requested_mm"][1]:g} mm. Outer {W:g} x {H:g}, inner {IW:g} x {IH:g}.'),
              ('EACH OPENING',f'{OW:g} x {OH:g} mm before lattice subdivision.'),
              ('LATTICE',f'{NV} vertical + {NH} horizontal per leaf; {NV*NH} crossings.'),
              ('CLEARANCES',f'Frame to leaf: {GAP_OUT:g} mm.'+(f' Between leaves: {GAP_MID:g} mm.' if NLEAF==2 else '')),
              ('REAR PICTURE',f'{A3W:g} x {A3H:g} mm, centred, minimum margin {PMG:g} mm.' if PICTURE else 'No picture specified.'),
              ('HARDWARE REFERENCES',f'{2*NLEAF} hinges, {NLEAF} handles, {NLEAF} catches. Hinge sides: '+', '.join(f.side for f in FORMAT)+'.'),
              ('JOINT DETAILS',', '.join(formats.detail_variants(PARAMS)))]
    for ttl,body in schedule:
        label(d,(x,y),ttl,27,bold=True);y+=48
        y=wrapped(d,body,(x,y),w,28);y+=40
    d.rounded_rectangle((110,3410,3490,3800),radius=18,fill=COL['panel'],outline=COL['border'],width=2)
    label(d,(160,3460),'ASSEMBLY AND FABRICATION STATUS',34,bold=True)
    notes=[face_note(),
           'Hardware shapes and opening axes are position references. Products and load capacity remain PENDING.',
           'Material minima, fit coupons, backing and CAM setup remain PENDING.']
    if PICTURE:notes.append('The picture is fixed to a separate rear support, never to moving leaves.')
    y=3530
    for note in notes:y=wrapped(d,note,(160,y),3270,28)+20
    label(d,(110,3850),'Reference members are transformed from the saved and verified CNC part geometry.',27,fill=COL['muted'])
    im.save(OUT/'03_assembly_reference.png',dpi=(220,220))


def render_opening(doc):
    im=Image.new('RGB',(4000,2750),COL['white']);d=ImageDraw.Draw(im)
    label(d,(110,60),f'04  OPENING / {TITLE}',55,bold=True)
    label(d,(110,152),f'Looking down | {NLEAF} moving leaf | Opening toward the viewer | Reference axes',28,fill=COL['muted'])
    d.line((110,225,3890,225),fill=COL['border'],width=3)
    ox,oy=OPENING_ORIGIN
    Renderer(im,(ox-50,oy-100,ox+W+50,oy+max(360,LW+THK+110)),(110,285,2720,2190)).entities(
        [e for e in doc.modelspace() if meta(e).get('view')=='opening'])
    y=365
    for ttl,body in [('ILLUSTRATION ONLY','The plan shows a nominal 90-degree rotation about provisional front-projecting axes.'),
                     ('HINGE SIDES',', '.join(f.side.upper() for f in FORMAT)+'; two hinges per leaf.'),
                     ('REAR PICTURE',f'One fixed {A3W:g} x {A3H:g} mm picture on a separate backing.' if PICTURE else 'No picture or rear picture plane is specified.'),
                     ('PENDING','Select actual hinges, screws, catches and backing. Check full movement, loads and clearances before manufacture.')]:
        label(d,(2970,y),ttl,29,bold=True);y+=57
        y=wrapped(d,body,(2970,y),875,29)+66
    label(d,(115,2580),'REFERENCE ONLY / Dynamic interference and real hardware are not validated by this illustration.',29,bold=True)
    label(d,(115,2650),'No opening diagram is a CNC pocket or a toolpath.',27,fill=COL['muted'])
    im.save(OUT/'04_opening_reference.png',dpi=(220,220))


def write_readme(report):
    ma=report['manufacturing_assessment']
    lines=[f"한옥 창호 CAD 패키지 / {PARAMS['revision']}",f'형식: {TITLE}',
           f'외곽: {W:g} x {H:g} mm. 창짝 {NLEAF}개, 각각 {LW:g} x {LH:g} mm.',
           f"크기 기준: {'외경(완성 외곽)' if SIZE['basis']=='outer' else '내경(고정틀 안목)'} {SIZE['requested_mm'][0]:g} x {SIZE['requested_mm'][1]:g} mm 입력. 외경 {W:g} x {H:g}, 내경 {IW:g} x {IH:g} mm.",
           f'창짝당 창살: 세로 {NV}, 가로 {NH}. 교차점 {NV*NH}개.',
           f'부품 {NPART}, 홈 {NPOCKT}, 도그본 {NDOG}, 결합쌍 {NPOCKT//2}.',
           f'원판: {BL:g} x {BWD:g} x {THK:g} mm. 부재 길이는 목리 X 방향.',
           f'가공 깊이: {DEPTH:g} mm. 모든 가공은 A면. 공구 지름 {PARAMS["machining"]["tool_diameter"]:g}, 도그본 R{R:g}.',
           f'창짝-고정틀 간극 {GAP_OUT:g} mm.'+(f' 창짝 사이 간극 {GAP_MID:g} mm.' if NLEAF==2 else ''),
           f'그림: {A3W:g} x {A3H:g} mm, 후면 기준영역 안에 중앙 배치, 각 변 최소 여유 {PMG:g} mm.' if PICTURE else '그림: 지정하지 않음.',
           '실제 존재하는 결합 상세: '+', '.join(formats.detail_variants(PARAMS)),
           f'경첩 {2*NLEAF}, 손잡이 {NLEAF}, 캐치 {NLEAF}: 실물 선정 전 참고 위치.',
           '경첩 부재: '+', '.join(f'{f.hinge_stile}/{f.fixed_stile}' for f in FORMAT),
           '손잡이 부재: '+', '.join(f.handle_stile for f in FORMAT),
           '',f"저장 DXF 재검증: {report['checks_passed']}개 검사 PASS. 검사 ID·기대값·실측값·허용 오차는 validation_report.json.",
           f"실측 최소 홈 사이 폭: {ma['machined_web']['measured_mm']}; 가장자리 폭: {ma['edge_web']['measured_mm']}; 잔존 두께: {ma['remaining_thickness']['measured_mm']} mm.",
           '제작용 최소값은 미확정(null/PENDING). 명목 기하 합격은 제작 승인이나 강도 보증이 아닙니다.',
           '부재는 명목 무공차입니다. 시험편·끼움 공차·재료·하드웨어·후판 고정·개폐 간섭·CAM·고정 지그를 확인해야 합니다.',
           'CUT_THROUGH는 전체 두께. POCKET과 DOGBONE은 부모 홈과 합쳐 절삭합니다. 개방 경계는 폐기물 방향 오버런이 필요합니다.',
           'HINGE_REF와 LATCH_REF는 생산 가공에서 제외합니다. 공구 경로·탭·이송·회전수·G-code는 포함하지 않습니다.',
           '', '파일: window.dxf, PNG 5장, CSV 4종, design_request.json, design_parameters.json, design_spec.json,',
           'resolved_parameters.json, validation_report.json, environment.json, package_manifest.json, source/.',
           '재생성: source/requirements.txt를 설치하고 PYTHONPATH=source python -m hanok_generator build --input design_request.json --output rebuilt',
           '검증: PYTHONPATH=source python -m hanok_generator verify .',
           'DXF는 고정 해시 시드와 메타데이터를 사용합니다. PNG 재현에는 environment.json의 폰트와 라이브러리도 같아야 합니다.',
           '파일을 수정한 뒤 기존 매니페스트를 덮어쓰지 마십시오. 새 입력으로 새 패키지를 생성하십시오.']
    (OUT/'README.txt').write_bytes(('\n'.join(lines)+'\n').encode('utf-8'))
