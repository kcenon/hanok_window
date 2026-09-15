"""Create and re-read-validate one nominal design in a dedicated worker process."""
from __future__ import annotations
import argparse, csv, hashlib, itertools, json, math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
import ezdxf
from shapely.geometry import Polygon, Point, LineString, box
from shapely.affinity import affine_transform, translate, rotate
from shapely.ops import unary_union
from PIL import Image, ImageDraw
from .cad_helpers import *
from .numeric_policy import (POLICY_VERSION, LENGTH_TOL_MM, RATIO_TOL, AREA_TOL_MM2,
                            VOLUME_TOL_MM3, ARC_CHORD_TOL_MM, close, coordinates_match,
                            geometry_matches, polyline_arcs, policy_record)
from .machining_checks import measure_machining
from .. import formats
from .generate_spec import (build as build_spec, build_parts, derive, bar_offsets, leaf_bounds,
                           opening_bounds, group_name)

# Reproducible output. Without this, ezdxf stamps the save time into $TDCREATE
# and $TDUPDATE, issues fresh $VERSIONGUID and $FINGERPRINTGUID values, and dates
# its own written-by marker, so two builds of identical geometry hash
# differently and package_manifest.json cannot tell a rebuild from an edit. The
# option only substitutes constants for those provenance fields; no geometry,
# layer or metadata content is affected. The revision travels in document
# metadata and on the sheet instead - see pin_build_identity.
ezdxf.options.write_fixed_meta_data_for_testing=True

# The same for every design: the length tolerance, how far right of the board the
# reference views start, and the Y origins of the assembly and opening views.
# 1220 + 130 = 1350 keeps the drawings of a 1220 mm board where they always were.
TOL=LENGTH_TOL_MM
REFERENCE_GAP_X=130.
ASSEMBLY_Y=100.
OPENING_Y=-370.
REFERENCE_VIEWS=('assembly','detail','opening')


@dataclass(frozen=True)
class Design:
    """One job's derived design. configure() makes it; every step below reads it as cfg.

    The fields keep the short names that the drawing and check code has always used.
    """
    OUT: Path; DXF: Path; SPEC: Path; PARAMS: dict; D: dict
    W: float; H: float; IW: float; IH: float; SIZE: dict
    FW: float; SM: float; BW: float; LAP: float; LW: float; LH: float; MINR: float
    LY0: float; LY1: float; OW: float; OH: float; PX: float; PY: float; PRW: float; PRH: float
    A3W: float; A3H: float; PMG: float; DEPTH: float; THK: float; R: float
    NLEAF: int; NV: int; NH: int; GAP_OUT: float; GAP_MID: float
    BL: float; BWD: float; BT: float; MARGIN: float; PGAP: float
    LEAVES: list; OPENINGS: list; SIZES: dict; NPART: int
    NPOCK: dict; NPOCKT: int; NSEAT: int; NDOG: int; POCKET_LAYER: str; LAYERS: dict
    FORMAT: list; TITLE: str; PICTURE: bool; PICX: float; PICY: float
    ASSEMBLY_ORIGIN: tuple; OPENING_ORIGIN: tuple; PART_Z: dict


def configure(parameters, output):
    """Return one job's derived design. Nothing is read on import or written here."""
    OUT=Path(output)
    DXF=OUT/'window.dxf'
    SPEC=OUT/'design_spec.json'
    PARAMS=parameters
    D=derive(PARAMS)
    
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
    # The reference views start right of the board, so a longer board moves them.
    ASSEMBLY_ORIGIN=(BL+REFERENCE_GAP_X,ASSEMBLY_Y)
    OPENING_ORIGIN=(BL+REFERENCE_GAP_X,OPENING_Y)
    # Each member's assembly Z, the back face of its layer, for the joint and solid checks.
    PART_Z={q.part_id:q.assembly_z for q in build_parts(D)}
    return Design(OUT=OUT,DXF=DXF,SPEC=SPEC,PARAMS=PARAMS,D=D,W=W,H=H,IW=IW,IH=IH,SIZE=SIZE,
                  FW=FW,SM=SM,BW=BW,LAP=LAP,LW=LW,LH=LH,MINR=MINR,
                  LY0=LY0,LY1=LY1,OW=OW,OH=OH,PX=PX,PY=PY,PRW=PRW,PRH=PRH,
                  A3W=A3W,A3H=A3H,PMG=PMG,DEPTH=DEPTH,THK=THK,R=R,
                  NLEAF=NLEAF,NV=NV,NH=NH,GAP_OUT=GAP_OUT,GAP_MID=GAP_MID,
                  BL=BL,BWD=BWD,BT=BT,MARGIN=MARGIN,PGAP=PGAP,
                  LEAVES=LEAVES,OPENINGS=OPENINGS,SIZES=SIZES,NPART=NPART,
                  NPOCK=NPOCK,NPOCKT=NPOCKT,NSEAT=NSEAT,NDOG=NDOG,POCKET_LAYER=POCKET_LAYER,LAYERS=LAYERS,
                  FORMAT=FORMAT,TITLE=TITLE,PICTURE=PICTURE,PICX=PICX,PICY=PICY,
                  ASSEMBLY_ORIGIN=ASSEMBLY_ORIGIN,OPENING_ORIGIN=OPENING_ORIGIN,PART_Z=PART_Z)


def load_spec(cfg):
    """Regenerate from the parameters so design_spec.json and the DXF cannot drift.

    Nothing is written here; build() replaces design_spec.json together with the
    DXF only after both validation phases pass.
    """
    s=build_spec(cfg.PARAMS)
    return s,{p['part_id']:p for p in s['parts']}


def local_to_assembly(p,g):
    return affine_transform(g,p['assembly_transform'])


def inverse_map(m):
    a,b,c,d,tx,ty=m
    det=a*d-b*c
    if abs(det)<1e-12: raise ValueError('Singular assembly transform')
    return [d/det,-b/det,-c/det,a/det,(b*ty-d*tx)/det,(c*tx-a*ty)/det]


def add_part_geometry(cfg,m,s,p):
    pid=p['part_id'];x=p['nest_x'];y=p['nest_y'];L=p['length'];B=p['width']
    dat=dict(kind='part',part_id=pid,family=p['kind'],length_mm=L,width_mm=B,
             thickness_mm=cfg.THK,depth_mm=cfg.THK,nesting_origin=[x,y],
             assembly_map=p['assembly_transform'],assembly_face_A=p['face_a'],
             assembly_group=p['assembly_group'],machining_face='A')
    rect(m,x,y,L,B,'CUT_THROUGH',**dat)
    # IDs are annotations, not engraving operations. For wide members the text
    # occupies the untouched lower band; lattice labels sit between slots.
    text(m,pid,(x+(L*.4 if p['kind']=='S01' else L/2),y+(B/2 if B==cfg.BW else B*.31)),3.4 if B==cfg.BW else 4.5,
         'PART_ID','center',kind='part_id',part_id=pid,view='nest')
    for q in s['pockets']:
        if q['part_id']!=pid: continue
        u0,v0,u1,v1=q['u0'],q['v0'],q['u1'],q['v1']
        edges=[]
        if abs(u0)<TOL: edges.append('U_MIN')
        if abs(u1-L)<TOL: edges.append('U_MAX')
        if abs(v0)<TOL: edges.append('V_MIN')
        if abs(v1-B)<TOL: edges.append('V_MAX')
        rect(m,x+u0,y+v0,u1-u0,v1-v0,cfg.POCKET_LAYER,
             kind='pocket',part_id=pid,feature_id=q['feature_id'],joint=q['joint'],
             joint_id=q['joint_pair_id'],mate_part_id=q['mate_part_id'],
             mate_feature_id=q['mate_feature_id'],seat=q['seat'],depth_mm=cfg.DEPTH,
             local_rect=[u0,v0,u1-u0,v1-v0],open_edges=edges,machining_face='A')
    for d in s['dogbones']:
        if d['part_id']!=pid:continue
        circle_poly(m,x+d['center_u'],y+d['center_v'],d['radius'],'DOGBONE',
                    kind='dogbone',part_id=pid,feature_id=d['feature_id'],
                    parent_pocket=d['parent_pocket'],depth_mm=cfg.DEPTH,radius_mm=d['radius'],
                    local_center=[d['center_u'],d['center_v']],
                    operation='UNION_WITH_PARENT_POCKET',machining_face='A')


def face_note(cfg):
    front=' / '.join(k for k,(_,_,count) in cfg.SIZES.items() if count and k in ('F01','S01','L01'))
    back=' / '.join(k for k,(_,_,count) in cfg.SIZES.items() if count and k in ('F02','S02','L02'))
    return f'{front}: A -> FRONT. {back}: flip A -> BACK.'


def add_board(cfg,m,spec):
    tot=spec['derived']['totals']
    rect(m,0,0,cfg.BL,cfg.BWD,'BOARD_BOUNDARY',kind='board',view='nest',size_mm=[cfg.BL,cfg.BWD,cfg.BT])
    text(m,f'HANOK WINDOW / {cfg.TITLE}',(0,cfg.BWD+55),13,kind='title',view='nest')
    # The saved header carries constant timestamps so builds stay reproducible;
    # this line is where a reader finds which revision the sheet actually is.
    text(m,f"REVISION {cfg.PARAMS['revision']} / {cfg.PARAMS['build_date']} / GENERATED FROM design_parameters.json",
         (cfg.BL,cfg.BWD+55),6,align='right',kind='revision',view='nest')
    text(m,f"{cfg.W:g} W x {cfg.H:g} H / {tot['parts']} PARTS / {tot['pockets']} POCKETS / "
           f"{tot['reliefs']} RELIEFS / mm / MODEL SPACE 1:1",(0,cfg.BWD+30),5.5,view='nest')
    dimh(m,0,cfg.BL,cfg.BWD,cfg.BWD+14,f'{cfg.BL:g}',view='nest')
    dimv(m,0,cfg.BWD,0,-27,f'{cfg.BWD:g}',view='nest')
    # Notes, the grain arrow and the offcut line sit below the board, so however full
    # the layout is, the board holds only parts, pockets, reliefs, part labels and
    # hardware marks. The nesting PNG leaves them out (kind sheet_note); its side
    # panel carries the same notes.
    notes=[f'ONE BOARD {cfg.BL:g} x {cfg.BWD:g} x {cfg.BT:g} / ALL POCKETS MACHINED FROM COMMON FACE A',
           face_note(cfg),
           f'{cfg.POCKET_LAYER} + DOGBONE: UNION, REMOVE {cfg.DEPTH:g} mm. OPEN LAPS NEED WASTE-SIDE OVERRUN.',
           'HINGE_REF / LATCH_REF ARE POSITION REFERENCES ONLY. DO NOT MACHINE.',
           'NOMINAL FIT: VERIFY STOCK, TEST COUPONS, WORKHOLDING AND CAM BEFORE CUTTING.',
           'BOARD AREA WITHOUT PARTS: UNUSED OFFCUT / NOT ADDITIONAL PARTS']
    for i,s in enumerate(notes):text(m,s,(0,-60-i*20),6.6,view='nest',kind='sheet_note')
    gy=-235
    line(m,(cfg.BL*.115,gy),(cfg.BL*.885,gy),'GRAIN_DIRECTION',view='nest',kind='sheet_note')
    for sg in (1,-1):
        line(m,(cfg.BL*.885,gy),(cfg.BL*.885-44,gy+sg*21),'GRAIN_DIRECTION',view='nest',kind='sheet_note')
    text(m,'GRAIN DIRECTION  +X',(cfg.BL/2,gy+40),19,'GRAIN_DIRECTION','center',view='nest',kind='sheet_note')
    text(m,f'All {tot["parts"]} part lengths run parallel to the {cfg.BL:g} mm grain direction.',
         (cfg.BL/2,gy-40),8,align='center',view='nest',kind='sheet_note')
    text(m,'No G-code, tabs, toolpaths, feeds or speeds are included. All hardware and backing remain PENDING.',
         (0,-35),5.3,view='nest')


