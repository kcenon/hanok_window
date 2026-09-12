#!/usr/bin/env python3
"""Build and audit a one-board A3 hanok window.
Geometry is nominal, not a CAM toolpath. Requires ezdxf>=1.4, shapely>=2, Pillow.
All machining contours are independent, closed Model Space LWPOLYLINEs.
"""
from __future__ import annotations
import csv, json, math, hashlib, itertools, sys, zipfile
from collections import Counter, defaultdict
from pathlib import Path
import ezdxf
from ezdxf.enums import TextEntityAlignment
from ezdxf.path import make_path
from shapely.geometry import Polygon, Point, box
from shapely import affinity
from shapely.ops import unary_union
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent
DXF = OUT / 'hanok_window_A3_one_board_CNC.dxf'
APP = 'HANOK_A3'
R = 3.2
TOOL_R = 3.0
TOL = 1e-7
LAYERS = {
 'BOARD_BOUNDARY':(8,35), 'CUT_THROUGH':(7,35), 'POCKET_10MM':(30,25),
 'DOGBONE':(6,25), 'HINGE_REF':(4,18), 'LATCH_REF':(4,18),
 'PART_ID':(7,18), 'DIMENSIONS':(3,18), 'GRAIN_DIRECTION':(3,35),
 'ASSEMBLY_REFERENCE':(8,18), 'NOTES':(7,18),
}
FAMILIES = {'F01':(463,40,2),'F02':(586,40,2),'S01':(377,30,2),
            'S02':(500,30,2),'L01':(337,10,5),'L02':(460,10,4)}
VX = [143.0 + 75*i for i in range(5)]
HY = [133.4 + 65.4*j for j in range(4)]
PARTS: dict[str,dict] = {}

def tag(e, **d):
    s=json.dumps(d,ensure_ascii=True,separators=(',',':'))
    e.set_xdata(APP, [(1000,s[i:i+240]) for i in range(0,len(s),240)])
    return e

def meta(e):
    if not e.has_xdata(APP): return {}
    return json.loads(''.join(t.value for t in e.get_xdata(APP) if t.code==1000))

def poly(msp, points, layer, **data):
    e=msp.add_lwpolyline(points,format='xy',close=True,dxfattribs={'layer':layer})
    return tag(e,**data) if data else e

def rect(msp,x,y,w,h,layer,**data):
    return poly(msp,[(x,y),(x+w,y),(x+w,y+h),(x,y+h)],layer,**data)

def circle_poly(msp,cx,cy,r,layer,**data):
    # Two exact semicircular bulge segments, not a polygonal circle approximation.
    e=msp.add_lwpolyline([(cx+r,cy,1),(cx-r,cy,1)],format='xyb',close=True,
                         dxfattribs={'layer':layer})
    return tag(e,**data)

def line(msp,a,b,layer='DIMENSIONS',**data):
    e=msp.add_line(a,b,dxfattribs={'layer':layer})
    return tag(e,**data) if data else e

def text(msp,s,p,h=4,layer='NOTES',align='left',rotation=0,**data):
    e=msp.add_text(s,dxfattribs={'layer':layer,'height':h,'rotation':rotation})
    ea = {'left':TextEntityAlignment.MIDDLE_LEFT,
          'center':TextEntityAlignment.MIDDLE_CENTER,
          'right':TextEntityAlignment.MIDDLE_RIGHT}[align]
    e.set_placement(p,align=ea)
    return tag(e,text_align=align,**data)

def dimh(msp,x1,x2,y_obj,y_dim,label=None,detail=None,view=None):
    data={'kind':'dim','detail':detail,'view':view}
    for x in (x1,x2): line(msp,(x,y_obj),(x,y_dim+2 if y_dim>y_obj else y_dim-2),**data)
    line(msp,(x1,y_dim),(x2,y_dim),**data)
    ah=min(3.0,(x2-x1)/5)
    line(msp,(x1,y_dim),(x1+ah,y_dim+ah/2),**data)
    line(msp,(x1,y_dim),(x1+ah,y_dim-ah/2),**data)
    line(msp,(x2,y_dim),(x2-ah,y_dim+ah/2),**data)
    line(msp,(x2,y_dim),(x2-ah,y_dim-ah/2),**data)
    text(msp,label or f'{x2-x1:g}',((x1+x2)/2,y_dim+4),3.6,'DIMENSIONS','center',**data)

def dimv(msp,y1,y2,x_obj,x_dim,label=None,detail=None,view=None):
    data={'kind':'dim','detail':detail,'view':view}
    for y in (y1,y2): line(msp,(x_obj,y),(x_dim+2 if x_dim>x_obj else x_dim-2,y),**data)
    line(msp,(x_dim,y1),(x_dim,y2),**data)
    ah=min(3.0,(y2-y1)/5)
    for y,sg in ((y1,1),(y2,-1)):
        line(msp,(x_dim,y),(x_dim-ah/2,y+sg*ah),**data)
        line(msp,(x_dim,y),(x_dim+ah/2,y+sg*ah),**data)
    text(msp,label or f'{y2-y1:g}',(x_dim+4,(y1+y2)/2),3.6,'DIMENSIONS','center',90,**data)

def entity_polygon(e):
    pts=[(v.x,v.y) for v in make_path(e).flattening(distance=0.00001,segments=64)]
    return Polygon(pts)

def local_rect(p, u,v,w,h, joint,jid,open_edges):
    d={'kind':'pocket','part_id':p['id'],'joint':joint,'joint_id':jid,
       'depth_mm':10.0,'local_rect':[u,v,w,h],'open_edges':open_edges,'machining_face':'A'}
    e=rect(MSP,p['x']+u,p['y']+v,w,h,'POCKET_10MM',**d)
    p['pockets'].append(d)
    return e

def add_receiver(p,u,v,jid):
    local_rect(p,u,v,10,10,'J4',jid,['V_MIN' if v==0 else 'V_MAX'])
    # Dogbone disk centers lie INSIDE the nominal pocket, toward its interior.
    # Each disk reaches the square closed corner exactly and extends 0.9373 mm
    # past its two adjacent nominal edges. Entire disks stay inside sash stock.
    cy=v+10-R/math.sqrt(2) if v==0 else v+R/math.sqrt(2)
    for name,cx in [('LEFT',u+R/math.sqrt(2)),('RIGHT',u+10-R/math.sqrt(2))]:
        circle_poly(MSP,p['x']+cx,p['y']+cy,R,'DOGBONE',
                    kind='dogbone',part_id=p['id'],joint='J4',joint_id=jid,
                    depth_mm=10.0,corner=name,radius_mm=R,local_center=[cx,cy],
                    operation='UNION_WITH_PARENT_POCKET',machining_face='A')

def new_part(pid,x,y,amap,face):
    fam=pid[:3]; L,W,_=FAMILIES[fam]
    p={'id':pid,'family':fam,'length':L,'width':W,'thickness':20,
       'x':x,'y':y,'assembly_map':amap,'assembly_face_A':face,'pockets':[]}
    PARTS[pid]=p
    rect(MSP,x,y,L,W,'CUT_THROUGH',kind='part',part_id=pid,family=fam,
         length_mm=L,width_mm=W,thickness_mm=20,depth_mm=20,
         nesting_origin=[x,y],assembly_map=amap,assembly_face_A=face,
         grain_axis='X',machining_face='A')
    text(MSP,pid,(x+(16 if W==10 else 56),y+W/2),3.2 if W==10 else 4.5,
         'PART_ID',kind='part_id',part_id=pid)
    if W>10:
        text(MSP,f'{L} x {W}  |  A -> {face}',(x+115,y+W/2),3.2,
             kind='part_note',part_id=pid)
    return p

def ends(p,size,jtype,jids):
    local_rect(p,0,0,size,p['width'],jtype,jids[0],['U_MIN','V_MIN','V_MAX'])
    local_rect(p,p['length']-size,0,size,p['width'],jtype,jids[1],['U_MAX','V_MIN','V_MAX'])

