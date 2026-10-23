"""Optional home-plate detection from its outline, for frames where it is visible.

The plate is found by RELATIVE contrast: pixels clearly brighter and less colorful
than the surrounding dirt (CIE Lab, against a large local median). Absolute
"white" thresholds fail on real fields: a dirty plate under lights, and HDR video,
can make plate and dirt overlap in absolute color while the local contrast
remains (measured on iPhone HDR practice footage: plate +13..+32 lightness and
-7..-12 chroma relative to nearby dirt).

Heuristic and NOT validated under game conditions. The catcher hides the plate
for most of a pitch, so this can anchor a pose between pitches but cannot carry
it through one; poses must pass PlateTracker.accept like any other source.
"""
from __future__ import annotations
import cv2
import numpy as np
from .registration import fit_pose
from .zone import PLATE_XZ

WORLD = np.array([[x,0,z] for x,z in PLATE_XZ],dtype=np.float64)
# Tuned on 1920 px frames; every pixel size below scales with the frame.
REFERENCE_PX = 1920


def _odd(n:float) -> int:
    n=max(3,int(round(n)))
    return n if n%2 else n+1


def plate_mask(frame,*,min_score=16.0,max_extra_chroma=3.0,ref_px=None):
    """Mask of pixels that are lighter and less colorful than their local background.

    score = (lightness - background) - (chroma - background), in 8-bit Lab units,
    must exceed ``min_score``; chroma may not exceed the background's by more than
    ``max_extra_chroma``. A combined score (rather than requiring LOWER chroma)
    keeps a white plate detectable on neutral gray mats or turf, where there is no
    chroma contrast, while bright-but-dirt-colored patches still score low.

    ``ref_px`` is the long side of the full frame; pass it when ``frame`` is a
    crop so the neighborhood sizes match the original image.
    """
    h,w=frame.shape[:2]
    k=(ref_px or max(h,w))/REFERENCE_PX
    lab=cv2.cvtColor(frame,cv2.COLOR_BGR2LAB)
    L=lab[...,0]
    chroma=np.clip(np.hypot(lab[...,1].astype(np.float32)-128,lab[...,2].astype(np.float32)-128),0,255).astype(np.uint8)
    # Background: median over a neighborhood several plate-widths across,
    # computed at quarter resolution for speed.
    small=(max(1,w//4),max(1,h//4))
    kernel=_odd(101*k)
    def background(channel):
        b=cv2.medianBlur(cv2.resize(channel,small,interpolation=cv2.INTER_AREA),kernel)
        return cv2.resize(b,(w,h),interpolation=cv2.INTER_LINEAR).astype(np.float32)
    dL=L.astype(np.float32)-background(L)
    dC=chroma.astype(np.float32)-background(chroma)
    mask=(((dL-dC)>min_score)&(dC<max_extra_chroma)).astype(np.uint8)*255
    mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((_odd(5*k),)*2,np.uint8))
    # Dirt streaks split a plate into pieces; close gaps a few percent of its width.
    close=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(_odd(41*k),)*2)
    return cv2.morphologyEx(mask,cv2.MORPH_CLOSE,close)


def contour_candidates(frame,*,min_area=900,min_solidity=0.7,ref_px=None):
    """Convex pentagons (image points) that could be the plate's outline."""
    k=(ref_px or max(frame.shape[:2]))/REFERENCE_PX
    contours,_=cv2.findContours(plate_mask(frame,ref_px=ref_px),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    for contour in sorted(contours,key=cv2.contourArea,reverse=True):
        area=cv2.contourArea(contour)
        if area<min_area*k*k:continue
        hull=cv2.convexHull(contour)
        if len(hull)<5 or area/cv2.contourArea(hull)<min_solidity:continue
        # A dirty edge adds spurious corners; force the best-fitting 5-gon instead.
        pts=cv2.approxPolyN(hull,5,ensure_convex=True).reshape(-1,2).astype(np.float64)
        if len(pts)==5:yield pts


def order_pentagon(pts):
    """Image view is presumed from catcher to pitcher: apex points downscreen.

    World vertex 3 is the apex. Neighbors map to world 2/right and 4/left.
    """
    tip=int(np.argmax(pts[:,1]))
    previous=(tip-1)%5;following=(tip+1)%5
    # x ordering determines first/third baseline from a catcher-side camera.
    right,left = (previous,following) if pts[previous,0]>pts[following,0] else (following,previous)
    i1=(right-1)%5 if (right+1)%5==tip else (right+1)%5
    i0=(left-1)%5 if (left+1)%5==tip else (left+1)%5
    if len({tip,right,left,i1,i0})!=5:return None
    return pts[[i0,i1,right,tip,left]]


def detect_plate(frame,camera,*,max_reprojection_px=4.0,ref_px=None):
    """Best plate pose in one frame, or None. Ungated: pass it to PlateTracker.accept.

    The 4 px limit (vs 2.5 px for printed markers) reflects real, worn plate
    edges; on practice footage it accepted far more true plates while gated
    poses showed no frame-to-frame jumps over 10 cm.
    """
    best=None
    for pts in contour_candidates(frame,ref_px=ref_px):
        ordered=order_pentagon(pts)
        if ordered is None:continue
        est=fit_pose(WORLD,ordered,camera)
        if est is None or est.reprojection_px>max_reprojection_px:continue
        est.method='plate-contour'
        # Rank by error RELATIVE to outline size: in pixels, a small sliver fits as
        # well as the real plate does (seen on practice footage: a 2k px sliver at
        # 1.3 px beat the 64k px plate at 2.6 px and placed the camera 4.5 m off).
        relative=est.reprojection_px/(cv2.arcLength(ordered.astype(np.float32),True)/5)
        if best is None or relative<best[0]:best=(relative,est)
    return None if best is None else best[1]