def hinge_axes(cfg):
    """Provisional vertical swing axes, midway between frame and leaf edges."""
    return [(cfg.FW+cfg.LEAVES[f.index][0])/2 if f.side=='left'
            else (cfg.LEAVES[f.index][2]+cfg.W-cfg.FW)/2 for f in cfg.FORMAT]


def hinge_heights(cfg):
    inset=cfg.PARAMS['hardware_reference']['hinge_inset_from_leaf_end']
    return [cfg.LY0+inset,cfg.LY1-inset]


def meeting_stile_centres(cfg):
    """Centre line of each leaf's handle-side stile, away from its hinges."""
    return [cfg.LEAVES[f.index][2]-cfg.SM/2 if f.side=='left' else cfg.LEAVES[f.index][0]+cfg.SM/2 for f in cfg.FORMAT]


def hardware_records(cfg):
    hw=cfg.PARAMS['hardware_reference'];out=[]
    ww,wi,hl=hw['wing_width'],hw['wing_inset'],hw['hinge_length']
    for form in cfg.FORMAT:
        side,pf,ps=form.side.upper(),form.fixed_stile,form.hinge_stile
        xf=cfg.FW-wi-ww if form.side=='left' else cfg.W-cfg.FW+wi
        xs=cfg.LEAVES[form.index][0]+wi if form.side=='left' else cfg.LEAVES[form.index][2]-wi-ww
        for idx,y in enumerate(hinge_heights(cfg),1):
            hid=f'H-{side}-{idx}'
            for pid,x,wing in [(pf,xf,'FIXED'),(ps,xs,'SASH')]:
                out.append(dict(hardware_id=hid,part_id=pid,layer='HINGE_REF',
                                box=[x,y-hl/2,x+ww,y+hl/2],hardware_type='HINGE',wing=wing,
                                depth_ref_mm=hw['hinge_depth_ref']))
    hx=meeting_stile_centres(cfg);hwd,hht=hw['handle_width'],hw['handle_height']
    cy=(cfg.LY0+cfg.LY1)/2
    for i,(x,form) in enumerate(zip(hx,cfg.FORMAT),1):
        pid=form.handle_stile
        out.append(dict(hardware_id=f'HANDLE-{i}',part_id=pid,layer='LATCH_REF',
                        box=[x-hwd/2,cy-hht/2,x+hwd/2,cy+hht/2],hardware_type='HANDLE'))
    cs=hw['catch_size'];sy=cfg.LY1-hw['catch_inset_from_leaf_top']
    fy=cfg.H-cfg.FW+hw['catch_inset_from_frame_inner_top']
    for i,(x,form) in enumerate(zip(hx,cfg.FORMAT),1):
        if cfg.NLEAF==1:
            # Provisional catch above the handle on its opposite-hinge stile.
            fx=cfg.W-cfg.FW/2 if form.side=='left' else cfg.FW/2
            placements=[(form.handle_stile,x,cy+hht+cs),
                        ('F01-2' if form.side=='left' else 'F01-1',fx,cy+hht+cs)]
        else:
            placements=[(form.top_rail,x,sy),('F02-2',x,fy)]
        for pid,cx,cc in placements:
            out.append(dict(hardware_id=f'CATCH-{i}',part_id=pid,layer='LATCH_REF',
                            box=[cx-cs/2,cc-cs/2,cx+cs/2,cc+cs/2],hardware_type='CATCH'))
    return out


def add_hardware(cfg,m,parts):
    ox,oy=cfg.ASSEMBLY_ORIGIN
    for d in hardware_records(cfg):
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
    for x in hinge_axes(cfg):
        for y in hinge_heights(cfg):
            line(m,(ox+x,oy+y-cfg.THK-4),(ox+x,oy+y+cfg.THK+4),'HINGE_REF',view='assembly',
                 kind='hinge_location_ref',reference_only=True)


def add_assembly(cfg,m,parts):
    ox,oy=cfg.ASSEMBLY_ORIGIN
    text(m,f'{cfg.TITLE} / W{cfg.W:g} x H{cfg.H:g}',(ox,oy+cfg.H+84),10,view='assembly',kind='title')
    text(m,f'{cfg.NLEAF} LEAF / REFERENCE ONLY',(ox,oy+cfg.H+61),5,view='assembly')
    if cfg.PICTURE:
        rect(m,ox+cfg.PICX,oy+cfg.PICY,cfg.A3W,cfg.A3H,'ASSEMBLY_REFERENCE',view='assembly',role='picture',
             nominal_size=[cfg.A3W,cfg.A3H],dxf_role='rear_picture')
    # This reflects the same parts and transformations as the machining layout.
    for p in sorted(parts.values(),key=lambda p:(p['face_a']=='BACK',p['part_id'])):
        g=translate(local_to_assembly(p,box(0,0,p['length'],p['width'])),ox,oy)
        poly(m,list(g.exterior.coords)[:-1],'ASSEMBLY_REFERENCE',view='assembly',role='body',
             part_id=p['part_id'],assembly_group=p['assembly_group'])
    if cfg.PICTURE:
        rect(m,ox+cfg.PX,oy+cfg.PY,cfg.PRW,cfg.PRH,'ASSEMBLY_REFERENCE',view='assembly',role='picture_region',nominal_size=[cfg.PRW,cfg.PRH])
    for x0,y0,x1,y1 in cfg.OPENINGS:
        rect(m,ox+x0,oy+y0,x1-x0,y1-y0,'ASSEMBLY_REFERENCE',view='assembly',role='opening',nominal_size=[cfg.OW,cfg.OH])
    # Outer (외경) and fixed-frame inner (내경) are both dimensioned; the basis the
    # size was requested in carries an INPUT mark.
    mark={b:(' (INPUT)' if cfg.SIZE['basis']==b else '') for b in ('outer','inner')}
    dimh(m,ox,ox+cfg.W,oy+cfg.H,oy+cfg.H+27,f'{cfg.W:g} OVERALL'+mark['outer'],view='assembly')
    dimv(m,oy,oy+cfg.H,ox+cfg.W,ox+cfg.W+36,f'{cfg.H:g} OVERALL'+mark['outer'],view='assembly')
    dimh(m,ox+cfg.FW,ox+cfg.W-cfg.FW,oy+cfg.FW,oy-72,f'{cfg.IW:g} FRAME INNER'+mark['inner'],view='assembly')
    dimv(m,oy+cfg.FW,oy+cfg.H-cfg.FW,ox+cfg.FW,ox-58,f'{cfg.IH:g} FRAME INNER'+mark['inner'],view='assembly')
    names=['LEFT','RIGHT'] if cfg.NLEAF==2 else ['SINGLE']
    for (x0,y0,x1,y1),nm in zip(cfg.LEAVES,names):
        dimh(m,ox+x0,ox+x1,oy+y0,oy-18,f'{cfg.LW:g} {nm} LEAF',view='assembly')
    dimv(m,oy+cfg.LY0,oy+cfg.LY1,ox,ox-29,f'{cfg.LH:g} LEAF',view='assembly')
    for x0,y0,x1,y1 in cfg.OPENINGS:
        dimh(m,ox+x0,ox+x1,oy+y1,oy+y1+51,f'{cfg.OW:g} OPENING',view='assembly')
    dimv(m,oy+cfg.PY,oy+cfg.PY+cfg.OH,ox+cfg.OPENINGS[-1][2],ox+cfg.OPENINGS[-1][2]+52,f'{cfg.OH:g} OPENING',view='assembly')
    if cfg.PICTURE:
        text(m,f'PICTURE {cfg.A3W:g} x {cfg.A3H:g}',(ox+cfg.W/2,oy+cfg.PY+24),6,'ASSEMBLY_REFERENCE','center',view='assembly',role='picture_label')
    for (x0,y0,x1,y1),nm in zip(cfg.LEAVES,names):
        text(m,f'{nm} / {cfg.LW:g} x {cfg.LH:g}',(ox+(x0+x1)/2,oy+cfg.LY1-17),4,'ASSEMBLY_REFERENCE','center',view='assembly')
    # Member labels are placed from the assembled geometry, not from fixed offsets.
    for p in parts.values():
        g=local_to_assembly(p,box(0,0,p['length'],p['width']))
        cx=(g.bounds[0]+g.bounds[2])/2;cy=(g.bounds[1]+g.bounds[3])/2
        if p['kind'] in ('F01','S01'):
            text(m,p['part_id'],(ox+cx,oy+cfg.H*.58),3.6,'ASSEMBLY_REFERENCE','center',90,view='assembly')
        elif p['kind']=='F02' or (p['kind']=='S02' and int(p['part_id'].split('-')[1])%2):
            text(m,p['part_id'],(ox+cx,oy+cy),3.5,'ASSEMBLY_REFERENCE','center',view='assembly')
    gaptext=f'{cfg.GAP_MID:g} mm centre gap / ' if cfg.NLEAF==2 else ''
    text(m,gaptext+f'{cfg.GAP_OUT:g} mm external clearances',(ox+cfg.W/2,oy-39),4.7,align='center',view='assembly')
    if cfg.PICTURE:
        text(m,f'Fixed rear picture region {cfg.PRW:g} x {cfg.PRH:g}; leaf members obscure the closed front.',
             (ox+cfg.W/2,oy-53),3.8,align='center',view='assembly')