def make_parts():
    # All long axes follow board X. A is the same upper board face for all parts.
    for k,y in [(1,20),(2,72)]:
        p=new_part(f'F02-{k}',20,y,[1,0,0,-1,0,40 if k==1 else 463],'BACK')
        ends(p,40,'J1',[f'F_{"B" if k==1 else "T"}L',f'F_{"B" if k==1 else "T"}R'])
        p=new_part(f'F01-{k}',618,y,[0,-1,1,0,40 if k==1 else 586,0],'FRONT')
        ends(p,40,'J1',[f'F_B{"L" if k==1 else "R"}',f'F_T{"L" if k==1 else "R"}'])
    for k,y in [(1,124),(2,166)]:
        p=new_part(f'S02-{k}',20,y,[1,0,0,-1,43,73 if k==1 else 420],'BACK')
        ends(p,30,'J2',[f'S_{"B" if k==1 else "T"}L',f'S_{"B" if k==1 else "T"}R'])
        for i,xc in enumerate(VX,1): add_receiver(p,xc-43-5,0 if k==1 else 20,f'E_V{i}_{"B" if k==1 else "T"}')
        p=new_part(f'S01-{k}',532,y,[0,-1,1,0,73 if k==1 else 543,43],'FRONT')
        ends(p,30,'J2',[f'S_B{"L" if k==1 else "R"}',f'S_T{"L" if k==1 else "R"}'])
        for j,yc in enumerate(HY,1): add_receiver(p,yc-43-5,0 if k==1 else 20,f'E_H{j}_{"L" if k==1 else "R"}')
    for j in range(1,5):
        y=208+(j-1)*22
        p=new_part(f'L02-{j}',20,y,[1,0,0,-1,63,HY[j-1]+5],'BACK')
        ends(p,10,'J4',[f'E_H{j}_L',f'E_H{j}_R'])
        for i,xc in enumerate(VX,1): local_rect(p,xc-63-5,0,10,10,'J3',f'X_{i}_{j}',['V_MIN','V_MAX'])
        p=new_part(f'L01-{j}',492,y,[0,-1,1,0,VX[j-1]+5,63],'FRONT')
        ends(p,10,'J4',[f'E_V{j}_B',f'E_V{j}_T'])
        for k,yc in enumerate(HY,1): local_rect(p,yc-63-5,0,10,10,'J3',f'X_{j}_{k}',['V_MIN','V_MAX'])
    p=new_part('L01-5',841,208,[0,-1,1,0,VX[4]+5,63],'FRONT')
    ends(p,10,'J4',['E_V5_B','E_V5_T'])
    for j,yc in enumerate(HY,1): local_rect(p,yc-63-5,0,10,10,'J3',f'X_5_{j}',['V_MIN','V_MAX'])


def add_hardware():
    # Reference-only front face leaf envelopes. No screw holes / CAM depth assigned.
    for yc in (113,350):
        for pid,u,v in [('F01-1',yc,2),('S01-1',yc-43,13)]:
            p=PARTS[pid]
            rect(MSP,p['x']+u-20,p['y']+v,40,15,'HINGE_REF',
                 kind='hinge_ref',part_id=pid,reference_only=True,
                 length_ref_mm=40,depth_ref_mm=2,face='A_FRONT',center_assembly_y=yc)
    for pid,u,v in [('S01-2',188.5,7),('F01-2',231.5,16)]:
        p=PARTS[pid]
        rect(MSP,p['x']+u-10,p['y']+v,20,16,'LATCH_REF',
             kind='latch_ref',part_id=pid,reference_only=True,depth_ref_mm=None)


def add_board_reference():
    rect(MSP,0,0,1220,900,'BOARD_BOUNDARY',kind='board',size_mm=[1220,900,20])
    text(MSP,'A3 HANOK WINDOW / ONE-BOARD CNC',(0,952),14,kind='title')
    text(MSP,'REV 1  |  mm  |  MODEL SPACE 1:1  |  17 PARTS  |  92 HALF-LAP POCKETS  |  36 RELIEFS',
         (0,928),5.6,kind='subtitle')
    dimh(MSP,0,1220,900,910,'1220',view='nest')
    dimv(MSP,0,900,0,-24,'900',view='nest')
    line(MSP,(130,505),(1090,505),'GRAIN_DIRECTION',kind='grain')
    line(MSP,(1090,505),(1045,526),'GRAIN_DIRECTION',kind='grain')
    line(MSP,(1090,505),(1045,484),'GRAIN_DIRECTION',kind='grain')
    text(MSP,'GRAIN DIRECTION  +X',(610,544),20,'GRAIN_DIRECTION','center',kind='grain')
    text(MSP,'RESERVED OFFCUT - NOT ADDITIONAL PARTS',(610,690),15,align='center',kind='offcut')
    text(MSP,'All 17 parts are nested below. All long axes are parallel to grain.',
         (610,658),9,align='center',kind='offcut')
    notes=[
        'ONE BOARD / 1220 x 900 x 20 / ALL MACHINING FROM COMMON FACE A',
        'ASSEMBLY: F01 + S01 + L01: A FACES FRONT. F02 + S02 + L02: FLIP A TO BACK.',
        'POCKET_10MM + DOGBONE: ADDITIVE REMOVAL, SAME 10 mm DEPTH. UNION IN CAM.',
        'EDGE-OPEN LAPS: ALLOW CUTTER OVERRUN INTO WASTE; DO NOT ROUND THE OPEN SHOULDERS.',
        'HINGE_REF / LATCH_REF ARE NOT PRODUCTION OPERATIONS. HARDWARE NOT SELECTED.',
    ]
    for k,s in enumerate(notes): text(MSP,s,(30,844-k*18),7,kind='board_note')
    for k,s in enumerate([
       'CUT_THROUGH = 20 mm nominal stock profile. No tabs, feeds, speeds or toolpaths are generated.',
       'Nominal fit only: 10.00 / 10.00. Measure stock, test fit, and approve CAM compensation before production.',
       'Small 10 mm lattice strips need an approved hold-down / tabs / onion-skin strategy; pocket first, release last.',
       'Picture support, hinges, handle, catch and wall fixing are purchased non-wood components; not nested.',
       'No weather seal, glazing rebate or exterior structural/window certification is included.'
    ]): text(MSP,s,(0,-35-k*13),5.2,kind='footer_note')


ASSEMBLY_ORIGIN=(1370.0,360.0)

def add_assembly():
    ox,oy=ASSEMBLY_ORIGIN
    text(MSP,'ASSEMBLY REFERENCE / FRONT',(ox,oy+520),11,view='assembly',kind='title')
    text(MSP,'REFERENCE ONLY - never select for CAM',(ox,oy+500),5,view='assembly')
    # The picture is a reference plane behind the lattice, not a machined contour.
    rect(MSP,ox+83,oy+83,420,297,'ASSEMBLY_REFERENCE',
         kind='assembly',role='picture',view='assembly',nominal_size=[420,297])
    # Front-facing vertical members first, then front retained half of horizontal members.
    for pid in sorted(PARTS, key=lambda k:(PARTS[k]['assembly_face_A']=='BACK',k)):
        p=PARTS[pid]
        b=affinity.affine_transform(box(0,0,p['length'],p['width']),p['assembly_map'])
        coords=[(x+ox,y+oy) for x,y in list(b.exterior.coords)[:-1]]
        poly(MSP,coords,'ASSEMBLY_REFERENCE',kind='assembly',role='body',
             part_id=pid,view='assembly',family=p['family'])
    rect(MSP,ox+73,oy+73,440,317,'ASSEMBLY_REFERENCE',
         kind='assembly',role='opening',view='assembly',nominal_size=[440,317])
    # Re-show the thin picture outline above bodies in a different linetype.
    # No duplicate outline entity: the picture entity itself is rendered last by role.
    for yc in (113,350):
        for x in (23,45):
            rect(MSP,ox+x,oy+yc-20,15,40,'HINGE_REF',
                 kind='assembly_hinge',view='assembly',reference_only=True,depth_ref_mm=2)
        line(MSP,(ox+41.5,oy+yc-24),(ox+41.5,oy+yc+24),'HINGE_REF',
             kind='hinge_axis_ref',view='assembly',reference_only=True)
    rect(MSP,ox+520,oy+221.5,16,20,'LATCH_REF',kind='assembly_catch',view='assembly',reference_only=True)
    rect(MSP,ox+554,oy+221.5,16,20,'LATCH_REF',kind='assembly_catch',view='assembly',reference_only=True)
    dimh(MSP,ox,ox+586,oy+463,oy+482,'586',view='assembly')
    dimv(MSP,oy,oy+463,ox+586,ox+612,'463',view='assembly')
    dimh(MSP,ox+43,ox+543,oy+43,oy-18,'500 SASH',view='assembly')
    dimv(MSP,oy+43,oy+420,ox,ox-28,'377 SASH',view='assembly')
    dimh(MSP,ox+73,ox+513,oy+390,oy+443,'440 OPENING',view='assembly')
    dimv(MSP,oy+73,oy+390,ox+513,ox+568,'317 OPENING',view='assembly')
    text(MSP,'A3 420 x 297',(ox+293,oy+101),6,'ASSEMBLY_REFERENCE','center',
         kind='assembly_label',role='picture_label',view='assembly')
    text(MSP,'F02-2',(ox+293,oy+452),4.2,'ASSEMBLY_REFERENCE','center',view='assembly')
    text(MSP,'F02-1',(ox+293,oy+14),4.2,'ASSEMBLY_REFERENCE','center',view='assembly')
    text(MSP,'S02-2',(ox+293,oy+405),4.2,'ASSEMBLY_REFERENCE','center',view='assembly')
    text(MSP,'S02-1',(ox+293,oy+58),4.2,'ASSEMBLY_REFERENCE','center',view='assembly')
    text(MSP,'3 mm clearance on all four sides',(ox+293,oy-38),5,align='center',view='assembly')
    text(MSP,'5 vertical + 4 horizontal bars / 20 crossings / 30 equal clear cells: 65 x 55.4',
         (ox+293,oy-53),4.2,align='center',view='assembly')


