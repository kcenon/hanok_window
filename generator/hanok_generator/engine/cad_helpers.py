"""Shared DXF primitives and deterministic raster renderer. No CAM paths.
The raster drawings are rendered directly from saved DXF entities.
"""
from __future__ import annotations
import json, math, os
from pathlib import Path
import ezdxf
from ezdxf.enums import TextEntityAlignment
from ezdxf.path import make_path
from shapely.geometry import Polygon
from PIL import Image, ImageDraw, ImageFont
from .numeric_policy import polyline_points
APP = 'HANOK_PORTRAIT_DL'
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
    # Production geometry is LWPOLYLINE. Sample its actual circular bulges;
    # make_path would first approximate circles by cubic Bezier curves.
    pts=polyline_points(e) if e.dxftype()=='LWPOLYLINE' else [
        (v.x,v.y) for v in make_path(e).flattening(distance=0.00001,segments=64)]
    return Polygon(pts)


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

# Which face each role actually resolved to. Fonts come from the machine, not
# from this package, so the PNGs are only reproducible on a machine that resolves
# the same files. Recording the resolution makes a PNG hash mismatch diagnosable
# instead of mysterious. The DXF stores TEXT entities and no outlines, so it is
# unaffected by whatever is chosen here.
FONTS_USED={}

def font(size,bold=False,mono=False):
    role='mono' if mono else 'bold' if bold else 'regular'
    candidate = FONT_MONO if mono else FONT_BOLD if bold else FONT_REG
    candidates=[os.environ.get('HANOK_FONT',''),candidate,
                'DejaVuSansMono.ttf' if mono else 'DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf',
                'Arial.ttf', 'arial.ttf']
    for path in candidates:
        if not path: continue
        try:
            f=ImageFont.truetype(path,max(6,int(size)))
            FONTS_USED.setdefault(role,path)
            return f
        except OSError: pass
    FONTS_USED.setdefault(role,'PIL built-in default')
    return ImageFont.load_default(size=max(6,int(size)))

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
        # The pocket layer is named after the depth (POCKET_9MM on an 18 mm board), so
        # nested pockets are known by their kind and detail pockets by their role.
        if data.get('kind')=='pocket' or role=='pocket':fill=COL['pocket'];stroke=COL['pocketline'];lw=max(2,round(self.s*.35))
        if layer=='DOGBONE' or role=='dogbone':fill=COL['dog'];stroke=COL['dogline'];lw=max(1,round(self.s*.28))
        if layer in ('HINGE_REF','LATCH_REF'):stroke=COL['hardware'];dashed=True;lw=max(2,round(self.s*.4))
        if role=='section_front':fill=COL['front'];stroke=COL['ink'];lw=max(2,round(self.s*.35))
        if role=='section_back':fill=COL['back'];stroke=COL['ink'];lw=max(2,round(self.s*.35))
        if role=='picture':fill=COL['paper'];stroke=COL['picture'];dashed=True;lw=max(2,round(self.s*.55))
        if role in ('opening','picture_region'):stroke=COL['opening'];dashed=True;lw=max(2,round(self.s*.45))
        if layer=='GRAIN_DIRECTION':stroke=COL['grain'];lw=max(3,round(self.s*1.1))
        if layer=='BOARD_BOUNDARY':fill=COL['paper'];stroke=COL['ink'];lw=max(3,round(self.s*.75))
        if layer=='DIMENSIONS':stroke=COL['muted'];lw=max(1,round(self.s*.25))
        if data.get('kind')=='detail_border':stroke=COL['border'];fill=None;lw=2
        if e.dxftype()=='LWPOLYLINE':
            pts=[self.pt((v.x,v.y)) for v in make_path(e).flattening(distance=.003,segments=16)]
            if fill:self.d.polygon(pts,fill=fill)
            if dashed:self.dashed(pts,stroke,lw,dash=(22,7,4,7) if role=='picture' else (12,7),close=e.closed)
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