def add_opening(cfg,m):
    """Illustrative plan at 90 degrees; provisional axis only, not hardware approval."""
    ox,oy=cfg.OPENING_ORIGIN;arc=min(120,cfg.LW*.65);axz=cfg.THK+4
    heading=max(330,cfg.LW+cfg.THK+80)
    text(m,'OPENING REFERENCE / PLAN (LOOKING DOWN)',(ox,oy+heading),8,view='opening',kind='title')
    text(m,'REFERENCE ONLY / AXES AND BACKING POSITION NOT FINAL',(ox,oy+heading-20),4.7,view='opening')
    for g in [box(0,0,cfg.FW,cfg.THK),box(cfg.W-cfg.FW,0,cfg.W,cfg.THK)]:
        poly(m,list(translate(g,ox,oy).exterior.coords)[:-1],'ASSEMBLY_REFERENCE',view='opening',role='body')
    axes=hinge_axes(cfg)
    for form,ax in zip(cfg.FORMAT,axes):
        name=form.side.upper();lx0,_,lx1,_=cfg.LEAVES[form.index]
        deg=form.angle;sg=1 if form.side=='left' else -1
        axis=(ax,axz)
        closed=box(lx0,0,lx1,cfg.THK)
        poly(m,list(translate(closed,ox,oy).exterior.coords)[:-1],'ASSEMBLY_REFERENCE',
             view='opening',role='opening',kind='closed_leaf_ghost',leaf=name)
        opened=rotate(closed,deg,origin=axis)
        poly(m,list(translate(opened,ox,oy).exterior.coords)[:-1],'ASSEMBLY_REFERENCE',
             view='opening',role='body',kind='opened_leaf_illustration',leaf=name,
             reference_only=True,illustrative_angle_deg=90,provisional_axis=list(axis))
        circle_poly(m,ox+axis[0],oy+axis[1],3,'HINGE_REF',view='opening',reference_only=True)
        text(m,f'{name} LEAF',(ox+ax+sg*cfg.LW*.2,oy+134),5,'ASSEMBLY_REFERENCE','center',90,view='opening')
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
    if cfg.PICTURE:
        rect(m,ox+cfg.PICX,oy-axz,cfg.A3W,4,'ASSEMBLY_REFERENCE',view='opening',role='picture',reference_only=True)
        line(m,(ox+cfg.PX,oy-axz-5),(ox+cfg.PX+cfg.PRW,oy-axz-5),'ASSEMBLY_REFERENCE',view='opening',reference_only=True)
        text(m,'PICTURE FIXED ON SEPARATE REAR SUPPORT',(ox+cfg.W/2,oy-47),4.4,align='center',view='opening')
    if cfg.NLEAF==2:
        text(m,'CENTRE MEMBERS MOVE WITH EACH LEAF',(ox+cfg.W/2,oy+247),5,align='center',view='opening')
    text(m,'NO FIXED CENTRE MULLION',(ox+cfg.W/2,oy+265),6,align='center',view='opening')
    text(m,'VIEWER / FRONT +Z',(ox+cfg.W/2,oy+222),5,align='center',view='opening')
    axes_label=', '.join(f'({ax:g},{axz:g})' for ax in axes)
    text(m,f'Illustrative axes: (X,Z)={axes_label}. Recheck selected hardware.',
         (ox,oy-70),3.8,view='opening')
    text(m,'No actual hinge, screw, backing clearance or load capacity is verified here.',
         (ox,oy-83),3.8,view='opening')


def pin_build_identity(cfg,doc):
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
    md['HANOK_REVISION']=cfg.PARAMS['revision']
    md['HANOK_BUILD_DATE']=cfg.PARAMS['build_date']
    md['HANOK_SOURCE_OF_TRUTH']='design_parameters.json'
    md['HANOK_NUMERIC_POLICY']=POLICY_VERSION