def add_details():
    positions={'J1':(1320,100),'J2':(1580,100),'J3':(1320,-110),'J4':(1580,-110)}
    for j,(ox,oy) in positions.items():
        common={'detail':j,'view':'detail'}
        def tx(s,x,y,h=3.8,align='left',layer='NOTES'):
            return text(MSP,s,(ox+x,oy+y),h,layer,align,**common)
        def rr(x,y,w,h,role='body',**kw):
            return rect(MSP,ox+x,oy+y,w,h,'ASSEMBLY_REFERENCE',role=role,**common,**kw)
        def pp(pts,role='body',**kw):
            return poly(MSP,[(ox+x,oy+y) for x,y in pts],'ASSEMBLY_REFERENCE',role=role,**common,**kw)
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
            tx('20 crossings x 2 matching pockets = 40 pockets',15,95,4.2)
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
            rr(45,107,10,10,'pocket');rr(135,117,10,10,'pocket')
            for cx in (45+R/math.sqrt(2),55-R/math.sqrt(2)):
                circle_poly(MSP,ox+cx,oy+117-R/math.sqrt(2),R,'ASSEMBLY_REFERENCE',
                            role='dogbone',**common,radius_mm=R)
            dimh(MSP,ox+45,ox+55,oy+107,oy+94,'10',detail=j)
            dimv(MSP,oy+107,oy+117,ox+55,ox+69,'10',detail=j)
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
            tx('S01 + L02 is the face-reversed equivalent. 18 end joints total.',10,18,3.4)
        tx('REFERENCE ONLY / DXF 1:1 / PNG enlarged',10,7,3.2)
    return positions


