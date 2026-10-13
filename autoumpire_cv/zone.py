"""Identical pentagonal prism conventions as src/geometry.js."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

PLATE_HALF_M = 17 * 0.0254 / 2
PLATE_XZ = [(-PLATE_HALF_M,-PLATE_HALF_M), (PLATE_HALF_M,-PLATE_HALF_M),
            (PLATE_HALF_M,0), (0,PLATE_HALF_M), (-PLATE_HALF_M,0)]

@dataclass(frozen=True)
class StrikeZone:
    bottom_m: float
    top_m: float

    def __post_init__(self):
        if not (0<=self.bottom_m<self.top_m<=3):
            raise ValueError('Invalid zone bounds (meters)')

    @property
    def corners(self)->np.ndarray:
        return np.asarray([[x,y,z] for y in (self.bottom_m,self.top_m) for x,z in PLATE_XZ],dtype=np.float64)

    @property
    def edges(self):
        return [(i,(i+1)%5) for i in range(5)]+[(i+5,(i+1)%5+5) for i in range(5)]+[(i,i+5) for i in range(5)]

    def frame_dict(self,pose,frame_num:int):
        return {'frame':frame_num,'world_to_camera':pose.world_to_camera.reshape(-1).tolist(),
                'reprojection_px':pose.reprojection_px,
                'zone':{'bottom_m':self.bottom_m,'top_m':self.top_m}}

    def draw(self,frame,camera,pose):
        import cv2
        from .registration import project_world
        pix=project_world(self.corners,pose,camera)
        for i,j in self.edges:
            a,b=tuple(np.rint(pix[i]).astype(int)),tuple(np.rint(pix[j]).astype(int))
            cv2.line(frame,a,b,(53,202,255),2,cv2.LINE_AA)
        return frame