def build(cfg):
    spec,parts=load_spec(cfg)
    doc=ezdxf.new('R2010');doc.units=ezdxf.units.MM
    doc.header['$MEASUREMENT']=1;doc.header['$LUNITS']=2;doc.header['$LUPREC']=3
    doc.header['$INSBASE']=(0,0,0);doc.header['$LWDISPLAY']=True
    pin_build_identity(cfg,doc)
    doc.appids.new(APP)
    for name,(c,lw) in cfg.LAYERS.items():doc.layers.new(name,dxfattribs={'color':c,'lineweight':lw})
    doc.linetypes.new('REF_DASH',dxfattribs={'description':'Reference dash 4-2','pattern':[6,4,-2]})
    doc.linetypes.new('A3_DASHDOT',dxfattribs={'description':'A3 picture dash-dot','pattern':[13,8,-2,1,-2]})
    for name in ['HINGE_REF','LATCH_REF']:doc.layers.get(name).dxf.linetype='REF_DASH'
    msp=doc.modelspace()
    for p in parts.values():add_part_geometry(cfg,msp,spec,p)
    add_board(cfg,msp,spec);add_assembly(cfg,msp,parts);add_hardware(cfg,msp,parts)
    positions=add_details(cfg,msp);add_opening(cfg,msp)
    for e in msp:
        role=meta(e).get('role')
        if role=='picture':e.dxf.linetype='A3_DASHDOT'
        elif role in ('opening','picture_region'):e.dxf.linetype='REF_DASH'
    # Default view opens on the stock, its machining layout and the notes below it, not
    # the reference sheets: from 300 below the board to 85 above it.
    doc.set_modelspace_vport(height=cfg.BWD+385,center=(cfg.BL/2,cfg.BWD/2-107.5))
    # Write candidates beside the outputs and swap them in only after both phases
    # pass, so a rejected build leaves the previous spec and DXF as they were
    # instead of pairing a new spec with an old drawing.
    tmp=cfg.OUT/'_validated_candidate.dxf';tmpspec=cfg.OUT/'_validated_candidate_spec.json'
    tmpspec.write_bytes((json.dumps(spec,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    try:
        pre=validate(cfg,doc,'IN_MEMORY_BEFORE_SAVE',tmpspec)
        with open(tmp,'wt',encoding=doc.output_encoding,errors='dxfreplace',newline='\n') as fp:doc.write(fp)
        checkdoc=ezdxf.readfile(tmp)
        report=validate(cfg,checkdoc,'READ_BACK_FROM_SAVED_DXF',tmpspec)
    except BaseException:
        tmp.unlink(missing_ok=True);tmpspec.unlink(missing_ok=True)
        raise
    tmpspec.replace(cfg.SPEC);tmp.replace(cfg.DXF)
    report.update(file=cfg.DXF.name,sha256=hashlib.sha256(cfg.DXF.read_bytes()).hexdigest(),
                  pre_save_status=pre['status'],ezdxf_version=ezdxf.__version__)
    (cfg.OUT/'validation_report.json').write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    write_manifests(cfg,checkdoc)
    return checkdoc,report,positions


class ValidationError(AssertionError):
    def __init__(self,phase,checks):
        self.report=dict(status='FAIL_NOMINAL_DXF_GEOMETRY',phase=phase,checks=checks,
                         failed_checks=[q['name'] for q in checks if q['status']=='FAIL'])
        super().__init__('DXF validation failed: '+', '.join(self.report['failed_checks']))


def validate(cfg,doc,phase,spec_path=None):
    """Inspect actual DXF geometry against expectations rebuilt from the parameters.

    The generator reaches pocket coordinates by intersecting assembled members
    and mapping the overlap back through each part's affine. The formula check
    below reaches them from the bar spacing instead, so a mistake in either path
    shows up as a disagreement rather than as a shared assumption.
    """
    checks=[];errors=[];ents=list(doc.modelspace())
    check=check_recorder(check_expectations(cfg),checks,errors)
    # The report lists checks in call order, so the sections run in this order
    # and each check stays in its place even where it would fit another section.
    (rawparts,pockets,dogs,partents,count,mach,geom,partgeo,
     pairs,gap,margin)=check_parts_and_board(cfg,check,ents)
    byjoint,by_pair,machining=check_pockets_and_dogbones(cfg,check,rawparts,pockets,dogs,partents,geom,partgeo)
    check_layers_units_and_labels(cfg,check,doc,ents,mach,partents)
    ap,assembled=check_joint_pairs_and_solids(cfg,check,rawparts,pockets,dogs,partents,geom,partgeo,pairs,by_pair)
    check_assembly_dimensions(cfg,check,partents,ap)
    check_references(cfg,check,ents,mach,pockets,count,byjoint,ap,assembled)
    check_metadata(cfg,check,doc,spec_path)
    if errors:raise ValidationError(phase,checks)
    return dict(status='PASS_NOMINAL_DXF_GEOMETRY',phase=phase,saved_dxf_reread=phase=='READ_BACK_FROM_SAVED_DXF',
                revision=cfg.PARAMS['revision'],checks_passed=len(checks),checks=checks,
                numeric_policy=policy_record(),manufacturing_assessment=machining['manufacturing_assessment'],
                parts_total=cfg.NPART,part_counts=dict(count),
                nominal_pockets_total=len(pockets),pocket_counts=dict(byjoint),dogbone_reliefs_total=len(dogs),
                machining_profiles_total=len(mach),mated_joints_total=len(by_pair),
                minimum_part_gap_mm=gap,minimum_board_margin_mm=margin,
                nesting_bounds_mm=list(unary_union(list(partgeo.values())).bounds),
                lattice_per_leaf=dict(vertical=cfg.NV,horizontal=cfg.NH,crossings=cfg.D['crossings_total']//cfg.NLEAF),
                overall_width_height_mm=[cfg.W,cfg.H],leaf_width_height_mm=[cfg.LW,cfg.LH],board_mm=[cfg.BL,cfg.BWD,cfg.BT],
                physical_fabrication_validated=False,visual_inspection_status='PENDING',
                pending=['Actual hinges, screws, load capacity and swing interference',
                         'Rear backing, mounting, picture protection and fastener clearance',
                         'Stock species, grain integrity, thickness, moisture and movement',
                         'Fit coupons and nominal zero-clearance joint tolerances',
                         'CAM pocket union, open-edge overrun and cutter compensation',
                         'Workholding, tabs/onion skin, feeds/speeds and final manufacturing approval'])


def check_expectations(cfg):
    """Expected value of each check that reports a measured value, by check name."""
    return {
        'unique_part_ids_and_total':cfg.NPART, 'board_boundary':dict(count=1,bounds=[0,0,cfg.BL,cfg.BWD]),
        'minimum_nesting_gap':cfg.PGAP, 'minimum_board_edge_margin':cfg.MARGIN,
        'total_base_pockets':cfg.NPOCKT, 'S01_J4_seats_each':cfg.NH,'S02_J4_seats_each':cfg.NV,
        'lattice_bars_per_leaf':[cfg.NV,cfg.NH], 'corner_reliefs':dict(count=cfg.NDOG,radius_mm=cfg.R),
        'half_lap_depth':dict(retained_front=cfg.THK/2,retained_back=cfg.THK/2,stock=cfg.THK),
        'frame_geometry':dict(bounds=[0,0,cfg.W,cfg.H],area_mm2=cfg.W*cfg.H-cfg.D['inner_w']*cfg.D['inner_h']),
        'leaf_envelopes':[[cfg.LW,cfg.LH]]*cfg.NLEAF, 'leaf_height_to_width_ratio':cfg.MINR,
        'leaf_clearances':dict(external=cfg.GAP_OUT,meeting=cfg.GAP_MID if cfg.NLEAF==2 else None),
        'picture_geometry':dict(enabled=cfg.PICTURE,size_mm=[cfg.A3W,cfg.A3H]),
        'picture_margins_match_each_side':dict(minimum_mm=cfg.PMG,centred=True),
        'leaf_opening_references':dict(count=cfg.NLEAF,size_mm=[cfg.OW,cfg.OH]),
        'hardware_counts_and_references':dict(HINGE=2*cfg.NLEAF,HANDLE=cfg.NLEAF,CATCH=cfg.NLEAF),
        'reference_details_match_existing_joints':sorted(formats.detail_variants(cfg.PARAMS)),
        'opening_illustration_matches_leaves':cfg.NLEAF,
        **{f'{joint}_pocket_count':quantity for joint,quantity in cfg.NPOCK.items()},
    }


def check_recorder(expectations,checks,errors):
    """Return the check() that appends one record per call to checks and each failed name to errors."""
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
    return check


def check_parts_and_board(cfg,check,ents):
    """Part identity and counts, closed machining contours and the nesting on the board."""
    rawparts=[e for e in ents if e.dxf.layer=='CUT_THROUGH']
    pockets=[e for e in ents if e.dxf.layer==cfg.POCKET_LAYER]
    dogs=[e for e in ents if e.dxf.layer=='DOGBONE']
    partids=[meta(e).get('part_id') for e in rawparts]
    check('unique_part_ids_and_total',len(partids)==cfg.NPART and len(set(partids))==cfg.NPART,len(partids))
    partents={meta(e)['part_id']:e for e in rawparts}
    count=Counter(meta(e).get('family') for e in rawparts)
    for k,(_,_,n) in cfg.SIZES.items():check(f'{k}_part_count',count[k]==n,{'actual':count[k],'required':n})
    mach=rawparts+pockets+dogs
    check('all_machining_entities_closed_lwpolyline',all(e.dxftype()=='LWPOLYLINE' and e.closed for e in mach),len(mach))
    geom={e.dxf.handle:entity_polygon(e) for e in mach}
    check('valid_positive_area_no_self_intersection',all(g.is_valid and g.area>0 for g in geom.values()))
    keys=[(e.dxf.layer,geom[e.dxf.handle].normalize().wkb) for e in mach]
    check('no_duplicate_complete_machining_contours',len(keys)==len(set(keys)),len(keys)-len(set(keys)))
    partgeo={pid:geom[e.dxf.handle] for pid,e in partents.items()}
    check('all_part_sizes_match_spec',all(
        abs(g.bounds[2]-g.bounds[0]-cfg.SIZES[pid[:3]][0])<TOL and
        abs(g.bounds[3]-g.bounds[1]-cfg.SIZES[pid[:3]][1])<TOL and
        geometry_matches(g,box(g.bounds[0],g.bounds[1],g.bounds[0]+cfg.SIZES[pid[:3]][0],g.bounds[1]+cfg.SIZES[pid[:3]][1]))
        for pid,g in partgeo.items()))
    boardents=[e for e in ents if e.dxf.layer=='BOARD_BOUNDARY']
    check('board_boundary',len(boardents)==1 and geometry_matches(entity_polygon(boardents[0]),box(0,0,cfg.BL,cfg.BWD)),
          dict(count=len(boardents),bounds=list(entity_polygon(boardents[0]).bounds) if boardents else None))
    check('all_parts_within_board',all(box(0,0,cfg.BL,cfg.BWD).buffer(TOL).covers(g) for g in partgeo.values()))
    pairs=list(itertools.combinations(partgeo,2))
    overlap=max(partgeo[a].intersection(partgeo[b]).area for a,b in pairs)
    gap=min(partgeo[a].distance(partgeo[b]) for a,b in pairs)
    margin=min(min(g.bounds[0],g.bounds[1],cfg.BL-g.bounds[2],cfg.BWD-g.bounds[3]) for g in partgeo.values())
    check('no_nesting_overlap',overlap<AREA_TOL_MM2,overlap)
    check('minimum_nesting_gap',gap>=cfg.PGAP-TOL,gap)
    check('minimum_board_edge_margin',margin>=cfg.MARGIN-TOL,margin)
    check('all_lengths_parallel_X_grain',all(g.bounds[2]-g.bounds[0]>g.bounds[3]-g.bounds[1] for g in partgeo.values()))
    return rawparts,pockets,dogs,partents,count,mach,geom,partgeo,pairs,gap,margin


def check_pockets_and_dogbones(cfg,check,rawparts,pockets,dogs,partents,geom,partgeo):
    """Pocket counts and coordinates, dogbone reliefs and the machining they leave."""
    bypart=defaultdict(list);byjoint=Counter();by_pair=defaultdict(list)
    for e in pockets:
        d=meta(e);bypart[d['part_id']].append(e);byjoint[d['joint']]+=1;by_pair[d['joint_id']].append(e)
    for j,n in cfg.NPOCK.items():check(f'{j}_pocket_count',byjoint[j]==n,byjoint[j])
    check('total_base_pockets',len(pockets)==cfg.NPOCKT,len(pockets))
    expected={'F01':2,'F02':2,'S01':2+cfg.NH,'S02':2+cfg.NV,'L01':2+cfg.NH,'L02':2+cfg.NV}
    check('pockets_per_part',all(len(bypart[p])==expected[p[:3]] for p in partents))
    check('S01_J4_seats_each',all(sum(meta(e)['joint']=='J4' and meta(e)['seat'] for e in bypart[p])==cfg.NH for p in partents if p.startswith('S01')),
          {p:sum(meta(e)['joint']=='J4' and meta(e)['seat'] for e in bypart[p]) for p in partents if p.startswith('S01')})
    check('S02_J4_seats_each',all(sum(meta(e)['joint']=='J4' and meta(e)['seat'] for e in bypart[p])==cfg.NV for p in partents if p.startswith('S02')),
          {p:sum(meta(e)['joint']=='J4' and meta(e)['seat'] for e in bypart[p]) for p in partents if p.startswith('S02')})
    check('all_lattice_two_end_laps',all(sum(meta(e)['joint']=='J4' for e in bypart[p])==2 for p in partents if p.startswith('L')))
    check('lattice_crossing_pockets',all(sum(meta(e)['joint']=='J3' for e in bypart[p])==(cfg.NH if p.startswith('L01') else cfg.NV) for p in partents if p.startswith('L')))
    byleaf=Counter((meta(e)['assembly_group'],meta(e)['family']) for e in rawparts)
    check('lattice_bars_per_leaf',all(
        byleaf[(group_name(cfg.D,i),'L01')]==cfg.NV and byleaf[(group_name(cfg.D,i),'L02')]==cfg.NH for i in range(cfg.NLEAF)),
        {group_name(cfg.D,i):[byleaf[(group_name(cfg.D,i),'L01')],byleaf[(group_name(cfg.D,i),'L02')]] for i in range(cfg.NLEAF)})
    # Compare actual local rectangles to the spacing formula, not just counts.
    VX,HY=bar_offsets(cfg.D,'V'),bar_offsets(cfg.D,'H')
    actual_patterns={}
    formula_ok=True
    for pid,pe in partents.items():
        k=pid[:3];L,B,_=cfg.SIZES[k];x,y=meta(pe)['nesting_origin']
        got=sorted(translate(geom[e.dxf.handle],-x,-y).bounds for e in bypart[pid])
        lap=cfg.FW if k[0]=='F' else cfg.SM if k[0]=='S' else cfg.LAP
        want=[(0,0,lap,B),(L-lap,0,L,B)]
        if k[0]=='S':
            # A seat is as wide as the bar it receives and as deep as the bar's
            # insertion, so its v extent is set by end_lap, never by bar width.
            want += [(cfg.SM+c-cfg.BW/2,cfg.SM-cfg.LAP,cfg.SM+c+cfg.BW/2,cfg.SM) for c in (HY if k=='S01' else VX)]
        elif k[0]=='L':
            want += [(cfg.LAP+c-cfg.BW/2,0,cfg.LAP+c+cfg.BW/2,cfg.BW) for c in (HY if k=='L01' else VX)]
        want=sorted(want)
        formula_ok &= len(got)==len(want) and all(coordinates_match(a,b) for a,b in zip(got,want))
        actual_patterns[pid]=got
    check('all_pocket_coordinates_match_exact_formulas',formula_ok)
    seats=[e for e in pockets if meta(e).get('seat')]
    dbpar=defaultdict(list)
    for e in dogs:dbpar[meta(e)['parent_pocket']].append(e)
    dogok=len(dogs)==cfg.NDOG and len(seats)==cfg.NSEAT
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
            dogok &= abs(radius-cfg.R)<TOL and dd['part_id']==d['part_id'] and close(dd['depth_mm'],cfg.DEPTH)
            dogok &= partgeo[pid].buffer(TOL).covers(box(cx-radius,cy-radius,cx+radius,cy+radius))
        dogok &= len(gotcenters)==len(wantcenters) and all(
            coordinates_match(a,b) for a,b in zip(sorted(gotcenters),wantcenters))
    check('corner_reliefs',bool(dogok),dict(count=len(dogs),radii_mm=sorted({arc[2] for e in dogs for arc in polyline_arcs(e)})))
    radii=[];tool_ok=len(dogs)==cfg.NDOG
    for de in dogs:
        arcs=polyline_arcs(de)
        tool_ok &= len(arcs)==2
        radii.extend(a[2] for a in arcs)
    tool_radius=cfg.PARAMS['machining']['tool_diameter']/2
    tool_ok &= all(r>=tool_radius-TOL for r in radii)
    check('machining_relief_radius_at_least_tool_radius',bool(tool_ok),
          dict(tool_radius_mm=tool_radius,minimum_actual_radius_mm=min(radii) if radii else None))
    machining=measure_machining(pockets,dogs,geom,partgeo,cfg.THK)
    check('distinct_machining_regions_separated',machining['separated'],machining['separation'])
    check('machining_preserves_non_open_edges',machining['non_open_edges_preserved'],machining['edges'])
    check('all_pockets_reliefs_inside_own_part',all(partgeo[meta(e)['part_id']].buffer(TOL).covers(geom[e.dxf.handle]) for e in pockets+dogs))
    check('layer_depth_and_face_separation',all(close(meta(e).get('depth_mm',-1),cfg.THK) for e in rawparts) and all(close(meta(e).get('depth_mm',-1),cfg.DEPTH) and meta(e).get('machining_face')=='A' for e in pockets+dogs))
    return byjoint,by_pair,machining


def check_layers_units_and_labels(cfg,check,doc,ents,mach,partents):
    """Required layers, flat millimetre model space and one label per part."""
    check('all_required_layers_exist',all(name in doc.layers for name in cfg.LAYERS))
    check('mm_modelspace_flat_geometry',doc.units==4 and len(doc.paperspace())==0 and all(e.dxf.elevation==0 for e in mach))
    check('part_annotations_separate_and_unique',Counter(meta(e).get('part_id') for e in ents if e.dxf.layer=='PART_ID')==Counter({p:1 for p in partents}))


def check_joint_pairs_and_solids(cfg,check,rawparts,pockets,dogs,partents,geom,partgeo,pairs,by_pair):
    """Joint pairs on opposite faces and assembled solids that must not interpenetrate."""
    def assembled(pid,g):
        d=meta(partents[pid]);x,y=d['nesting_origin']
        return affine_transform(translate(g,-x,-y),d['assembly_map'])
    ap={p:assembled(p,g) for p,g in partgeo.items()}
    check('assembly_transform_faces_consistent',all(
        ((d['assembly_map'][0]*d['assembly_map'][3]-d['assembly_map'][1]*d['assembly_map'][2])>0)==(d['assembly_face_A']=='FRONT')
        for d in map(meta,rawparts)))
    npair=cfg.NPOCKT//2
    pairgood=len(by_pair)==npair;maxmismatch=0.;mateok=True
    for jid,gg in by_pair.items():
        if len(gg)!=2:pairgood=False;continue
        a,b=gg;da,db=meta(a),meta(b)
        ga=assembled(da['part_id'],geom[a.dxf.handle]);gb=assembled(db['part_id'],geom[b.dxf.handle])
        mismatch=ga.symmetric_difference(gb).area;maxmismatch=max(mismatch,maxmismatch)
        pairgood &= geometry_matches(ga,gb) and da['joint']==db['joint']
        pairgood &= {meta(partents[d['part_id']])['assembly_face_A'] for d in [da,db]}=={'FRONT','BACK'}
        # The two halves of a lap interlock only when both members lie on one layer.
        pairgood &= cfg.PART_Z.get(da['part_id'],0.)==cfg.PART_Z.get(db['part_id'],0.)
        pairgood &= geometry_matches(ap[da['part_id']].intersection(ap[db['part_id']]),ga)
        mateok &= da['mate_feature_id']==db['feature_id'] and db['mate_feature_id']==da['feature_id']
    check('joint_pairs_XY_match_opposite_faces',bool(pairgood),{'pairs':len(by_pair),'max_mismatch_area_mm2':maxmismatch})
    check('mate_feature_links_bidirectional',bool(mateok))
    # Each part becomes 2D regions carrying the Z range that survives machining:
    # untouched material keeps the full thickness, while a pocket cut from face A
    # leaves 0..THK-DEPTH on a FRONT part and DEPTH..THK on a flipped one. Deriving
    # the range from the actual depth is what makes a wrong depth measurable here;
    # assuming two complementary half-slabs would quietly accept any value. Each
    # range is then shifted by the part's assembly Z, so members on different
    # layers may overlap in the front view.
    solids={}
    for pid,g in ap.items():
        cut=[e for e in pockets+dogs if meta(e)['part_id']==pid]
        removal=unary_union([assembled(pid,geom[e.dxf.handle]) for e in cut]) if cut else None
        front=meta(partents[pid])['assembly_face_A']=='FRONT'
        pieces=[(g if removal is None else g.difference(removal),0.,float(cfg.THK))]
        if removal is not None:
            pieces.append((removal.intersection(g),
                           0.,float(cfg.THK-cfg.DEPTH)) if front else
                          (removal.intersection(g),float(cfg.DEPTH),float(cfg.THK)))
        z=float(cfg.PART_Z.get(pid,0.))
        solids[pid]=[(r,z+z0,z+z1) for r,z0,z1 in pieces if not r.is_empty and r.area>AREA_TOL_MM2 and z1>z0]
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
           'method':f'per-region Z ranges from depth {cfg.DEPTH:g} in stock {cfg.THK:g}; '
                    f'actual circular bulges sampled with chord error <= {ARC_CHORD_TOL_MM:g} mm'})
    check('half_lap_depth',abs(2*cfg.DEPTH-cfg.THK)<TOL,
          {'retained_front':cfg.THK-cfg.DEPTH,'retained_back':cfg.THK-cfg.DEPTH,'stock':cfg.THK})
    return ap,assembled


def check_assembly_dimensions(cfg,check,partents,ap):
    """Frame, requested size, leaves, clearances and lattice spacing measured on the assembly."""
    fixed=unary_union([g for pid,g in ap.items() if pid.startswith('F')])
    leaves=[unary_union([g for pid,g in ap.items() if meta(partents[pid])['assembly_group']==group_name(cfg.D,i)]) for i in range(cfg.NLEAF)]
    check('frame_geometry',geometry_matches(fixed,box(0,0,cfg.W,cfg.H).difference(box(cfg.FW,cfg.FW,cfg.W-cfg.FW,cfg.H-cfg.FW))),
          dict(bounds=list(fixed.bounds),area_mm2=fixed.area))
    # Re-measure the size in the basis it was requested in: the outer boundary of
    # the assembled fixed frame, or the clear opening that frame encloses.
    holes=[box(*ring.bounds) for ring in getattr(fixed,'interiors',[])]
    hole=max(holes,key=lambda g:g.area).bounds if holes else None
    measured=dict(outer=[fixed.bounds[2]-fixed.bounds[0],fixed.bounds[3]-fixed.bounds[1]],
                  inner=[hole[2]-hole[0],hole[3]-hole[1]] if hole else None)
    got=measured[cfg.SIZE['basis']]
    check('requested_size_matches_measured_frame',
          got is not None and all(abs(a-b)<TOL for a,b in zip(got,cfg.SIZE['requested_mm'])),
          dict(actual=got,required=cfg.SIZE['requested_mm'],basis=cfg.SIZE['basis'],measured_mm=measured),
          target='inner_mm' if cfg.SIZE['basis']=='inner' else 'outer_mm')
    check('leaf_envelopes',all(
        coordinates_match(lf.bounds,cfg.LEAVES[i]) for i,lf in enumerate(leaves)),
        [[lf.bounds[2]-lf.bounds[0],lf.bounds[3]-lf.bounds[1]] for lf in leaves])
    # Read the proportion off the assembled members rather than from LW/LH, so it
    # still holds if the leaf envelope itself were derived wrongly.
    ratios=[(lf.bounds[3]-lf.bounds[1])/(lf.bounds[2]-lf.bounds[0]) for lf in leaves]
    check('leaf_height_to_width_ratio',all(r>=cfg.MINR-RATIO_TOL for r in ratios),
          [round(r,6) for r in ratios])
    gapsok=all(abs(lf.distance(fixed)-cfg.GAP_OUT)<TOL for lf in leaves)
    gapsok &= all(abs(leaves[i].distance(leaves[i+1])-cfg.GAP_MID)<TOL for i in range(cfg.NLEAF-1))
    check('leaf_clearances',gapsok,dict(external=[lf.distance(fixed) for lf in leaves],
          meeting=[leaves[i].distance(leaves[i+1]) for i in range(cfg.NLEAF-1)]))
    # Measure lattice spacing off the assembled bars. The pocket formula check
    # calls bar_offsets(), the same helper the generator uses to place the bars,
    # so an error inside that helper cancels out there and cannot be caught. This
    # block asks nothing about where a bar should be: it reads the opening from
    # the sash members, reads the bar edges, and requires the resulting gaps to be
    # equal to each other and to the span left over once the bars are subtracted.
    spacing_ok=True;cells={}
    for i in range(cfg.NLEAF):
        grp=group_name(cfg.D,i)
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
    check('no_fixed_centre_mullion',fixed.intersection(box(cfg.FW,cfg.FW,cfg.W-cfg.FW,cfg.H-cfg.FW)).area<AREA_TOL_MM2)
    leafbox={group_name(cfg.D,i):box(*cfg.LEAVES[i]) for i in range(cfg.NLEAF)}
    check('no_member_bridges_leaves',all(leafbox[meta(e)['assembly_group']].buffer(TOL).covers(ap[pid])
          for pid,e in partents.items() if meta(e)['assembly_group']!='FIXED'))


def reference_geometry(e):
    """Model-space shape of one reference entity: closed polyline, line or text anchor."""
    if e.dxftype()=='LINE':return LineString([(e.dxf.start.x,e.dxf.start.y),(e.dxf.end.x,e.dxf.end.y)])
    if e.dxftype()=='TEXT':
        p=e.dxf.align_point if e.dxf.halign or e.dxf.valign else e.dxf.insert
        return Point(p.x,p.y)
    return entity_polygon(e)


def check_references(cfg,check,ents,mach,pockets,count,byjoint,ap,assembled):
    """Assembly, picture, opening, hardware and detail references against the cut parts."""
    ox,oy=cfg.ASSEMBLY_ORIGIN
    assemblies=[e for e in ents if meta(e).get('view')=='assembly']
    abodies=[e for e in assemblies if meta(e).get('role')=='body']
    check('assembly_reference_matches_all_cut_parts',len(abodies)==cfg.NPART and all(geometry_matches(translate(entity_polygon(e),-ox,-oy),ap[meta(e)['part_id']]) for e in abodies))
    pictures=[e for e in assemblies if meta(e).get('role')=='picture']
    regions=[e for e in assemblies if meta(e).get('role')=='picture_region']
    margins={};picture_ok=not pictures and not regions;line_ok=picture_ok;margin_ok=picture_ok
    if cfg.PICTURE:
        picture_ok=len(pictures)==len(regions)==1;line_ok=margin_ok=False
        if picture_ok:
            pic,reg=pictures[0],regions[0]
            pg=translate(entity_polygon(pic),-ox,-oy);rg=translate(entity_polygon(reg),-ox,-oy)
            picture_ok=geometry_matches(pg,box(cfg.PICX,cfg.PICY,cfg.PICX+cfg.A3W,cfg.PICY+cfg.A3H)) and geometry_matches(rg,box(cfg.PX,cfg.PY,cfg.PX+cfg.PRW,cfg.PY+cfg.PRH))
            px0,py0,px1,py1=pg.bounds;rx0,ry0,rx1,ry1=rg.bounds
            margins=dict(left=px0-rx0,right=rx1-px1,bottom=py0-ry0,top=ry1-py1)
            margin_ok=rg.buffer(TOL).covers(pg) and all(v>=cfg.PMG-TOL for v in margins.values()) and close(margins['left'],margins['right'],TOL) and close(margins['top'],margins['bottom'],TOL)
            line_ok=pic.dxf.linetype!=reg.dxf.linetype
    check('picture_geometry',picture_ok,dict(enabled=cfg.PICTURE,pictures=len(pictures),regions=len(regions)))
    check('picture_margins_match_each_side',margin_ok,dict(required_minimum_mm=cfg.PMG,measured_mm=margins))
    check('picture_reference_linetypes',line_ok)
    openings=[e for e in assemblies if meta(e).get('role')=='opening']
    opening_geometry=[entity_polygon(e) for e in openings]
    check('leaf_opening_references',len(openings)==cfg.NLEAF and all(
        geometry_matches(g,box(g.bounds[0],g.bounds[1],g.bounds[0]+cfg.OW,g.bounds[1]+cfg.OH)) for g in opening_geometry),
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
    wanthw={'HINGE':2*cfg.NLEAF,'HANDLE':cfg.NLEAF,'CATCH':cfg.NLEAF}
    check('hardware_counts_and_references',
          bool(hwmatch) and {k:len(v) for k,v in hwtype.items()}==wanthw,{k:len(v) for k,v in hwtype.items()})
    expected_hw={(r['hardware_id'],r['part_id']):box(*r['box']) for r in hardware_records(cfg)}
    actual_hw={(meta(e)['hardware_id'],meta(e)['part_id']):assembled(meta(e)['part_id'],entity_polygon(e)) for e in hws}
    check('hardware_attachment_geometry',set(actual_hw)==set(expected_hw) and all(geometry_matches(g,expected_hw[k]) for k,g in actual_hw.items() if k in expected_hw),
          dict(attachments=[list(k) for k in actual_hw]))
    detailtypes={meta(e).get('detail') for e in ents if meta(e).get('view')=='detail'}
    check('reference_details_match_existing_joints',detailtypes==({'J1','J2'} | ({'J3'} if byjoint['J3'] else set()) | ({'J4V'} if count['L01'] else set()) | ({'J4H'} if count['L02'] else set())),sorted(detailtypes))
    detailborders=[e for e in ents if meta(e).get('kind')=='detail_border']
    check('reference_detail_members_exist',all(all(count[k]>0 for k in meta(e)['detail_part_kinds']) for e in detailborders),[meta(e)['detail_part_kinds'] for e in detailborders])
    check('references_never_on_machining_layers',not any(meta(e).get('view') in ['assembly','detail','opening'] for e in mach))
    # A CAM import of the whole sheet must not put a reference view on the parts.
    # Detail dimensions carry only a detail key. TEXT is tested at its anchor,
    # because how far it runs depends on the font.
    board=box(0,0,cfg.BL,cfg.BWD)
    refs=[e for e in ents if meta(e).get('view') in REFERENCE_VIEWS or meta(e).get('detail')]
    onboard=sum(board.intersects(reference_geometry(e)) for e in refs)
    check('references_outside_board',onboard==0,dict(reference_entities=len(refs),on_board=onboard))
    opened=[e for e in ents if meta(e).get('kind')=='opened_leaf_illustration']
    check('opening_illustration_matches_leaves',len(opened)==cfg.NLEAF and {meta(e).get('leaf') for e in opened}=={f.side.upper() for f in cfg.FORMAT} and all(meta(e).get('reference_only') for e in opened),len(opened))
    # A pocket check, kept last here because the report lists checks in call order.
    check('pockets_open_edge_intent',all(bool(meta(e).get('open_edges')) for e in pockets))


def check_metadata(cfg,check,doc,spec_path):
    """Recorded revision and numeric policy, design_spec.json on disk and the DXF audit."""
    md=doc.ezdxf_metadata()
    check('revision_recorded_matches_parameters',
          md.get('HANOK_REVISION')==cfg.PARAMS['revision'] and md.get('HANOK_BUILD_DATE')==cfg.PARAMS['build_date'],
          {'revision':md.get('HANOK_REVISION'),'build_date':md.get('HANOK_BUILD_DATE')})
    check('numeric_policy_recorded',md.get('HANOK_NUMERIC_POLICY')==POLICY_VERSION,policy_record())
    spec_path=cfg.SPEC if spec_path is None else spec_path
    if spec_path.is_file():
        fresh=json.dumps(build_spec(cfg.PARAMS),sort_keys=True)
        check('design_spec_on_disk_matches_parameters',fresh==json.dumps(json.loads(spec_path.read_text(encoding='utf-8')),sort_keys=True))
    audit=doc.audit()
    check('DXF_audit_no_errors_no_fixes',not audit.has_errors and not audit.has_fixes,{'errors':len(audit.errors),'fixes':len(audit.fixes)})


def write_manifests(cfg,doc):
    ents=list(doc.modelspace());pmap={meta(e)['part_id']:meta(e) for e in ents if e.dxf.layer=='CUT_THROUGH'}
    def emit(name,rows):
        with (cfg.OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
            fields=list(rows[0]) if rows else ['part_id','feature_id','parent_pocket','center_u_mm','center_v_mm','radius_mm','depth_mm','intent','dxf_handle']
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    emit('parts_manifest.csv',[dict(part_id=pid,length_mm=d['length_mm'],width_mm=d['width_mm'],thickness_mm=cfg.THK,
         nest_x_mm=d['nesting_origin'][0],nest_y_mm=d['nesting_origin'][1],assembly_group=d['assembly_group'],
         A_face_in_assembly=d['assembly_face_A'],grain_axis='X',assembly_affine=json.dumps(d['assembly_map']),
         pocket_count=sum(meta(e).get('part_id')==pid and e.dxf.layer==cfg.POCKET_LAYER for e in ents)) for pid,d in pmap.items()])
    emit('pocket_manifest.csv',[dict(part_id=d['part_id'],feature_id=d['feature_id'],joint=d['joint'],pair_id=d['joint_id'],
         u0_mm=d['local_rect'][0],v0_mm=d['local_rect'][1],length_mm=d['local_rect'][2],width_mm=d['local_rect'][3],
         depth_mm=cfg.DEPTH,seat=d['seat'],mate_part_id=d['mate_part_id'],mate_feature_id=d['mate_feature_id'],
         open_edges=';'.join(d['open_edges']),A_face_in_assembly=pmap[d['part_id']]['assembly_face_A'],dxf_handle=e.dxf.handle)
         for e in ents if e.dxf.layer==cfg.POCKET_LAYER for d in [meta(e)]])
    emit('dogbone_manifest.csv',[dict(part_id=d['part_id'],feature_id=d['feature_id'],parent_pocket=d['parent_pocket'],
         center_u_mm=d['local_center'][0],center_v_mm=d['local_center'][1],radius_mm=cfg.R,depth_mm=cfg.DEPTH,
         intent='UNION_WITH_PARENT_POCKET',dxf_handle=e.dxf.handle)
         for e in ents if e.dxf.layer=='DOGBONE' for d in [meta(e)]])
    emit('hardware_reference_manifest.csv',[dict(hardware_id=d['hardware_id'],hardware_type=d['hardware_type'],part_id=d['part_id'],
         layer=e.dxf.layer,production_machining=False,front_face_position_only=True,depth_ref_mm=d.get('depth_ref_mm','UNSPECIFIED'),
         dxf_handle=e.dxf.handle) for e in ents if meta(e).get('kind')=='hardware_ref' and meta(e).get('view')=='nest' for d in [meta(e)]])


def add_details(cfg,msp):
    variants=formats.detail_variants(cfg.PARAMS)
    positions={key:(cfg.ASSEMBLY_ORIGIN[0]+cfg.W+160+(i%2)*270,100+(2-i//2)*210) for i,key in enumerate(variants)}
    for key,(ox,oy) in positions.items():
        j='J4' if key.startswith('J4') else key
        kinds={'J1':['F01','F02'],'J2':['S01','S02'],'J3':['L01','L02'],'J4V':['S02','L01'],'J4H':['S01','L02']}[key]
        common={'detail':key,'view':'detail','detail_part_kinds':kinds,'joint_type':j}
        def tx(s,x,y,h=3.8,align='left',layer='NOTES'):
            return text(msp,s,(ox+x,oy+y),h,layer,align,**common)
        def rr(x,y,w,h,role='body',**kw):
            return rect(msp,ox+x,oy+y,w,h,'JOINT_DETAILS_REF',role=role,**common,**kw)
        def pp(pts,role='body',**kw):
            if key=='J4H':role={'section_front':'section_back','section_back':'section_front'}.get(role,role)
            return poly(msp,[(ox+x,oy+y) for x,y in pts],'JOINT_DETAILS_REF',role=role,**common,**kw)
        rect(msp,ox,oy,240,190,'NOTES',kind='detail_border',**common)
        names={'J1':'FIXED FRAME HALF-LAP','J2':'SASH HALF-LAP',
               'J3':'LATTICE CROSSING HALF-LAP','J4':'LATTICE-TO-SASH SEAT'}
        tx(f'{key}  {names[j]}',10,178,7)
        n=cfg.FW if j=='J1' else cfg.SM if j=='J2' else cfg.BW
        across=cfg.LAP if j=='J4' else n
        tx(f'{n:g} x {across:g} pocket / depth {cfg.DEPTH:g} / stock {cfg.THK:g}',10,164,4.7)
        if j in ('J1','J2'):
            fam1,fam2=('F01','F02') if j=='J1' else ('S01','S02')
            by=97 if j=='J1' else 107
            tx(f'{fam1} / A -> FRONT',15,148,4)
            tx(f'{fam2} / A -> BACK (flip)',135,148,3.6)
            rr(15,by,80,n); rr(135,by,80,n)
            rr(15,by,n,n,'pocket'); rr(135,by,n,n,'pocket')
            dimh(msp,ox+15,ox+15+n,oy+by,oy+by-9,f'{n:g}',detail=key)
            dimv(msp,oy+by,oy+by+n,ox+95,ox+104,f'{n:g}',detail=key)
            dimh(msp,ox+135,ox+135+n,oy+by,oy+by-9,f'{n:g}',detail=key)
            # Section schematic: complementary retained halves at their overlap.
            sx=70; sy=36
            pp([(sx,sy),(sx+20+n,sy),(sx+20+n,sy+cfg.DEPTH),(sx+20,sy+cfg.DEPTH),
                (sx+20,sy+cfg.THK),(sx,sy+cfg.THK)],'section_back')
            pp([(sx+20,sy+cfg.DEPTH),(sx+20+n,sy+cfg.DEPTH),(sx+20+n,sy),
                (sx+40+n,sy),(sx+40+n,sy+cfg.THK),(sx+20,sy+cfg.THK)],'section_front')
            dimv(msp,oy+sy,oy+sy+cfg.THK,ox+sx+40+n,ox+sx+50+n,f'{cfg.THK:g}',detail=key)
            dimv(msp,oy+sy+cfg.DEPTH,oy+sy+cfg.THK,ox+sx+20+n,ox+sx+66+n,f'{cfg.DEPTH:g} depth',detail=key)
            tx('ASSEMBLED SECTION - complementary faces',15,69,4)
            tx('Local end regions only; open edges need cutter overrun in CAM.',10,18,3.3)
        elif j=='J3':
            tx('L01 / A -> FRONT',15,148,4)
            tx('L02 / A -> BACK (flip)',135,148,3.7)
            rr(15,125,80,cfg.BW);rr(135,125,80,cfg.BW)
            rr(50,125,cfg.BW,cfg.BW,'pocket');rr(170,125,cfg.BW,cfg.BW,'pocket')
            dimh(msp,ox+50,ox+50+cfg.BW,oy+125,oy+112,f'{cfg.BW:g}',detail=key)
            dimv(msp,oy+125,oy+125+cfg.BW,ox+95,ox+105,f'{cfg.BW:g}',detail=key)
            dimh(msp,ox+170,ox+170+cfg.BW,oy+125,oy+112,f'{cfg.BW:g}',detail=key)
            tx(f'{cfg.D["crossings_total"]} crossings x 2 matching pockets = {cfg.NPOCK["J3"]} pockets',15,95,4.2)
            sx=85;sy=40
            rr(sx+20,sy,cfg.BW,cfg.DEPTH,'section_back')
            pp([(sx,sy),(sx+20,sy),(sx+20,sy+cfg.DEPTH),(sx+20+cfg.BW,sy+cfg.DEPTH),
                (sx+20+cfg.BW,sy),(sx+50,sy),(sx+50,sy+cfg.THK),(sx,sy+cfg.THK)],'section_front')
            dimv(msp,oy+sy,oy+sy+cfg.THK,ox+sx+50,ox+sx+60,f'{cfg.THK:g}',detail=key)
            dimv(msp,oy+sy+cfg.DEPTH,oy+sy+cfg.THK,ox+sx+20+cfg.BW,ox+sx+76,f'{cfg.DEPTH:g} depth',detail=key)
            tx('ASSEMBLED SECTION - front and back remain flush',15,75,4)
            tx(f'Slots span the entire {cfg.BW:g} mm bar width. No closed-side dogbones.',10,18,3.3)
        else:
            tx('S02 receiver / A -> BACK' if key=='J4V' else 'S01 receiver / A -> FRONT',15,148,3.9)
            tx('L01 end / A -> FRONT' if key=='J4V' else 'L02 end / A -> BACK',135,148,3.9)
            # The seat is BW wide along the rail and LAP deep into it; those are
            # two different parameters even though the default design shares 10.
            seat=107+cfg.SM-cfg.LAP
            rr(15,107,80,cfg.SM);rr(135,117,70,cfg.BW)
            rr(45,seat,cfg.BW,cfg.LAP,'pocket');rr(135,117,cfg.LAP,cfg.BW,'pocket')
            for cx in (45,45+cfg.BW):
                circle_poly(msp,ox+cx,oy+seat,cfg.R,'JOINT_DETAILS_REF',
                            role='dogbone',**common,radius_mm=cfg.R)
            dimh(msp,ox+45,ox+45+cfg.BW,oy+seat,oy+116,f'{cfg.BW:g}',detail=key)
            dimv(msp,oy+seat,oy+107+cfg.SM,ox+95,ox+105,f'{cfg.LAP:g} lap',detail=key)
            dimh(msp,ox+135,ox+135+cfg.LAP,oy+117,oy+105,f'{cfg.LAP:g}',detail=key)
            tx(f'2 x R{cfg.R:g} at closed corners; union with nominal pocket',15,82,3.7)
            # Sectioned along the insertion direction, so the stepped overlap runs
            # for LAP, not for the bar width. Depth stays a Z quantity.
            sx=83;sy=35
            pp([(sx,sy),(sx+20,sy),(sx+20,sy+cfg.DEPTH),(sx+20+cfg.LAP,sy+cfg.DEPTH),
                (sx+20+cfg.LAP,sy+cfg.THK),(sx,sy+cfg.THK)],'section_front')
            pp([(sx+20,sy),(sx+55,sy),(sx+55,sy+cfg.THK),(sx+20+cfg.LAP,sy+cfg.THK),
                (sx+20+cfg.LAP,sy+cfg.DEPTH),(sx+20,sy+cfg.DEPTH)],'section_back')
            dimv(msp,oy+sy,oy+sy+cfg.THK,ox+sx+55,ox+sx+65,f'{cfg.THK:g}',detail=key)
            dimv(msp,oy+sy+cfg.DEPTH,oy+sy+cfg.THK,ox+sx+20+cfg.LAP,ox+sx+81,f'{cfg.DEPTH:g} depth',detail=key)
            dimh(msp,ox+sx+20,ox+sx+20+cfg.LAP,oy+sy,oy+sy-12,f'{cfg.LAP:g} lap',detail=key)
            tx(f'ASSEMBLED SECTION / {cfg.LAP:g} mm seat depth, {cfg.DEPTH:g} mm in Z',15,67,4)
            tx(f'{kinds[0]} + {kinds[1]}: {2*cfg.NLEAF*(cfg.NV if key=="J4V" else cfg.NH)} end joints in this design.',10,18,3.4)
        tx('REFERENCE ONLY / DXF 1:1 / PNG enlarged',10,7,3.2)
    return positions


def render_details(cfg,doc,positions):
    rows=math.ceil(len(positions)/2);height=280+rows*1680+220
    im=Image.new('RGB',(4400,height),COL['white']);d=ImageDraw.Draw(im)
    label(d,(120,65),'02  JOINERY DETAILS',65,bold=True)
    label(d,(120,153),f'Closed pocket geometry  |  All wood {cfg.THK:g} mm thick  |  Pocket depth {cfg.DEPTH:g} mm  |  Exact R{cfg.R:g} relief arcs',31,fill=COL['muted'])
    d.line((120,220,4280,220),fill=COL['border'],width=3)
    viewports={key:(100+(i%2)*2160,280+(i//2)*1680,2040,1615) for i,key in enumerate(positions)}
    for j,(ox,oy) in positions.items():
        vp=viewports[j];r=Renderer(im,(ox,oy,ox+240,oy+190),vp)
        ents=[e for e in doc.modelspace() if meta(e).get('detail')==j]
        # All geometry is read from the reference detail regions in the final DXF.
        r.entities(ents)
    y=height-190
    legend=[(COL['pocket'],f'{cfg.DEPTH:g} mm pocket'),(COL['dog'],f'R{cfg.R:g} relief'),
            (COL['front'],'retained front half'),(COL['back'],'retained back half')]
    x=160
    for c,s in legend:
        d.rectangle((x,y,x+43,y+43),fill=c,outline=COL['line'],width=2)
        label(d,(x+65,y+3),s,29);x+=1015
    label(d,(120,height-85),'Detail geometry stays 1:1 in DXF Model Space. Only this PNG view is enlarged. Dimensions are millimetres.',27,fill=COL['muted'])
    im.save(cfg.OUT/'02_joinery_details.png',dpi=(220,220));return im


def nest_entities(cfg,doc,full=True):
    ents=list(doc.modelspace());out=[]
    if full:out += [e for e in ents if e.dxf.layer=='BOARD_BOUNDARY']
    for lay in ['CUT_THROUGH',cfg.POCKET_LAYER,'DOGBONE','HINGE_REF','LATCH_REF','PART_ID']:
        out += [e for e in ents if e.dxf.layer==lay and (lay in ['CUT_THROUGH',cfg.POCKET_LAYER,'DOGBONE'] or meta(e).get('view')=='nest')]
    # Notes below the board lie outside the nesting viewport; the side panel carries them.
    if full:out += [e for e in ents if meta(e).get('view')=='nest' and e.dxf.layer in ['GRAIN_DIRECTION','NOTES','DIMENSIONS'] and meta(e).get('kind') not in ('title','sheet_note')]
    return out


def cutzone(cfg,report):
    """Framing box for the enlarged views, taken from the measured nesting bounds."""
    nb=report['nesting_bounds_mm']
    return (0,0,nb[2]+cfg.MARGIN,nb[3]+cfg.MARGIN)


def render_nesting(cfg,doc,report):
    im=Image.new('RGB',(4400,4280),COL['white']);d=ImageDraw.Draw(im)
    nb=report['nesting_bounds_mm']
    label(d,(120,65),f'01  ONE-BOARD NESTING / {cfg.TITLE}',61,bold=True)
    label(d,(120,155),f'{cfg.BL:g} x {cfg.BWD:g} x {cfg.BT:g} mm  |  CNC face A  |  {cfg.W:g} W x {cfg.H:g} H assembled  |  All part lengths parallel to +X grain',28,fill=COL['muted'])
    d.line((120,225,4280,225),fill=COL['border'],width=3)
    r=Renderer(im,(-45,-52,cfg.BL+20,cfg.BWD+46),(90,280,3000,2370));r.entities(nest_entities(cfg,doc,True))
    x,y,w=3190,310,980
    label(d,(x,y),'SAVED DXF CHECKED',33,bold=True);y+=75
    for value,desc in [(report['parts_total'],'independent wooden parts'),
                       (report['nominal_pockets_total'],'closed nominal pocket contours'),
                       (report['dogbone_reliefs_total'],f'exact R{cfg.R:g} relief contours'),
                       (report['mated_joints_total'],'matching half-lap joint pairs')]:
        label(d,(x,y),str(value),66,bold=True);label(d,(x+165,y+25),desc,25);y+=118
    y+=20;d.line((x,y,x+w,y),fill=COL['border'],width=3);y+=43
    label(d,(x,y),'LAYER / MACHINING INTENT',30,bold=True);y+=70
    for col,ttl,sub in [(COL['wood'],'CUT_THROUGH',f'{cfg.THK:g} mm nominal full-depth outer profile'),
                        (COL['pocket'],cfg.POCKET_LAYER,f'{cfg.DEPTH:g} mm deep from common A face'),
                        (COL['dog'],'DOGBONE',f'{cfg.DEPTH:g} mm deep; union with parent seat'),
                        (COL['hardware'],'HINGE_REF / LATCH_REF','Reference only. EXCLUDE FROM CAM.')]:
        d.rectangle((x,y,x+40,y+40),fill=col,outline=COL['line'],width=2)
        label(d,(x+62,y),ttl,27,bold=True)
        label(d,(x+62,y+44),sub,24,fill=COL['muted']);y+=116
    y+=25;label(d,(x,y),'ASSEMBLY FACE ORIENTATION',29,bold=True);y+=62
    for s in [face_note(cfg),
              f'Minimum stock edge margin: {cfg.MARGIN:g} mm.',
              f'Minimum between-part gap: {cfg.PGAP:g} mm.',
              f'Cut-zone envelope: X{nb[0]:g}-{nb[2]:g} / Y{nb[1]:g}-{nb[3]:g}.',
              'Open-edge laps need waste-side cutter overrun.',
              'No tabs, toolpaths, feeds or speeds included.']:
        y=wrapped(d,s,(x,y),w,26);y+=20
    label(d,(120,2760),f'CUT-ZONE ENLARGEMENT / SAME {report["parts_total"]} PARTS',45,bold=True)
    label(d,(120,2830),'A second viewport of the saved DXF, not additional parts. Pocket and relief positions are taken from CAD entities.',27,fill=COL['muted'])
    d.rounded_rectangle((95,2900,4300,4140),radius=18,fill=COL['panel'],outline=COL['border'],width=2)
    rr=Renderer(im,cutzone(cfg,report),(130,2920,4120,1200));rr.entities(nest_entities(cfg,doc,False))
    label(d,(120,4180),'NOMINAL GEOMETRY ONLY  |  Fit coupons, actual hardware and CAM setup require approval before production.',27,fill=COL['muted'])
    im.save(cfg.OUT/'01_one_board_nesting.png',dpi=(220,220))


def render_closeup(cfg,doc,report):
    im=Image.new('RGB',(4400,1850),COL['white']);d=ImageDraw.Draw(im)
    label(d,(110,60),'05  ALL POCKETS / CUT-ZONE CLOSEUP',58,bold=True)
    label(d,(110,145),f'Same {report["parts_total"]} parts at increased viewing scale  |  {report["nominal_pockets_total"]} nominal pockets + {report["dogbone_reliefs_total"]} reliefs  |  Closed DXF contours',28,fill=COL['muted'])
    Renderer(im,cutzone(cfg,report),(100,245,4200,1400)).entities(nest_entities(cfg,doc,False))
    label(d,(110,1720),'Part labels are annotations, not engraving. Dashed hardware outlines are references, not approved machining.',28,fill=COL['muted'])
    im.save(cfg.OUT/'05_all_pockets_closeup.png',dpi=(220,220))


def render_assembly(cfg,doc):
    im=Image.new('RGB',(3600,3950),COL['white']);d=ImageDraw.Draw(im)
    label(d,(105,62),f'03  ASSEMBLY / {cfg.TITLE}',54,bold=True)
    label(d,(105,151),f'{cfg.W:g} x {cfg.H:g} mm frame | {cfg.NLEAF} leaf, each {cfg.LW:g} x {cfg.LH:g} mm | Lattice {cfg.NV} vertical + {cfg.NH} horizontal',27,fill=COL['muted'])
    d.line((105,225,3495,225),fill=COL['border'],width=3)
    ox,oy=cfg.ASSEMBLY_ORIGIN
    r=Renderer(im,(ox-78,oy-92,ox+cfg.W+75,oy+cfg.H+80),(70,290,2590,2980))
    ents=[e for e in doc.modelspace() if meta(e).get('view')=='assembly' and meta(e).get('kind')!='title']
    for role in ('picture','body','other'):
        r.entities([e for e in ents if (meta(e).get('role')==role if role!='other' else meta(e).get('role') not in ('picture','body'))])
    x,y,w=2760,360,700
    basis='Outer frame' if cfg.SIZE['basis']=='outer' else 'Fixed-frame inner opening'
    schedule=[('WINDOW',cfg.TITLE),
              ('SIZE BASIS',f'{basis} {cfg.SIZE["requested_mm"][0]:g} x {cfg.SIZE["requested_mm"][1]:g} mm. Outer {cfg.W:g} x {cfg.H:g}, inner {cfg.IW:g} x {cfg.IH:g}.'),
              ('EACH OPENING',f'{cfg.OW:g} x {cfg.OH:g} mm before lattice subdivision.'),
              ('LATTICE',f'{cfg.NV} vertical + {cfg.NH} horizontal per leaf; {cfg.NV*cfg.NH} crossings.'),
              ('CLEARANCES',f'Frame to leaf: {cfg.GAP_OUT:g} mm.'+(f' Between leaves: {cfg.GAP_MID:g} mm.' if cfg.NLEAF==2 else '')),
              ('REAR PICTURE',f'{cfg.A3W:g} x {cfg.A3H:g} mm, centred, minimum margin {cfg.PMG:g} mm.' if cfg.PICTURE else 'No picture specified.'),
              ('HARDWARE REFERENCES',f'{2*cfg.NLEAF} hinges, {cfg.NLEAF} handles, {cfg.NLEAF} catches. Hinge sides: '+', '.join(f.side for f in cfg.FORMAT)+'.'),
              ('JOINT DETAILS',', '.join(formats.detail_variants(cfg.PARAMS)))]
    for ttl,body in schedule:
        label(d,(x,y),ttl,27,bold=True);y+=48
        y=wrapped(d,body,(x,y),w,28);y+=40
    d.rounded_rectangle((110,3410,3490,3800),radius=18,fill=COL['panel'],outline=COL['border'],width=2)
    label(d,(160,3460),'ASSEMBLY AND FABRICATION STATUS',34,bold=True)
    notes=[face_note(cfg),
           'Hardware shapes and opening axes are position references. Products and load capacity remain PENDING.',
           'Material minima, fit coupons, backing and CAM setup remain PENDING.']
    if cfg.PICTURE:notes.append('The picture is fixed to a separate rear support, never to moving leaves.')
    y=3530
    for note in notes:y=wrapped(d,note,(160,y),3270,28)+20
    label(d,(110,3850),'Reference members are transformed from the saved and verified CNC part geometry.',27,fill=COL['muted'])
    im.save(cfg.OUT/'03_assembly_reference.png',dpi=(220,220))


def render_opening(cfg,doc):
    im=Image.new('RGB',(4000,2750),COL['white']);d=ImageDraw.Draw(im)
    label(d,(110,60),f'04  OPENING / {cfg.TITLE}',55,bold=True)
    label(d,(110,152),f'Looking down | {cfg.NLEAF} moving leaf | Opening toward the viewer | Reference axes',28,fill=COL['muted'])
    d.line((110,225,3890,225),fill=COL['border'],width=3)
    ox,oy=cfg.OPENING_ORIGIN
    Renderer(im,(ox-50,oy-100,ox+cfg.W+50,oy+max(360,cfg.LW+cfg.THK+110)),(110,285,2720,2190)).entities(
        [e for e in doc.modelspace() if meta(e).get('view')=='opening'])
    y=365
    for ttl,body in [('ILLUSTRATION ONLY','The plan shows a nominal 90-degree rotation about provisional front-projecting axes.'),
                     ('HINGE SIDES',', '.join(f.side.upper() for f in cfg.FORMAT)+'; two hinges per leaf.'),
                     ('REAR PICTURE',f'One fixed {cfg.A3W:g} x {cfg.A3H:g} mm picture on a separate backing.' if cfg.PICTURE else 'No picture or rear picture plane is specified.'),
                     ('PENDING','Select actual hinges, screws, catches and backing. Check full movement, loads and clearances before manufacture.')]:
        label(d,(2970,y),ttl,29,bold=True);y+=57
        y=wrapped(d,body,(2970,y),875,29)+66
    label(d,(115,2580),'REFERENCE ONLY / Dynamic interference and real hardware are not validated by this illustration.',29,bold=True)
    label(d,(115,2650),'No opening diagram is a CNC pocket or a toolpath.',27,fill=COL['muted'])
    im.save(cfg.OUT/'04_opening_reference.png',dpi=(220,220))


def write_readme(cfg,report):
    ma=report['manufacturing_assessment']
    lines=[f"한옥 창호 CAD 패키지 / {cfg.PARAMS['revision']}",f'형식: {cfg.TITLE}',
           f'외곽: {cfg.W:g} x {cfg.H:g} mm. 창짝 {cfg.NLEAF}개, 각각 {cfg.LW:g} x {cfg.LH:g} mm.',
           f"크기 기준: {'외경(완성 외곽)' if cfg.SIZE['basis']=='outer' else '내경(고정틀 안목)'} {cfg.SIZE['requested_mm'][0]:g} x {cfg.SIZE['requested_mm'][1]:g} mm 입력. 외경 {cfg.W:g} x {cfg.H:g}, 내경 {cfg.IW:g} x {cfg.IH:g} mm.",
           f'창짝당 창살: 세로 {cfg.NV}, 가로 {cfg.NH}. 교차점 {cfg.NV*cfg.NH}개.',
           f'부품 {cfg.NPART}, 홈 {cfg.NPOCKT}, 도그본 {cfg.NDOG}, 결합쌍 {cfg.NPOCKT//2}.',
           f'원판: {cfg.BL:g} x {cfg.BWD:g} x {cfg.THK:g} mm. 부재 길이는 목리 X 방향.',
           f'가공 깊이: {cfg.DEPTH:g} mm. 모든 가공은 A면. 공구 지름 {cfg.PARAMS["machining"]["tool_diameter"]:g}, 도그본 R{cfg.R:g}.',
           f'창짝-고정틀 간극 {cfg.GAP_OUT:g} mm.'+(f' 창짝 사이 간극 {cfg.GAP_MID:g} mm.' if cfg.NLEAF==2 else ''),
           f'그림: {cfg.A3W:g} x {cfg.A3H:g} mm, 후면 기준영역 안에 중앙 배치, 각 변 최소 여유 {cfg.PMG:g} mm.' if cfg.PICTURE else '그림: 지정하지 않음.',
           '실제 존재하는 결합 상세: '+', '.join(formats.detail_variants(cfg.PARAMS)),
           f'경첩 {2*cfg.NLEAF}, 손잡이 {cfg.NLEAF}, 캐치 {cfg.NLEAF}: 실물 선정 전 참고 위치.',
           '경첩 부재: '+', '.join(f'{f.hinge_stile}/{f.fixed_stile}' for f in cfg.FORMAT),
           '손잡이 부재: '+', '.join(f.handle_stile for f in cfg.FORMAT),
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
    (cfg.OUT/'README.txt').write_bytes(('\n'.join(lines)+'\n').encode('utf-8'))
