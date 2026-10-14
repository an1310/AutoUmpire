#!/usr/bin/env python3
"""Predict overlay error for a marker layout from a given viewpoint (Monte Carlo).

Plan a layout BEFORE printing: checks each marker is in frame and large enough,
then perturbs ideal corners with Gaussian pixel noise and reports how far the
projected strike-zone corners move. Synthetic only: real corner noise, lens model
error, rolling shutter and survey error are not modelled, so measured field error
will be worse. Use it to compare layouts, not to certify one.

Example (camera/eye 0.9 m behind plate, 1.35 m up, looking at the zone):
  python tools/simulate_registration.py --config field.json \
      --eye 0.3 1.35 0.9 --target 0 0.6 -0.5 --noise-px 0.3 1.0
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import cv2
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from autoumpire_cv.registration import Camera,PlateTracker,fit_pose,marker_side_px
from track_video import validate_config


def look_at(eye,target):
    """World-to-camera rotation/translation for a level camera (OpenCV axes)."""
    eye=np.asarray(eye,float);forward=np.asarray(target,float)-eye
    forward/=np.linalg.norm(forward)
    right=np.cross(forward,[0,1.,0])
    if np.linalg.norm(right)<1e-6:raise ValueError('Camera cannot look straight up/down')
    right/=np.linalg.norm(right);down=np.cross(forward,right)
    R=np.stack([right,down,forward]);return R,-R@eye


def simulate(camera:Camera,markers,zone,eye,target,noise_px,trials=1000,seed=0):
    R,T=look_at(eye,target);rvec,_=cv2.Rodrigues(R)
    tracker=PlateTracker(camera,markers)
    report={'markers':{},'noise':{}}
    visible=[]
    for m in markers:
        img,_=cv2.projectPoints(m.points(),rvec,T,camera.matrix,camera.distortion)
        img=img.reshape(4,2)
        cam_z=(m.points()@R.T+T)[:,2]
        inside=bool((cam_z>0).all() and (img[:,0]>=0).all() and (img[:,0]<camera.width).all()
                    and (img[:,1]>=0).all() and (img[:,1]<camera.height).all())
        side=marker_side_px(img) if inside else 0.0
        ok=inside and side>=tracker.min_marker_side_px
        report['markers'][m.marker_id]={'in_frame':inside,'side_px':round(side,1),'usable':ok}
        if ok:visible.append(m)
    if len(visible)<tracker.min_markers:
        report['error']=f'only {len(visible)} usable markers; tracker needs {tracker.min_markers}'
        return report
    obj=np.vstack([m.points() for m in visible])
    ideal,_=cv2.projectPoints(obj,rvec,T,camera.matrix,camera.distortion);ideal=ideal.reshape(-1,2)
    true_zone,_=cv2.projectPoints(zone.corners,rvec,T,camera.matrix,camera.distortion)
    true_zone=true_zone.reshape(-1,2)
    rng=np.random.default_rng(seed)
    for sigma in noise_px:
        errs=[];failed=0
        for _ in range(trials):
            est=fit_pose(obj,ideal+rng.normal(0,sigma,ideal.shape),camera)
            if est is None:failed+=1;continue
            pz,_=cv2.projectPoints(zone.corners,est.rvec,est.tvec,camera.matrix,camera.distortion)
            errs.append(np.max(np.linalg.norm(pz.reshape(-1,2)-true_zone,axis=1)))
        errs=np.asarray(errs) if errs else np.asarray([np.nan])
        report['noise'][sigma]={'zone_err_px_p50':round(float(np.median(errs)),2),
                                'zone_err_px_p95':round(float(np.percentile(errs,95)),2),
                                'pose_failures':failed/trials}
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--config',required=True,help='field.json with camera, marker(s) and zone')
    p.add_argument('--eye',type=float,nargs=3,required=True,metavar=('X','Y','Z'),help='Camera position, plate frame (m)')
    p.add_argument('--target',type=float,nargs=3,default=[0,.7,-.3],metavar=('X','Y','Z'))
    p.add_argument('--noise-px',type=float,nargs='+',default=[.3,1.])
    p.add_argument('--trials',type=int,default=1000)
    a=p.parse_args()
    camera,markers,zone=validate_config(json.loads(Path(a.config).read_text()))
    print(json.dumps(simulate(camera,markers,zone,a.eye,a.target,a.noise_px,a.trials),indent=2))

if __name__=='__main__':main()
