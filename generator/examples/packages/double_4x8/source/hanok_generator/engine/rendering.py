"""PNG views of the saved DXF and shared face-orientation wording."""
import math

from PIL import Image, ImageDraw

from .cad_helpers import COL, Renderer, label, meta, wrapped
from .. import formats


def face_note(cfg):
    front=' / '.join(k for k,(_,_,count) in cfg.SIZES.items() if count and k in ('F01','S01','L01','B01'))
    back=' / '.join(k for k,(_,_,count) in cfg.SIZES.items() if count and k in ('F02','S02','L02','B02'))
    note=f'{front}: A -> FRONT. {back}: flip A -> BACK.'
    # The back frame carries no machining, so the note says where it goes instead.
    return note+f' B01 / B02: BEHIND THE FIXED FRAME, Z {-cfg.THK:g} TO 0.' if cfg.ART else note


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
              ('ARTWORK PANEL' if cfg.ART else 'REAR PICTURE',
               f'{cfg.ARTW:g} x {cfg.ARTH:g} x {cfg.ARTT:g} mm in a {cfg.BMW:g} mm back frame one layer behind; '
               f'{cfg.ACOV:g} mm covered on each side, {cfg.AFIT:g} mm fit, {cfg.ASPC:g} mm spacer.' if cfg.ART else
               f'{cfg.A3W:g} x {cfg.A3H:g} mm, centred, minimum margin {cfg.PMG:g} mm.' if cfg.PICTURE else 'No picture specified.'),
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
    if cfg.ART:notes.append('The artwork panel sits in the back frame behind the fixed frame, never on the moving leaves. '
                            'Spacer, backing and fixings are supplied separately.')
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
                     ('ARTWORK PANEL' if cfg.ART else 'REAR PICTURE',
                      f'One {cfg.ARTW:g} x {cfg.ARTH:g} x {cfg.ARTT:g} mm panel in the back frame, {cfg.ASPC:g} mm behind the fixed frame.' if cfg.ART else
                      f'One fixed {cfg.A3W:g} x {cfg.A3H:g} mm picture on a separate backing.' if cfg.PICTURE else 'No picture or rear picture plane is specified.'),
                     ('PENDING','Select actual hinges, screws, catches and backing. Check full movement, loads and clearances before manufacture.')]:
        label(d,(2970,y),ttl,29,bold=True);y+=57
        y=wrapped(d,body,(2970,y),875,29)+66
    label(d,(115,2580),'REFERENCE ONLY / Dynamic interference and real hardware are not validated by this illustration.',29,bold=True)
    label(d,(115,2650),'No opening diagram is a CNC pocket or a toolpath.',27,fill=COL['muted'])
    im.save(cfg.OUT/'04_opening_reference.png',dpi=(220,220))
