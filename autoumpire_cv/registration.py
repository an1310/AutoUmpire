"""Calibrated ArUco marker -> world-to-camera registration in plate coordinates.

Coordinate convention shared with the browser: x right (toward first base), y up,
z toward catcher. OpenCV camera coordinates: x right, y down, z forward.

A marker is placed FLAT in the field at a physically measured location relative
 to the center of plate. The marker's TOP edge faces the pitcher when yaw=0.
A marker by itself does NOT locate plate unless this offset is measured.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import math
import cv2
import numpy as np


@dataclass(frozen=True)
class MarkerLocation:
    marker_id: int = 0
    side_m: float = 0.15
    x_m: float = -0.8
    z_m: float = 0.0
    yaw_deg: float = 0.0

    def points(self) -> np.ndarray:
        if not (0 < self.side_m < 1 and -20 < self.x_m < 20 and -20 < self.z_m < 20):
            raise ValueError('Marker side/position out of range')
        h = self.side_m / 2
        # Corner order must match ArUco TL,TR,BR,BL in marker PRINT orientation.
        xz = np.array([[-h,-h], [h,-h], [h,h], [-h,h]], dtype=np.float64)
        yaw = math.radians(self.yaw_deg)
        # world Y axis yaw rotation, keeping x/z handedness.
        rot = np.array([[math.cos(yaw),math.sin(yaw)],
                        [-math.sin(yaw),math.cos(yaw)]])
        xz = xz @ rot.T + [self.x_m,self.z_m]
        return np.array([[x,0,z] for x,z in xz], dtype=np.float64)


@dataclass
class Camera:
    matrix: np.ndarray
    distortion: np.ndarray
    width: int
    height: int

    @classmethod
    def from_config(cls, data: dict) -> 'Camera':
        if 'matrix' in data:
            K = np.asarray(data['matrix'], dtype=np.float64)
        else:
            K = np.array([[data['fx'],0,data['cx']],
                          [0,data['fy'],data['cy']], [0,0,1]], dtype=np.float64)
        D = np.asarray(data.get('distortion',[0,0,0,0,0]), dtype=np.float64)
        w,h = int(data['width']),int(data['height'])
        if K.shape!=(3,3) or not np.isfinite(K).all() or K[0,0]<=0 or K[1,1]<=0:
            raise ValueError('Invalid camera intrinsics')
        if D.size not in (4,5,8,12,14) or not np.isfinite(D).all():
            raise ValueError('Invalid distortion')
        if w<=0 or h<=0: raise ValueError('Invalid calibrated image size')
        return cls(K,D,w,h)

    def validate_frame(self, frame):
        h,w = frame.shape[:2]
        if (w,h)!=(self.width,self.height):
            raise ValueError(f'Frame {w}x{h} != calibration {self.width}x{self.height}; do not resize or crop without updating intrinsics')


@dataclass
class Estimate:
    rvec: np.ndarray
    tvec: np.ndarray
    reprojection_px: float
    marker_pixels: float
    method: str = 'aruco'

    @property
    def world_to_camera(self) -> np.ndarray:
        R,_ = cv2.Rodrigues(self.rvec)
        M=np.eye(4)
        M[:3,:3]=R
        M[:3,3]=self.tvec.ravel()
        return M

    @property
    def camera_position(self) -> np.ndarray:
        R,_ = cv2.Rodrigues(self.rvec)
        return (-R.T @ self.tvec.reshape(3)).ravel()


def fit_pose(object_pts, image_pts, camera:Camera) -> Optional[Estimate]:
    """Fit planar world points. A single plane can be ambiguous: apply physical gates.

    solvePnPGeneric IPPE returns both planar candidates. Select the solution
    viewing the field from ABOVE the ground and camera behind the plate.
    The score (RMS) alone is NOT an independent accuracy guarantee.
    """
    obj=np.ascontiguousarray(object_pts,dtype=np.float64).reshape(-1,3)
    img=np.ascontiguousarray(image_pts,dtype=np.float64).reshape(-1,2)
    if len(obj)<4 or len(obj)!=len(img) or not np.isfinite(img).all(): return None
    try:
        ok, rvecs, tvecs, _ = cv2.solvePnPGeneric(obj,img,camera.matrix,camera.distortion,flags=cv2.SOLVEPNP_IPPE)
    except cv2.error:
        return None
    if not ok: return None
    candidates=[]
    for r,t in zip(rvecs,tvecs):
        R,_=cv2.Rodrigues(r)
        C=(-R.T @ t.reshape(3)).ravel()
        # Behind the catcher looking toward the mound; this is a deliberate
        # camera-placement assumption, configurable after initial field trials.
        if not (0.35 <= C[1] <= 4.0 and 0.05 <= C[2] <= 12): continue
        cam=obj @ R.T+t.reshape(1,3)
        if np.any(cam[:,2]<=0): continue
        pixels,_=cv2.projectPoints(obj,r,t,camera.matrix,camera.distortion)
        error=float(np.sqrt(np.mean(np.sum((pixels.reshape(-1,2)-img)**2,axis=1))))
        candidates.append((error,r,t))
    if not candidates:return None
    error,r,t=min(candidates,key=lambda x:x[0])
    perimeter=float(cv2.arcLength(img.astype(np.float32),True))
    return Estimate(r.copy(),t.copy(),error,perimeter/4)


class PlateTracker:
    """Marker-observed 6DoF pose; reject discontinuities and hide on missed frames.

    No IMU or optical-flow extrapolation; a lost marker means no rendering.
    """
    def __init__(self,camera:Camera,marker:MarkerLocation,*,max_reprojection_px=2.5,
                 min_marker_side_px=22.0,max_step_m=0.35,max_step_deg=25):
        self.camera,self.marker=camera,marker
        dictionary=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        self.detector=cv2.aruco.ArucoDetector(dictionary,cv2.aruco.DetectorParameters())
        self.max_reprojection_px=max_reprojection_px
        self.min_marker_side_px=min_marker_side_px
        self.max_step_m=max_step_m
        self.max_step_deg=max_step_deg
        self.previous:Optional[Estimate]=None
        self.rejected:Optional[str]=None

    def track(self,frame) -> Optional[Estimate]:
        self.camera.validate_frame(frame)
        corners,ids,_=self.detector.detectMarkers(frame)
        if ids is None or self.marker.marker_id not in ids.ravel():
            self.rejected='marker-not-visible';self.previous=None;return None
        i=int(np.where(ids.ravel()==self.marker.marker_id)[0][0])
        img=corners[i].reshape(-1,2)
        est=fit_pose(self.marker.points(),img,self.camera)
        if est is None:
            self.rejected='invalid-pose';self.previous=None;return None
        if est.marker_pixels < self.min_marker_side_px or est.reprojection_px>self.max_reprojection_px:
            self.rejected='insufficient-observation';self.previous=None;return None
        if self.previous is not None:
            delta=float(np.linalg.norm(est.camera_position-self.previous.camera_position))
            Ra,_=cv2.Rodrigues(est.rvec);Rb,_=cv2.Rodrigues(self.previous.rvec)
            angle=float(math.degrees(math.acos(np.clip((np.trace(Ra@Rb.T)-1)/2,-1,1))))
            if delta > self.max_step_m or angle > self.max_step_deg:
                self.rejected='pose-jump';self.previous=None;return None
        self.previous=est
        self.rejected=None
        return est


def project_world(points,pose:Estimate,camera:Camera) -> np.ndarray:
    pixels,_=cv2.projectPoints(np.asarray(points,dtype=np.float64).reshape(-1,3),
                               pose.rvec,pose.tvec,camera.matrix,camera.distortion)
    return pixels.reshape(-1,2)
