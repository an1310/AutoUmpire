"""Calibrated ArUco marker -> world-to-camera registration in plate coordinates.

Coordinate convention shared with the browser: x right (toward first base), y up,
z toward catcher. OpenCV camera coordinates: x right, y down, z forward.

A marker is placed FLAT in the field at a physically measured location relative
 to the center of plate. The marker's TOP edge faces the pitcher when yaw=0.
A marker by itself does NOT locate plate unless this offset is measured.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Optional, Sequence, Union
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
    timestamp_s: Optional[float] = None
    markers_used: tuple = ()
    markers_dropped: tuple = ()

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


MAX_MARKERS=8
NOMINAL_DT=1/30


def marker_side_px(img) -> float:
    return float(np.mean(np.linalg.norm(img-np.roll(img,-1,axis=0),axis=1)))


class PlateTracker:
    """Marker-observed 6DoF pose; reject discontinuities and hide on missed frames.

    No IMU or optical-flow extrapolation; a lost marker means no rendering.
    Acquisition (at start, after loss, or after a pose jump) needs
    ``reacquire_frames`` consecutive consistent poses before anything is shown.

    Several measured ground markers (a "board") are fit as ONE planar PnP problem,
    which is far better conditioned than a single small tag. Any usable subset of
    at least ``min_markers`` (default: 3, or all if fewer are configured) may be
    visible. Markers that disagree with the consensus pose (kicked, mis-measured)
    are excluded; if too few agree, the overlay is hidden. With only two markers
    a displacement along their baseline is absorbed by the fit and NOT detected.
    """
    def __init__(self,camera:Camera,marker:Union[MarkerLocation,Sequence[MarkerLocation]],*,
                 max_reprojection_px=2.5,min_marker_side_px=22.0,max_speed_m_s=10.5,max_turn_deg_s=750.0,
                 reacquire_frames=3,min_markers:Optional[int]=None):
        if reacquire_frames<1:raise ValueError('reacquire_frames must be >= 1')
        markers=(marker,) if isinstance(marker,MarkerLocation) else tuple(marker)
        if not 1<=len(markers)<=MAX_MARKERS:raise ValueError(f'Layout needs 1..{MAX_MARKERS} markers')
        ids=[m.marker_id for m in markers]
        if len(set(ids))!=len(ids):raise ValueError(f'Duplicate marker ids in layout: {ids}')
        # Three markers are the fewest that can out-vote one displaced marker.
        if min_markers is None:min_markers=min(3,len(markers))
        if not 1<=min_markers<=len(markers):raise ValueError('min_markers must be within 1..len(markers)')
        self.camera,self.markers,self.min_markers=camera,markers,min_markers
        self.points={m.marker_id:m.points() for m in markers}
        dictionary=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        params=cv2.aruco.DetectorParameters()
        # OpenCV's default is CORNER_REFINE_NONE; sub-pixel corners directly reduce pose jitter.
        params.cornerRefinementMethod=cv2.aruco.CORNER_REFINE_SUBPIX
        self.detector=cv2.aruco.ArucoDetector(dictionary,params)
        self.max_reprojection_px=max_reprojection_px
        self.min_marker_side_px=min_marker_side_px
        # Continuity limits are rates, so they mean the same at any frame rate.
        # Defaults equal the former 0.35 m / 25 deg per frame at 30 fps: they reject
        # IPPE flips and gross jumps, not ordinary head or camera motion.
        self.max_speed_m_s=max_speed_m_s
        self.max_turn_deg_s=max_turn_deg_s
        self.reacquire_frames=reacquire_frames
        self.previous:Optional[Estimate]=None
        self.candidates:list[Estimate]=[]
        self.rejected:Optional[str]=None

    def consistent(self,a:Estimate,b:Estimate) -> bool:
        """``a`` follows ``b``; untimed estimates are treated as NOMINAL_DT apart."""
        if a.timestamp_s is None or b.timestamp_s is None:dt=NOMINAL_DT
        else:dt=a.timestamp_s-b.timestamp_s
        if not dt>0:return False
        delta=float(np.linalg.norm(a.camera_position-b.camera_position))
        Ra,_=cv2.Rodrigues(a.rvec);Rb,_=cv2.Rodrigues(b.rvec)
        angle=float(math.degrees(math.acos(np.clip((np.trace(Ra@Rb.T)-1)/2,-1,1))))
        return delta<=self.max_speed_m_s*dt and angle<=self.max_turn_deg_s*dt

    def lose(self,reason:str,seed:Optional[Estimate]=None):
        self.rejected=reason;self.previous=None
        self.candidates=[] if seed is None else [seed]
        return None

    def track(self,frame,timestamp_s:Optional[float]=None) -> Optional[Estimate]:
        """``timestamp_s`` is the frame's presentation time; omit only for fixed-rate input."""
        self.camera.validate_frame(frame)
        est=self.fit_markers(*self.detector.detectMarkers(frame)[:2])
        if est is None:
            return None
        est.timestamp_s=timestamp_s
        if self.previous is not None:
            if not self.consistent(est,self.previous):
                # The new pose must earn acceptance like any other (re)acquisition.
                return self.lose('pose-jump',seed=est)
            self.previous=est;self.rejected=None
            return est
        # After start, loss or a jump, require consecutive mutually consistent
        # poses so a single (or alternating) IPPE flip is never shown.
        if self.candidates and not self.consistent(est,self.candidates[-1]):
            self.candidates=[]
        self.candidates.append(est)
        if len(self.candidates)<self.reacquire_frames:
            self.rejected='acquiring';return None
        self.candidates=[];self.previous=est;self.rejected=None
        return est

    def residuals(self,est:Estimate,ids,observed) -> dict:
        obj=np.vstack([self.points[i] for i in ids])
        img=np.vstack([observed[i] for i in ids])
        pixels=project_world(obj,est,self.camera).reshape(len(ids),4,2)
        rms=np.sqrt(np.mean(np.sum((pixels-img.reshape(len(ids),4,2))**2,axis=2),axis=1))
        return dict(zip(ids,rms.tolist()))

    def fit_subset(self,ids,observed) -> Optional[Estimate]:
        return fit_pose(np.vstack([self.points[i] for i in ids]),
                        np.vstack([observed[i] for i in ids]),self.camera)

    def consensus(self,ids,observed) -> list:
        """The unique largest subset (>= min_markers) whose joint fit every member obeys.

        Dropping the worst residual of a joint fit is NOT safe: a displaced marker
        drags the joint pose so the good markers show the largest residuals.
        Testing subsets directly avoids that masking; layouts are capped at
        MAX_MARKERS so this stays cheap. Returns [] when no subset passes or the
        largest passing subset is not unique (a marker indistinguishable from noise).
        """
        for size in range(len(ids),self.min_markers-1,-1):
            passing=[]
            for subset in combinations(ids,size):
                est=self.fit_subset(subset,observed)
                if est is not None and max(self.residuals(est,subset,observed).values())<=self.max_reprojection_px:
                    passing.append(list(subset))
            if passing:
                return passing[0] if len(passing)==1 else []
        return []

    def fit_markers(self,corners,ids) -> Optional[Estimate]:
        """Fit every consistent configured marker at once; on failure set ``rejected``."""
        seen=[] if ids is None else ids.ravel().tolist()
        observed={}
        for c,i in zip(corners,seen):
            # A repeated id (e.g. a second printed copy) cannot be assigned safely.
            if i in self.points and seen.count(i)==1:observed[i]=c.reshape(-1,2).astype(np.float64)
        if not observed:
            return self.lose('marker-not-visible')
        usable=[i for i in sorted(observed) if marker_side_px(observed[i])>=self.min_marker_side_px]
        if len(usable)<self.min_markers:
            return self.lose('insufficient-observation')
        used=self.consensus(usable,observed)
        if not used:
            return self.lose('markers-inconsistent' if self.min_markers>1 else 'insufficient-observation')
        est=self.fit_subset(used,observed)
        est.marker_pixels=min(marker_side_px(observed[i]) for i in used)
        est.markers_used=tuple(used)
        est.markers_dropped=tuple(i for i in usable if i not in used)
        return est


def project_world(points,pose:Estimate,camera:Camera) -> np.ndarray:
    pixels,_=cv2.projectPoints(np.asarray(points,dtype=np.float64).reshape(-1,3),
                               pose.rvec,pose.tvec,camera.matrix,camera.distortion)
    return pixels.reshape(-1,2)