def build():
    global DOC,MSP
    DOC=ezdxf.new('R2010',setup=False)
    DOC.units=ezdxf.units.MM
    DOC.header['$MEASUREMENT']=1
    DOC.header['$LUNITS']=2;DOC.header['$LUPREC']=3
    DOC.header['$INSBASE']=(0,0,0)
    DOC.header['$LWDISPLAY']=True
    DOC.appids.new(APP)
    for name,(color,lw) in LAYERS.items():
        DOC.layers.new(name,dxfattribs={'color':color,'lineweight':lw})
    # Reference layers are dashed; units are millimetres.
    DOC.linetypes.new('REF_DASH',dxfattribs={'description':'Reference only 4-2', 'pattern':[6,4,-2]})
    DOC.linetypes.new('A3_DASHDOT',dxfattribs={'description':'A3 placement 8-2-1-2','pattern':[13,8,-2,1,-2]})
    for name in ('HINGE_REF','LATCH_REF'):
        DOC.layers.get(name).dxf.linetype='REF_DASH'
    MSP=DOC.modelspace()
    make_parts();add_hardware();add_board_reference();add_assembly()
    detail_positions=add_details()
    for e in MSP:
        d=meta(e)
        if d.get('role')=='picture':e.dxf.linetype='A3_DASHDOT'
        if d.get('role')=='opening':e.dxf.linetype='REF_DASH'
    DOC.set_modelspace_vport(height=1090,center=(1000,415))
    # Mandatory validation before publishing and independent re-read afterwards.
    report_pre=validate(DOC, phase='IN_MEMORY_BEFORE_SAVE')
    tmp=OUT/'_validated_candidate.dxf'
    DOC.saveas(tmp)
    reread=ezdxf.readfile(tmp)
    report=validate(reread, phase='READ_BACK_FROM_SAVED_DXF')
    tmp.replace(DXF)
    report['file']=DXF.name
    report['sha256']=hashlib.sha256(DXF.read_bytes()).hexdigest()
    report['pre_save_validation']='PASS'
    report['ezdxf_version']=ezdxf.__version__
    report['schema_note']='All machining geometry is in Model Space; no CAM toolpaths.'
    (OUT/'validation_report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    write_csv(reread)
    return reread,report,detail_positions


def validate(doc,phase):
    msp=doc.modelspace(); errors=[]; checks=[]
    def check(name,ok,detail):
        checks.append({'check':name,'status':'PASS' if ok else 'FAIL','detail':detail})
        if not ok:errors.append(name)
    all_ents=list(msp)
    parts={meta(e).get('part_id'):e for e in all_ents if e.dxf.layer=='CUT_THROUGH'}
    pockets=[e for e in all_ents if e.dxf.layer=='POCKET_10MM']
    dogs=[e for e in all_ents if e.dxf.layer=='DOGBONE']
    counts=Counter(meta(e).get('family') for e in parts.values())
    for fam,(_,_,n) in FAMILIES.items():check(f'{fam}_quantity',counts[fam]==n,{'actual':counts[fam],'required':n})
    ps={pid:entity_polygon(e) for pid,e in parts.items()}
    board=box(0,0,1220,900)
    check('07_inside_board',all(board.covers(p) for p in ps.values()),'Every CUT_THROUGH lies inside 1220 x 900.')
    pairs=list(itertools.combinations(ps,2))
    overlap=max((ps[a].intersection(ps[b]).area for a,b in pairs),default=0)
    check('08_no_nesting_overlap',overlap<TOL,{'maximum_overlap_area_mm2':overlap})
    gap=min(ps[a].distance(ps[b]) for a,b in pairs)
    margin=min(min(p.bounds[0],p.bounds[1],1220-p.bounds[2],900-p.bounds[3]) for p in ps.values())
    check('09_nesting_spacing',gap>=12-TOL and margin>=20-TOL,{'minimum_gap_mm':gap,'minimum_board_margin_mm':margin})
    grouped=defaultdict(list)
    bypart=defaultdict(list)
    byjoint=Counter()
    for e in pockets:
        d=meta(e);grouped[d['joint_id']].append(e);bypart[d['part_id']].append(e);byjoint[d['joint']]+=1
    check('10_J1_all_ends',byjoint['J1']==8 and all(sum(meta(e)['joint']=='J1' for e in bypart[p])==2 for p in parts if p.startswith('F')),{'pockets':byjoint['J1'],'mated_corners':4})
    check('11_J2_all_ends',byjoint['J2']==8 and all(sum(meta(e)['joint']=='J2' for e in bypart[p])==2 for p in parts if p.startswith('S')),{'pockets':byjoint['J2'],'mated_corners':4})
    okcross=byjoint['J3']==40 and all(sum(meta(e)['joint']=='J3' for e in bypart[p])==(4 if p.startswith('L01') else 5) for p in parts if p.startswith('L'))
    check('12_J3_all_crossings',okcross,{'pockets':byjoint['J3'],'crossings':20})
    check('13_S02_five_J4_seats_each',all(sum(meta(e)['joint']=='J4' for e in bypart[p])==5 for p in parts if p.startswith('S02')),{'S02-1':5,'S02-2':5})
    check('14_S01_four_J4_seats_each',all(sum(meta(e)['joint']=='J4' for e in bypart[p])==4 for p in parts if p.startswith('S01')),{'S01-1':4,'S01-2':4})
    dogs_by_joint=defaultdict(list)
    for e in dogs:dogs_by_joint[meta(e)['joint_id']].append(e)
    receivers=[e for e in pockets if meta(e)['joint']=='J4' and meta(e)['part_id'].startswith('S')]
    dog_ok=len(dogs)==36
    for e in receivers:
        d=meta(e);dr=dogs_by_joint[d['joint_id']]
        dog_ok &= len(dr)==2 and all(meta(x)['part_id']==d['part_id'] and abs(meta(x)['radius_mm']-R)<TOL for x in dr)
        u,v,w,h=d['local_rect'];closed_v=v+10 if v==0 else v
        for de in dr:
            dd=meta(de);cx,cy=dd['local_center'];cornerx=u if dd['corner']=='LEFT' else u+10
            dog_ok &= abs(math.hypot(cx-cornerx,cy-closed_v)-R)<1e-8
            # Exact DXF circle representation must have two +1 bulges.
            dog_ok &= de.dxftype()=='LWPOLYLINE' and len(de)==2 and all(abs(vt[4]-1)<TOL for vt in de)
    check('15_required_dogbones',bool(dog_ok),{'circles':len(dogs),'receiving_seats':len(receivers),'radius_mm':R,'tool_radius_mm':TOOL_R})
    allinside=True
    for e in pockets+dogs:
        d=meta(e);allinside &= ps[d['part_id']].buffer(TOL).covers(entity_polygon(e))
    check('16_pockets_and_reliefs_inside_own_part',bool(allinside),{'nominal_pockets':len(pockets),'reliefs':len(dogs),'outside_area_allowed_mm2':0})
    check('17_layers_separate',all(meta(e)['depth_mm']==20 for e in parts.values()) and all(meta(e)['depth_mm']==10 for e in pockets+dogs),{'CUT_THROUGH':20,'POCKET_10MM':10,'DOGBONE':10,'hardware':'REFERENCE ONLY'})
    check('18_A3_fits_aperture',box(73,73,513,390).covers(box(83,83,503,380)),{'picture_mm':[420,297],'aperture_mm':[440,317],'margins_each_mm':10})
    mach=list(parts.values())+pockets+dogs
    check('closed_valid_machining_profiles',all(e.dxftype()=='LWPOLYLINE' and e.closed and entity_polygon(e).is_valid and entity_polygon(e).area>0 for e in mach),{'profiles':len(mach),'open':sum(not e.closed for e in mach)})
    keys=[entity_polygon(e).normalize().wkb for e in mach]
    check('no_duplicate_complete_machining_contours',len(keys)==len(set(keys)),{'duplicates':len(keys)-len(set(keys)),'note':'A shared boundary between different depth operations is intentional, not a duplicate contour.'})
    check('mm_modelspace_no_toolpaths',doc.units==4 and len(doc.paperspace())==0 and all(e.dxf.elevation==0 for e in mach),{'INSUNITS':doc.units,'paperspace_entities':len(doc.paperspace()),'machining_elevation_mm':0})
    expected_area=sum(L*W*n for L,W,n in FAMILIES.values())
    check('exact_part_sizes_and_grain',all(abs(p.area-meta(parts[pid])['length_mm']*meta(parts[pid])['width_mm'])<TOL and abs(p.bounds[2]-p.bounds[0]-meta(parts[pid])['length_mm'])<TOL for pid,p in ps.items()),{'total_blank_area_mm2':expected_area,'all_long_axes':'X'})
    ids=[meta(e)['part_id'] for e in all_ents if e.dxf.layer=='PART_ID']
    check('unique_annotation_ID_per_part',Counter(ids)==Counter({p:1 for p in parts}),{'count':len(ids)})
    check('L01_L02_end_laps',all(sum(meta(e)['joint']=='J4' for e in bypart[p])==2 for p in parts if p.startswith('L')),{'end_laps':18})
    # Independent 2D assembly registration and 2-slab (0..10, 10..20) solid audit.
    def in_assembly(pid,geometry):
        d=meta(parts[pid]);x,y=d['nesting_origin']
        return affinity.affine_transform(affinity.translate(geometry,-x,-y),d['assembly_map'])
    ap={p:in_assembly(p,g) for p,g in ps.items()}
    ref_match=True;ref_count=0
    for e in all_ents:
        md=meta(e)
        if md.get('kind') not in ('hinge_ref','latch_ref'):continue
        ga=in_assembly(md['part_id'],entity_polygon(e))
        matches=[entity_polygon(a) for a in all_ents
                 if meta(a).get('view')=='assembly' and a.dxf.layer==e.dxf.layer
                 and a.dxftype()=='LWPOLYLINE']
        matches=[affinity.translate(a,-ASSEMBLY_ORIGIN[0],-ASSEMBLY_ORIGIN[1]) for a in matches]
        ref_match &= any(ga.symmetric_difference(a).area<1e-6 for a in matches)
        ref_count+=1
    check('reference_hardware_nesting_matches_assembly',bool(ref_match) and ref_count==6,
          {'matching_reference_envelopes':ref_count,'status_limit':'Position envelopes only; not selected hardware or production machining.'})
    max_match=0;match_ok=len(grouped)==46
    for jid,ents in grouped.items():
        if len(ents)!=2: match_ok=False;continue
        a,b=ents;da,db=meta(a),meta(b)
        ga=in_assembly(da['part_id'],entity_polygon(a));gb=in_assembly(db['part_id'],entity_polygon(b))
        err=ga.symmetric_difference(gb).area;max_match=max(max_match,err)
        match_ok &= err<1e-6
        match_ok &= {meta(parts[da['part_id']])['assembly_face_A'],meta(parts[db['part_id']])['assembly_face_A']}=={'FRONT','BACK'}
        match_ok &= ap[da['part_id']].intersection(ap[db['part_id']]).symmetric_difference(ga).area<1e-6
    check('all_46_joint_pairs_register_on_opposite_faces',bool(match_ok),{'joint_pairs':len(grouped),'maximum_pocket_mismatch_area_mm2':max_match})
    solids={}
    for pid in parts:
        removals=[in_assembly(pid,entity_polygon(e)) for e in pockets+dogs if meta(e)['part_id']==pid]
        removed=unary_union(removals)
        full=ap[pid];milled=full.difference(removed)
        solids[pid]=[full,milled] if meta(parts[pid])['assembly_face_A']=='FRONT' else [milled,full]
    max_volume=0
    for a,b in itertools.combinations(parts,2):
        volume=sum(solids[a][i].intersection(solids[b][i]).area*10 for i in (0,1))
        max_volume=max(max_volume,volume)
    check('assembled_solid_no_interpenetration',max_volume<1e-5,{'maximum_intersection_volume_mm3':max_volume,'method':'Two exact depth slabs: z=0..10 and z=10..20; dogbone arcs tessellated at 0.00001 mm sag.'})
    check('finished_frame_sash_aperture',
          unary_union([ap[p] for p in ap if p.startswith('F')]).bounds==(0,0,586,463)
          and unary_union([ap[p] for p in ap if p.startswith('S')]).bounds==(43,43,543,420),
          {'frame_outer':[586,463],'frame_inner':[506,383],'sash':[500,377],'clearance_mm':3,'aperture':[440,317]})
    # With front normal +Z and a provisional front-projecting hinge axis, the
    # closed sash envelope opens through 90 degrees without entering fixed wood.
    # This checks an explicitly provisional axis, NOT any unselected hinge model.
    fixed_xz=unary_union([box(0,0,40,20),box(546,0,586,20)])
    closed_sash_xz=box(43,0,543,20)
    sweep_area=0.0
    for k in range(901):
        swung=affinity.rotate(closed_sash_xz,k/10,origin=(41.5,24),use_radians=False)
        sweep_area=max(sweep_area,swung.intersection(fixed_xz).area)
    check('provisional_hinge_axis_0_to_90_deg_sweep',sweep_area<TOL,
          {'axis_x_mm':41.5,'axis_z_mm':24,'angle_step_deg':0.1,'max_collision_area_mm2':sweep_area,
           'status_limit':'Reference axis only. Recheck actual hinge offset, knuckle, screws, catch and backer.'})
    audit=doc.audit()
    check('DXF_audit',not audit.has_errors and not audit.has_fixes,{'errors':len(audit.errors),'fixes':len(audit.fixes)})
    if errors:raise AssertionError('VALIDATION FAILED: '+', '.join(errors))
    return {'status':'PASS','phase':phase,'checks_passed':len(checks),'checks':checks,
            'part_counts':dict(counts),'parts_total':len(parts),'pocket_counts':dict(byjoint),
            'nominal_pockets_total':len(pockets),'dogbone_reliefs_total':len(dogs),
            'machining_profiles_total':len(mach),'mated_joints_total':len(grouped),
            'minimum_part_gap_mm':gap,'minimum_board_margin_mm':margin,
            'nesting_bounds_mm':list(unary_union(list(ps.values())).bounds),
            'board_mm':[1220,900,20],'net_blank_area_mm2':expected_area,
            'board_area_utilization_percent':round(expected_area/(1220*900)*100,3),
            'limitations':['Nominal zero-clearance fit; physical fit test required.',
                'Hardware, picture backing and hold-down are not finalized.',
                'No G-code, feeds/speeds, stock flatness, strength or physical prototype validation.']}


def write_csv(doc):
    fields=['part_id','joint','joint_id','u_start_mm','v_start_mm','length_u_mm','width_v_mm',
            'depth_mm','assembly_face_A','open_edges','dogbone_count','dxf_handle']
    partdata={meta(e)['part_id']:meta(e) for e in doc.modelspace() if e.dxf.layer=='CUT_THROUGH'}
    ds=Counter((meta(e)['part_id'],meta(e)['joint_id']) for e in doc.modelspace() if e.dxf.layer=='DOGBONE')
    with (OUT/'pocket_schedule.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for e in doc.modelspace():
            if e.dxf.layer!='POCKET_10MM':continue
            d=meta(e);u,v,l,h=d['local_rect']
            w.writerow(dict(part_id=d['part_id'],joint=d['joint'],joint_id=d['joint_id'],
                  u_start_mm=round(u,6),v_start_mm=round(v,6),length_u_mm=l,width_v_mm=h,
                  depth_mm=10,assembly_face_A=partdata[d['part_id']]['assembly_face_A'],
                  open_edges=';'.join(d['open_edges']),dogbone_count=ds[(d['part_id'],d['joint_id'])],
                  dxf_handle=e.dxf.handle))
    with (OUT/'part_schedule.csv').open('w',encoding='utf-8-sig',newline='') as f:
        fields=['part_id','length_mm','width_mm','thickness_mm','nesting_x_mm','nesting_y_mm',
                'assembly_face_A','pocket_count','grain_axis']
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for pid,d in sorted(partdata.items()):
            w.writerow(dict(part_id=pid,length_mm=d['length_mm'],width_mm=d['width_mm'],
                  thickness_mm=20,nesting_x_mm=d['nesting_origin'][0],nesting_y_mm=d['nesting_origin'][1],
                  assembly_face_A=d['assembly_face_A'],pocket_count=sum(meta(e).get('part_id')==pid and e.dxf.layer=='POCKET_10MM' for e in doc.modelspace()),grain_axis='X'))

# Rendering / documentation functions are appended below.

# Exact DXF-derived raster rendering (not an AI rendering or a CAM toolpath).
COL={
 'ink':'#202D3A','muted':'#667583','line':'#51606B','border':'#D9E0E4',
 'wood':'#F3EADD','wooddark':'#E6D3BB','pocket':'#F3BF68','pocketline':'#9E6118',
 'dog':'#CB67A0','dogline':'#912F68','hardware':'#527E8C','grain':'#38685B',
 'front':'#B4D2DB','back':'#CFDDD0','paper':'#FCFBF6','opening':'#46796C',
 'picture':'#735C9B','panel':'#F5F7F8','white':'#FFFFFF',
}
FONT_REG='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONT_BOLD='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
FONT_MONO='/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'

def font(size,bold=False,mono=False):
    return ImageFont.truetype(FONT_MONO if mono else FONT_BOLD if bold else FONT_REG,max(6,int(size)))

def label(draw,xy,s,size=28,fill=None,bold=False,anchor='la',mono=False):
    draw.text(xy,str(s),font=font(size,bold,mono),fill=fill or COL['ink'],anchor=anchor)

def wrapped(draw,s,xy,width,size=28,fill=None,linegap=1.5,bold=False):
    x,y=xy;f=font(size,bold)
    words=s.split();row=''
    for w in words:
        t=row+' '+w if row else w
        if draw.textlength(t,font=f)>width and row:
            draw.text((x,y),row,font=f,fill=fill or COL['ink']);y+=int(size*linegap);row=w
        else:row=t
    if row:draw.text((x,y),row,font=f,fill=fill or COL['ink']);y+=int(size*linegap)
    return y

class Renderer:
    def __init__(self,image,bounds,viewport):
        self.im=image;self.d=ImageDraw.Draw(image)
        self.x0,self.y0,self.x1,self.y1=bounds
        x,y,w,h=viewport
        self.s=min(w/(self.x1-self.x0),h/(self.y1-self.y0))
        self.left=x+(w-(self.x1-self.x0)*self.s)/2
        self.top=y+(h-(self.y1-self.y0)*self.s)/2
    def pt(self,p):
        return (self.left+(p[0]-self.x0)*self.s,self.top+(self.y1-p[1])*self.s)
    def dashed(self,pts,fill,width=2,dash=(12,7),close=False):
        pp=list(pts)+(list(pts[:1]) if close else [])
        for a,b in zip(pp,pp[1:]):
            dx=b[0]-a[0];dy=b[1]-a[1];L=math.hypot(dx,dy)
            if L==0:continue
            pos=0;k=0
            while pos<L:
                n=min(L,pos+dash[k%len(dash)])
                if k%2==0:self.d.line([(a[0]+dx*pos/L,a[1]+dy*pos/L),(a[0]+dx*n/L,a[1]+dy*n/L)],fill=fill,width=width)
                pos=n;k+=1
    def entity(self,e):
        data=meta(e);layer=e.dxf.layer;role=data.get('role','')
        stroke=COL['line'];fill=None;lw=max(1,round(self.s*.35));dashed=False
        if layer=='CUT_THROUGH' or role=='body':fill=COL['wood'];stroke=COL['ink'];lw=max(2,round(self.s*.45))
        if layer=='POCKET_10MM' or role=='pocket':fill=COL['pocket'];stroke=COL['pocketline'];lw=max(2,round(self.s*.35))
        if layer=='DOGBONE' or role=='dogbone':fill=COL['dog'];stroke=COL['dogline'];lw=max(1,round(self.s*.28))
        if layer in ('HINGE_REF','LATCH_REF'):stroke=COL['hardware'];dashed=True;lw=max(2,round(self.s*.4))
        if role=='section_front':fill=COL['front'];stroke=COL['ink'];lw=max(2,round(self.s*.35))
        if role=='section_back':fill=COL['back'];stroke=COL['ink'];lw=max(2,round(self.s*.35))
        if role=='picture':fill=COL['paper'];stroke=COL['picture'];dashed=True;lw=max(2,round(self.s*.55))
        if role=='opening':stroke=COL['opening'];dashed=True;lw=max(2,round(self.s*.45))
        if layer=='GRAIN_DIRECTION':stroke=COL['grain'];lw=max(3,round(self.s*1.1))
        if layer=='BOARD_BOUNDARY':fill=COL['paper'];stroke=COL['ink'];lw=max(3,round(self.s*.75))
        if layer=='DIMENSIONS':stroke=COL['muted'];lw=max(1,round(self.s*.25))
        if data.get('kind')=='detail_border':stroke=COL['border'];fill=None;lw=2
        if e.dxftype()=='LWPOLYLINE':
            pts=[self.pt((v.x,v.y)) for v in make_path(e).flattening(distance=.003,segments=16)]
            if fill:self.d.polygon(pts,fill=fill)
            if dashed:self.dashed(pts,stroke,lw,close=e.closed)
            else:self.d.line(pts+([pts[0]] if e.closed else []),fill=stroke,width=lw,joint='curve')
        elif e.dxftype()=='LINE':
            pts=[self.pt(e.dxf.start),self.pt(e.dxf.end)]
            if dashed:self.dashed(pts,stroke,lw)
            else:self.d.line(pts,fill=stroke,width=lw)
        elif e.dxftype()=='TEXT':
            pos=e.dxf.align_point if e.dxf.halign or e.dxf.valign else e.dxf.insert
            p=self.pt(pos)
            h=max(8,e.dxf.height*self.s*1.25)
            align=data.get('text_align','left');anchor={'center':'mm','left':'lm','right':'rm'}[align]
            fc=COL['grain'] if layer=='GRAIN_DIRECTION' else COL['muted'] if layer=='DIMENSIONS' else COL['ink']
            if role=='picture_label':fc=COL['picture']
            f=font(h,bold=(data.get('kind') in ('title','part_id')))
            if abs(e.dxf.rotation-90)<.01:
                bbox=f.getbbox(e.dxf.text)
                tw=bbox[2]-bbox[0]+10;th=bbox[3]-bbox[1]+12
                ti=Image.new('RGBA',(tw,th),(255,255,255,0));td=ImageDraw.Draw(ti)
                td.text((5-bbox[0],6-bbox[1]),e.dxf.text,font=f,fill=fc)
                ti=ti.rotate(90,expand=True)
                self.im.paste(ti,(round(p[0]-ti.width/2),round(p[1]-ti.height/2)),ti)
            else:self.d.text(p,e.dxf.text,font=f,fill=fc,anchor=anchor)
    def entities(self,ents):
        for e in ents:self.entity(e)

def nest_entities(doc,include_board=True):
    m=list(doc.modelspace())
    out=[]
    if include_board:out.extend(e for e in m if e.dxf.layer=='BOARD_BOUNDARY')
    for lay in ('CUT_THROUGH','POCKET_10MM','DOGBONE','HINGE_REF','LATCH_REF','PART_ID'):
        out.extend(e for e in m if e.dxf.layer==lay and meta(e).get('view')!='assembly')
    out.extend(e for e in m if meta(e).get('kind')=='part_note')
    if include_board:
        out.extend(e for e in m if e.dxf.layer=='GRAIN_DIRECTION' or meta(e).get('kind')=='offcut' or meta(e).get('view')=='nest')
    return out

def render_nesting(doc,report):
    im=Image.new('RGB',(4400,3950),COL['white']);d=ImageDraw.Draw(im)
    label(d,(125,65),'01  ONE-BOARD NESTING',65,bold=True)
    label(d,(125,154),'1220 x 900 x 20 mm  |  Common machining face A  |  All long axes follow +X grain',30,fill=COL['muted'])
    d.line((125,219,4275,219),fill=COL['border'],width=3)
    r=Renderer(im,(-45,-10,1240,925),(90,275,2990,2210))
    r.entities(nest_entities(doc,True))
    # Sidebar is annotation only, not another instance of CAD machining geometry.
    x=3200;y=300;sw=990
    label(d,(x,y),'VERIFIED DXF GEOMETRY',33,bold=True);y+=75
    for val,ttl in [('17','independent wood parts'),('92','closed nominal pocket contours'),('36','R3.2 dogbone relief circles'),('46','registered mating joint pairs')]:
        label(d,(x,y),val,69,bold=True)
        label(d,(x+145,y+24),ttl,26)
        y+=115
    y+=20
    d.line((x,y,x+sw,y),fill=COL['border'],width=3);y+=45
    label(d,(x,y),'MACHINING LAYERS',30,bold=True);y+=68
    for c,name,desc in [(COL['wood'],'CUT_THROUGH','20 mm nominal stock profile'),
                         (COL['pocket'],'POCKET_10MM','10 mm depth from common face A'),
                         (COL['dog'],'DOGBONE','10 mm depth; union with parent seat'),
                         (COL['hardware'],'HINGE_REF / LATCH_REF','Reference only. Do not machine.')]:
        d.rectangle((x,y+3,x+38,y+38),fill=c,outline=COL['line'],width=2)
        label(d,(x+59,y),name,27,bold=True)
        label(d,(x+59,y+42),desc,24,fill=COL['muted']);y+=112
    y+=30
    label(d,(x,y),'ASSEMBLY FACE SCHEDULE',30,bold=True);y+=62
    y=wrapped(d,'F01 / S01 / L01: machined face A points toward the front.',(x,y),sw,28);y+=24
    y=wrapped(d,'F02 / S02 / L02: flip after cutting; machined face A points toward the back.',(x,y),sw,28);y+=35
    d.line((x,y,x+sw,y),fill=COL['border'],width=3);y+=40
    label(d,(x,y),'LAYOUT CHECK',30,bold=True);y+=65
    for s in ['Minimum part gap: 12 mm','Minimum board edge margin: 20 mm',
              'Cut-part envelope: x 20-1178 / y 20-284',
              '10 mm slots are nominal; fit-test first.',
              'Open-edge laps need cutter overrun in CAM.',
              'No tabs, feeds, speeds or toolpaths included.']:
        y=wrapped(d,s,(x,y),sw,25);y+=16
    label(d,(125,2580),'CUT-ZONE ENLARGEMENT',45,bold=True)
    label(d,(125,2650),'The same 17 parts, enlarged below; not additional parts. Every pocket and relief is read back from the saved DXF.',27,fill=COL['muted'])
    d.rounded_rectangle((105,2715,4290,3740),radius=18,fill=COL['panel'],outline=COL['border'],width=2)
    rr=Renderer(im,(0,0,1220,300),(130,2730,4120,995));rr.entities(nest_entities(doc,False))
    label(d,(130,3795),'NOMINAL WOOD GEOMETRY VERIFIED  |  Hardware, CAM work-holding and physical fit require approval before cutting.',26,fill=COL['muted'])
    im.save(OUT/'01_one_board_nesting.png',dpi=(220,220))
    return im

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

def render_assembly(doc):
    im=Image.new('RGB',(4000,3300),COL['white']);d=ImageDraw.Draw(im)
    label(d,(115,60),'03  ASSEMBLY REFERENCE',65,bold=True)
    label(d,(115,150),'Front elevation  |  586 x 463 overall  |  500 x 377 sash  |  A3 landscape behind the opening grille',30,fill=COL['muted'])
    d.line((115,215,3885,215),fill=COL['border'],width=3)
    ox,oy=ASSEMBLY_ORIGIN
    r=Renderer(im,(ox-48,oy-62,ox+642,oy+495),(100,280,3010,2450))
    ents=[e for e in doc.modelspace() if meta(e).get('view')=='assembly' and meta(e).get('kind')!='title'
          and not (e.dxftype()=='TEXT' and e.dxf.text.startswith('REFERENCE ONLY'))]
    # Paper behind the wooden grille. Its placement outline and the aperture
    # boundary remain distinguishable. No duplicate DXF outline is introduced.
    pictures=[e for e in ents if meta(e).get('role')=='picture']
    r.entities(pictures)
    r.entities([e for e in ents if meta(e).get('role')=='body'])
    r.entities([e for e in ents if meta(e).get('role') not in ('body','picture')])
    x=3190;y=335;w=690
    label(d,(x,y),'DESIGN GEOMETRY',32,bold=True);y+=73
    for ttl,body in [('A3 PICTURE','420 x 297 mm, centered; 10 mm clear border on every side.'),
                     ('EFFECTIVE OPENING','440 x 317 mm before grille subdivision.'),
                     ('GRILLE','5 vertical / 4 horizontal members. 20 flush half-lap crossings.'),
                     ('SASH CLEARANCE','3 mm on all four sides inside the 506 x 383 fixed-frame opening.')]:
        label(d,(x,y),ttl,26,bold=True);y+=44
        y=wrapped(d,body,(x,y),w,27);y+=45
    d.line((x,y,x+w,y),fill=COL['border'],width=3);y+=40
    label(d,(x,y),'HARDWARE IS REFERENCE',28,bold=True);y+=65
    y=wrapped(d,'Two left-side front-face hinge envelopes: 40 mm long; 2 mm depth reference only.',(x,y),w,26);y+=25
    y=wrapped(d,'Choose the hinge model and verify pin offset, leaf thickness, screw positions and opening sweep before machining.',(x,y),w,26);y+=38
    y=wrapped(d,'Right-side handle and catch are location references only.',(x,y),w,26);y+=35
    d.line((x,y,x+w,y),fill=COL['border'],width=3);y+=40
    label(d,(x,y),'PICTURE RETENTION',28,bold=True);y+=60
    y=wrapped(d,'Provide a separate non-wood backing/support behind the fixed frame. The 17 wood parts alone do not hold the artwork.',(x,y),w,26)
    # Add short face labels and the actual line convention below the front view.
    d.rounded_rectangle((120,2840,3880,3165),radius=20,fill=COL['panel'],outline=COL['border'],width=2)
    label(d,(170,2890),'ASSEMBLY ORIENTATION',32,bold=True)
    label(d,(170,2955),'F01 / S01 / L01: A -> FRONT',31)
    label(d,(170,3018),'F02 / S02 / L02: A -> BACK (flip after cutting)',31)
    d.line((2130,2920,2280,2920),fill=COL['opening'],width=5)
    label(d,(2310,2900),'440 x 317 opening reference',28)
    d.line((2130,2985,2170,2985),fill=COL['picture'],width=5)
    d.line((2200,2985,2215,2985),fill=COL['picture'],width=5)
    d.line((2240,2985,2280,2985),fill=COL['picture'],width=5)
    label(d,(2310,2965),'420 x 297 A3 placement reference',28)
    label(d,(2130,3040),'This sheet contains no manufacturing toolpaths.',26,fill=COL['muted'])
    label(d,(120,3210),'All wooden bodies are transformed from the independently identified, verified DXF part geometry.',27,fill=COL['muted'])
    im.save(OUT/'03_assembly_reference.png',dpi=(220,220));return im


def write_readme(report):
    # UTF-8 documentation; no bundled font binaries.
    s=f'''A3 한식 창호 — One-Board CNC 제작도
Revision 1 / 2026-09-10 / 단위 mm / DXF R2010 (AC1024)
======================================================================

0. 파일의 용도와 검증 범위
------------------------
이 패키지는 실내용 장식 창호/개폐식 그림 프레임의 명목 치수 제작도입니다.
렌더링만 있는 자료가 아닙니다. 17개 목재 부품 외곽, 92개 결합 pocket,
36개 dog-bone이 Model Space의 실제 closed LWPOLYLINE geometry입니다.
모든 CNC 형상은 1:1, XY 평면 Z=0, mm 단위입니다. Z 좌표로 깊이를 표현하지
않으며 가공 깊이는 layer와 XDATA에 별도로 지정됩니다.

검증: 메모리상의 도면 검증 -> 임시 DXF 저장 -> ezdxf로 다시 읽기 -> 독립
검증 -> 최종 파일 확정 -> 저장된 DXF에서 PNG 렌더링 순서입니다.
프로그램 검증 {report['checks_passed']}개 모두 PASS. 실제 목재 절삭, 물성/강도 시험,
실물 경첩 시험 또는 CAM 시뮬레이션을 완료했다는 의미는 아닙니다.
사용자는 반드시 CAM 작업, 공차와 하드웨어를 승인한 뒤 제작해야 합니다.

1. 패키지 파일
--------------
hanok_window_A3_one_board_CNC.dxf  편집 가능한 주 제작도
01_one_board_nesting.png          전체 원판 + 동일 절삭 구역 확대
02_joinery_details.png            J1/J2/J3/J4 확대 참고도
03_assembly_reference.png         정면 조립도와 A3 위치
README.txt                       본 제작/조립 설명
validation_report.json           저장 후 DXF 재검증 결과와 SHA-256
part_schedule.csv                17개 부품 치수, 배치 및 조립면 표
pocket_schedule.csv              92개 pocket 좌표, 짝 ID 및 개방 경계 표
build_hanok_window.py             재생성 및 독립 검증용 Python 소스

2. 재료 / 치수
--------------
원판: 1220 x 900 x 20; 모든 부품의 완성 두께 20.00.
원판 상면의 동일 면을 A라고 정합니다. 반대편은 B입니다.
나뭇결은 X축(1220 방향); 17개 부품 모두 길이축이 X와 평행합니다.
원판 가장자리 여유 최솟값 20.00; 부품 외곽 간 거리 최솟값 12.00.
실제 부품의 전체 배치 범위: X=20~1178, Y=20~284.
원판의 나머지 부분은 자투리 보존 영역이며 추가 부품이 아닙니다.
기본 공구: 평면 끝 Ø6 end mill, 반지름 3; relief 기준 반지름 R3.2.
수종/함수율/결함/평탄도/가공물 고정은 별도 확인 대상입니다.
20 mm는 최종 정삭 후 실제 두께입니다. 두께가 다르면 T/2 깊이로 모든
대응 부품을 함께 재설계/보정해야 하며, 10 mm만 그대로 사용하면 안 됩니다.

A3 그림 420 x 297, 유효 개구부 440 x 317, 각 변 여백 10.
창짝 외곽 500 x 377; 테두리 정면 폭 30.
고정틀 외곽 586 x 463; 정면 폭 40; 내부 구멍 506 x 383.
창짝-고정틀 간극 각 변 3. 정면에서 기준 원점은 완성 창호 좌하단입니다.
유효 개구부는 격자를 넣기 전의 외곽 개구 치수이며, 한 칸 치수가 아닙니다.
세로 창살 5개, 가로 창살 4개. 각 칸의 순수 개구는 65 x 55.4, 총 30칸.

3. 부품표 — L x W x T, mm
-------------------------
F01  463 x 40 x 20   2개: F01-1 왼쪽, F01-2 오른쪽 고정틀 세로재
F02  586 x 40 x 20   2개: F02-1 아래, F02-2 위 고정틀 가로재
S01  377 x 30 x 20   2개: S01-1 왼쪽, S01-2 오른쪽 창짝 세로재
S02  500 x 30 x 20   2개: S02-1 아래, S02-2 위 창짝 가로재
L01  337 x 10 x 20   5개: L01-1~5 정면에서 왼쪽 -> 오른쪽
L02  460 x 10 x 20   4개: L02-1~4 정면에서 아래 -> 위
합계 17개. Part ID는 PART_ID layer의 annotation이며 각인 가공이 아닙니다.

부품별 pocket 수:
F01 각각 J1 2개; F02 각각 J1 2개 -> J1 합계 8.
S01 각각 J2 2개 + J4 4개 = 6; S02 각각 J2 2개 + J4 5개 = 7.
L01 각각 J3 4개 + 끝 J4 2개 = 6; L02 각각 J3 5개 + 끝 J4 2개 = 7.
J2 합계 8; J3 합계 40; J4 합계 36(창짝 안착 홈 18 + 창살 끝 반턱 18).
총 92개 pocket = 모서리 8쌍 + 창살 교차 20쌍 + 창살 끝 18쌍 = 46쌍.

4. 가장 중요한 조립면 — 원판 양면 가공 불필요
---------------------------------------------
가공은 모든 부품에 대해 공통 상면 A에서만 합니다. 판을 뒤집어 가공하지
않습니다. 다만 분리 후 조립 단계에서 아래 면 배치를 반드시 지킵니다.

F01, S01, L01 : A면이 완성 창호의 앞쪽(FRONT)을 향함.
F02, S02, L02 : 부품을 뒤집어 A면이 뒤쪽(BACK)을 향함.

세로재는 10 mm pocket이 앞쪽에 있고, 가로재는 뒤쪽에 있습니다.
따라서 교차부의 잔존 재료가 뒤 10 mm + 앞 10 mm로 겹쳐 전체 20 mm가 됩니다.
모든 pocket을 앞면으로 조립하면 맞물리지 않습니다.

도면의 각 부품 로컬 좌표는 u=길이(+X), v=폭(+Y)입니다.
완성 정면에서 세로재의 u+는 위쪽, v+는 왼쪽입니다.
완성 정면에서 뒤집은 가로재의 u+는 오른쪽, v+는 아래쪽입니다.
S01-1/S02-1의 J4 홈은 v=0~10 쪽, S01-2/S02-2는 v=20~30 쪽입니다.
이렇게 조립하면 네 창짝 부재의 J4 홈이 모두 개구부 안쪽을 향합니다.

5. 홈 위치 — 부품 길이 방향 u 기준
-----------------------------------
J1 F01: [0,40], [423,463]; F02: [0,40], [546,586].
각각 전폭 40, 깊이 10.
J2 S01: [0,30], [347,377]; S02: [0,30], [470,500].
각각 전폭 30, 깊이 10.

S02의 L01 안착 홈 중심 u: 100, 175, 250, 325, 400.
S01의 L02 안착 홈 중심 u: 90.4, 155.8, 221.2, 286.6.
각 nominal seat는 중심에서 u +/-5, 폭 방향 삽입 길이 10, 깊이 10.
L01 교차 홈 중심 u: 70.4, 135.8, 201.2, 266.6.
L02 교차 홈 중심 u: 80, 155, 230, 305, 380.
교차 홈은 길이축 10 x 전폭 10, 깊이 10.
L01 끝 반턱: u=0~10 및 327~337; L02 끝 반턱: u=0~10 및 450~460.

완성 정면의 창살 중심 X: 143, 218, 293, 368, 443.
완성 정면의 가로 창살 중심 Y: 133.4, 198.8, 264.2, 329.6.
창짝 좌하단 (43,43), 유효 개구 좌하단 (73,73), A3 좌하단 (83,83).
주 DXF 조립도는 별도의 Model Space 위치 (1370,360)만큼 평행 이동되어
있습니다. 위 좌표는 도면 배치 오프셋을 뺀 완성 창호 자체 좌표입니다.

6. Layer / CNC 가공 의도
------------------------
BOARD_BOUNDARY     원판 경계. 절삭 선택에서 제외.
CUT_THROUGH        17개 외곽. 20 mm nominal 관통; 깊이와 spoilboard 관입은
                   실측 원판 두께 및 CAM 기준면에 맞게 작업자가 정함.
POCKET_10MM        92개 nominal pocket. A면으로부터 깊이 10.
DOGBONE            R3.2 원형 폐곡선 36개. 깊이 10, 부모 pocket과 합집합.
HINGE_REF          40 x 15 leaf 배치 envelope, 깊이 참고 2. 자동 절삭 금지.
                   정확한 hinge model, leaf 두께, 핀 돌출, 구멍은 미확정.
LATCH_REF          손잡이/캐치 위치 참고. 확정 가공 깊이/구멍 없음.
PART_ID            부품 ID annotation. 각인 가공 지시 아님.
DIMENSIONS         치수선/화살표/치수 문자. 절삭 금지.
GRAIN_DIRECTION    목리 방향 annotation. 절삭 금지.
ASSEMBLY_REFERENCE 정면 조립 및 결합 상세의 모든 참고 형상. 절삭 금지.
NOTES              설명, 표제, 상세 테두리. 절삭 금지.

모든 실제 가공 contour는 Model Space에 독립적인 closed LWPOLYLINE으로
존재합니다. block 안에 숨겨진 가공 부품, open machining contour,
self-intersection, 완전히 중복된 가공 contour는 없습니다.
원형 relief는 2개의 bulge=1 반원으로 된 정확한 원형 폐곡선입니다.
DXF를 불러오는 CAM이 LWPOLYLINE bulge를 보존하는지 확인하십시오.
참고/치수선에는 당연히 열린 LINE 객체가 있지만 가공 contour가 아닙니다.
폐 pocket의 개방 경계와 관통 외곽의 일부 선분은 XY 위치가 일치합니다.
이는 깊이가 다른 두 작업의 의도된 공통 경계이며 중복 contour가 아닙니다.
모든 layer를 한 번에 선택하거나 깊이 구분 없이 OVERKILL/중복선 정리를
실행하면 결합 홈의 필요한 경계가 사라질 수 있습니다.

7. Dog-bone 및 개방형 pocket의 CAM 처리 — 반드시 읽을 것
---------------------------------------------------------
Dog-bone은 창짝의 J4 U자 안착 홈 18곳의 닫힌 안쪽 코너 2개씩, 총 36개에
존재합니다. nominal 10 x 10 사각형은 POCKET_10MM, 원형 relief는 DOGBONE에
실제로 그려져 있습니다. 원형은 임의 위치점 또는 설명문이 아닙니다.
각 원의 중심은 nominal 코너에서 pocket 안쪽 45도 방향으로
R/sqrt(2)=2.2627417씩 이동한 위치입니다. R=3.2라서 nominal 코너를 통과하고,
해당 사각형의 벽 바깥으로 최대 0.9372583 mm 더 제거합니다.
모든 원형 relief와 pocket은 해당 부품 경계 내부에 남도록 검증했습니다.

CAM에서 각 nominal pocket + 해당 DOGBONE 두 원을 Boolean UNION한 영역을
같은 깊이 10으로 제거하십시오. 원을 island(남길 섬) 또는 별도 관통
구멍으로 인식시키지 마십시오. 원과 사각형의 중첩은 추가 제거 영역이라는
의도이며, 깊이를 합산하여 20 mm로 만들면 안 됩니다. 결합별 XDATA의
joint_id 또는 pocket_schedule.csv로 두 원과 부모 홈의 대응을 찾을 수 있습니다.
Boolean union은 CAM 준비 과정이며, 이 DXF에는 임의 toolpath를 넣지 않았습니다.

J1/J2의 끝 반턱, J3의 전폭 창살 홈, J4의 창살 끝 반턱은 부품 바깥쪽으로
열린 pocket입니다. 닫힌 nominal contour는 '부품 내부에서 제거할 영역'을
뜻하며, 그 외곽 모두를 공구 진입 불가 벽으로 해석해서는 안 됩니다.
CAM에서 지정된 열린 경계 쪽으로 공구가 폐기 영역까지 벗어나 가공하도록
open-side pocket / boundary extension / 동등한 전략을 설정하십시오.
이를 일반 내부 pocket으로만 가공하면 열린 어깨 모서리에 R3 잔재가 남아
결합이 맞지 않을 수 있습니다. 외부 모서리에 불필요한 dog-bone을 넣는
대신 개방 경계의 overrun으로 해결하는 설계입니다.
J4 안착 홈의 부품 가장자리 쪽 경계도 개방형입니다. 반대쪽 닫힌 2코너만
DOGBONE으로 처리됩니다. 명목 pocket이 부품 밖으로 나가지 않으면서 실제
사각 mating part가 들어가도록 하는 CAD/CAM 역할 분리입니다.

8. 권장 가공 작업 순서 / 공차
-----------------------------
원판 함수율/평탄도와 최종 두께를 확인 -> 기준면 A를 표시 -> 고정 계획 승인
-> 동일 재료 자투리에서 10 mm 폭 결합부 시험 -> POCKET_10MM과 DOGBONE 처리
-> 필요 시 실제 선정 하드웨어의 별도 승인 가공 -> CUT_THROUGH 외곽 분리
-> 잔여 tabs/onion skin 제거, 부분 모서리 정리, 치수 검사 순으로 진행합니다.
10 mm 폭의 긴 창살은 분리 직후 쉽게 움직이거나 파손될 수 있습니다.
진공만으로 충분하다고 가정하지 마십시오. 실제 장비에 맞는 지그/고정/
탭/onion-skin을 CAM에서 결정하고 pocket 작업 동안 부품이 움직이지 않게 합니다.
탭 위치, 탭 높이, feed, speed, stepdown, 공구 보정, 실제 toolpath는 이 파일에
작성하지 않았습니다. clamp와 나사의 위치도 확인해야 합니다.
12 mm는 부품 최종 외곽 간 간격으로, toolpath 또는 clamp 간격이 아닙니다.

현재 10.00 슬롯 / 10.00 창살의 명목치이며 임의 유격을 넣지 않았습니다.
원목의 실제 치수, finish 두께, 함수율과 장비 보정에 따라 끼움 공차가 필요할
수 있습니다. 시험편 결과에 따라 CAM 벽 보정 또는 CAD 치수를 승인하고,
서로 맞물리는 부품은 함께 관리하십시오. 강제 압입하지 마십시오.
반턱 바닥은 10.00 잔존 두께가 되도록 맞춰야 앞뒤 표면이 20 mm로 평평해집니다.

9. 조립 순서
-------------
1) 분리 전/직후 A면과 Part ID를 표시하고, 날카로운 burr만 제거합니다.
   맞춤면의 치수를 과도하게 샌딩하지 않습니다.
2) 고정틀: F01-1/2를 A면 앞쪽으로 지그에 배치하고, F02-1/2는 A면을
   뒤로 뒤집어 대응 반턱에 포개어 586 x 463 및 대각선을 확인합니다.
3) 창짝: 평평한 지그에서 S01-1/2와 L01-1~5를 A면 위쪽(완성 앞면)으로
   배치합니다. 가로 창살 L02-1~4는 A면 아래로 뒤집어, 20개 교차부와
   양쪽 S01의 끝 안착 홈에 동시에 내려 끼웁니다.
4) S02-1/2도 A면 아래로 뒤집어 S01 모서리와 L01 양 끝에 내려 끼웁니다.
   먼저 무접착 dry-fit으로 500 x 377, 440 x 317, 앞뒤 표면의 평탄함,
   각 교차점, 양 끝 삽입 길이 10 및 직각을 확인합니다.
5) 이 구조는 홈이 평면 내 위치를 구속하는 half-lap 결합이지, 접착 없이
   앞뒤 방향으로도 스스로 잠기는 knock-down 조인트는 아닙니다.
   검증된 목공 접착제와 평면/직각 클램핑으로 결합을 고정해야 합니다.
   단순히 창살을 테두리 위에 붙이는 구조와는 다릅니다.
6) 실제 경첩 모델을 선정한 뒤 고정틀 F01-1과 창짝 S01-1에 승인된
   가공/체결을 합니다. 위·아래 참고 hinge 중심 Y는 350 및 113입니다.
7) 3 mm 간극용 shim으로 창짝을 맞추고, 선택 경첩의 개폐 경로, 나사 관통,
   catch/handle, 닫힘 스토퍼/완충을 실제 조립품에서 확인합니다.
8) 별도 후판/그림 고정구를 설치하고 A3를 가운데 배치합니다.

10. 경첩, 캐치, 후판 — 목재 부품과 별도로 필요한 항목
-------------------------------------------------------
경첩 참고 사각형은 앞면 장착 leaf envelope입니다. 흔한 경첩이라는 이유로
2 mm pocket을 바로 가공하지 마십시오. 정확한 leaf/knuckle/나사 설계와
핀 축의 앞뒤 위치에 따라 도면을 수정해야 합니다. Edge-mounted hinge로
바꾸는 경우에도 별도 측면 가공 지시가 필요합니다.

검증 보고서에는 임시 축 X=41.5, Z=24(앞면 Z=20보다 4 mm 앞)를 가정하여
0~90도를 0.1도 간격으로 회전시킨 창짝 envelope와 고정틀의 간섭 0 결과가
있습니다. 이 값은 실제 제품의 확정 핀 위치가 아니며, hinge knuckle,
나사 머리, handle/catch, 후판까지 포함한 실물 제품 검증이 아닙니다.
선정 하드웨어로 축이 바뀌면 반드시 다시 확인해야 합니다.

힌지 2개, 체결 나사, 손잡이, 캐치 및 필요 시 닫힘 스토퍼/완충재,
고정틀의 벽체/전시대 고정 하드웨어는 구매 부품입니다.
벽체 고정 위치와 나사 구멍은 선정되지 않아 임의로 가공하지 않았습니다.

A3는 개구보다 각 변 10 mm 작기 때문에 목재 17개만으로 뒷받침/고정되지
않습니다. 그림은 창살 뒤쪽의 별도 비목재 후판/마운트에 고정하십시오.
예를 들어 고정틀 뒤에서 비목재 패널 546 x 423을 가운데 배치하면
고정틀의 안쪽 개구 506 x 383에 대해 각 변 20 mm 겹침을 얻습니다.
이는 배치 참고 크기일 뿐 패널 재질/두께/체결 구멍은 최종 설계가 아닙니다.
후판/그림 표면과 창짝 뒷면 사이에는 실제 충분한 비접촉 간격을 확보하고,
닫힘 동작과 뒤틀림을 포함한 실측으로 확인해야 합니다.
추가 목재 부품을 필요 부품으로 몰래 제외한 것이 아니라, 구매 비목재
부품으로 그림 지지를 분리한 구성입니다. 후판은 원목 nesting에 없습니다.
유리/아크릴을 창짝 안에 끼울 rebate, 방수/기밀, 외부용 배수는 포함하지 않습니다.

11. 검증 결과
--------------
부품 수: F01=2, F02=2, S01=2, S02=2, L01=5, L02=4.
모든 부품 원판 안에 존재 / 겹침 없음 / min gap 12 / min margin 20.
J1=8, J2=8, J3=40, J4=36 / 총 pocket=92.
필요한 R3.2 dog-bone=36 / 해당 부품 밖으로 나간 pocket/relief 없음.
17+92+36=145개 가공 profile 모두 폐곡선, self-intersection 없음.
모든 46쌍의 대응 pocket을 조립 좌표로 변환하여 위치 일치와 앞뒤 면 대응 확인.
실제 제거 형상을 z=0~10, z=10~20 두 층으로 나눠 겹침 체적이 없는지 확인.
DXF units=4(mm), 모든 가공은 Model Space, annotation은 비가공 layer.
DXF audit errors=0, fixes=0. 자세한 검사와 수치는 validation_report.json 참조.
도면 XDATA는 HANOK_A3 application에 부품 ID, joint_id, 깊이, 조립면,
개방 경계, 조립 변환식을 기록합니다. CNC는 별도로 layer/depth를 설정해야 합니다.

12. 재생성 / 읽기 검증
----------------------
Python 3 환경에서 ezdxf>=1.4, shapely>=2, Pillow를 설치하고:
    python build_hanok_window.py
를 실행합니다. PNG 렌더링은 DejaVu Sans 계열 로컬 폰트가 필요합니다.
환경에 따라 소스의 FONT_REG, FONT_BOLD, FONT_MONO 경로를 수정하십시오.
폰트 바이너리는 패키지에 포함하지 않았습니다.

독립 재검증 예:
    import ezdxf
    import build_hanok_window as h
    d = ezdxf.readfile('hanok_window_A3_one_board_CNC.dxf')
    print(h.validate(d, phase='INDEPENDENT_RECHECK')['status'])

재생성은 같은 기하 형상/치수/검증 결과를 만드는 것을 뜻하며, DXF의 생성 시각,
handle 또는 SHA-256까지 모든 실행에서 동일하다는 뜻은 아닙니다.

DXF 형식 구현 참고:
- ezdxf 공식 문서, LWPolyline / closed flag / exact bulge arcs
  https://ezdxf.readthedocs.io/en/stable/dxfentities/lwpolyline.html
- ezdxf 공식 문서, General Document / readfile / units / audit
  https://ezdxf.readthedocs.io/en/stable/howto/document.html
결합 배치, dog-bone 좌표 및 조립 검증 수치는 이 패키지의 설계 계산 결과입니다.
'''
    (OUT/'README.txt').write_text(s,encoding='utf-8')


def make_zip():
    target=OUT.parent/'hanok_window_A3_one_board_CNC_package.zip'
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(OUT.iterdir()):
            if p.is_file() and p.suffix in ('.dxf','.png','.txt','.json','.csv','.py') and not p.name.startswith('_'):
                z.write(p,arcname=p.name)
    return target

def main():
    doc,report,positions=build()
    render_nesting(doc,report)
    render_details(doc,positions)
    render_assembly(doc)
    write_readme(report)
    z=make_zip()
    print(json.dumps({'status':report['status'],'checks_passed':report['checks_passed'],
                      'dxf':str(DXF),'zip':str(z),'pockets':report['nominal_pockets_total'],
                      'reliefs':report['dogbone_reliefs_total']},indent=2))

if __name__=='__main__':main()
