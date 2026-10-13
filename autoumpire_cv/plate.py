"""Optional conservative white pentagon detection for an unobstructed plate.

This algorithm is heuristic and is NOT validated under game conditions. Most
cameras behind the catcher will see the plate occluded. Marker mode is preferred.
"""
from __future__ import annotations
import cv2
import numpy as np
from .registration import fit_pose
from .zone import PLATE_XZ

WORLD = np.array([[x,0,z] for x,z in PLATE_XZ],dtype=np.float64)


def contour_candidates(frame,minimum_area=900):
    hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
    mask=cv2.inRange(hsv,np.array([0,0,165],np.uint8),np.array([179,65,255],np.uint8))
    mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    for contour in sorted(contours,key=cv2.contourArea,reverse=True):
        area=cv2.contourArea(contour)
        if area<minimum_area:continue
        per=cv2.arcLength(contour,True)
        approx=cv2.approxPolyDP(contour,.022*per,True)
        if len(approx)!=5 or not cv2.isContourConvex(approx):continue
        pts=approx.reshape(5,2).astype(np.float64)
        # Require a nondegenerate silhouette; not a guarantee it is home plate.
        if area/cv2.contourArea(cv2.convexHull(contour))<.85:continue
        yield pts


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


def detect_plate(frame,camera,*,max_reprojection_px=2.5):
    best=None
    for pts in contour_candidates(frame):
        ordered=order_pentagon(pts)
        if ordered is None:continue
        est=fit_pose(WORLD,ordered,camera)
        if est is not None and est.reprojection_px<=max_reprojection_px:
            est.method='plate-contour'
            if best is None or est.reprojection_px<best.reprojection_px:best=est
    return best
