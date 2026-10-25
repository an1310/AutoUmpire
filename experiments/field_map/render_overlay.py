#!/usr/bin/env python3
"""Step 4: draw the strike zone on every frame from the localized poses, fail-closed.

A frame shows the zone only if its pose has enough RANSAC inliers, its support
comes from well-constrained map points (median track length), and it continues
the previous accepted pose within speed/turn limits; after a jump (edit cut,
whip pan) it must be re-acquired over consecutive consistent frames.

  python experiments/field_map/render_overlay.py --work runs/seg1 --video seg1.mp4 \
      --output overlay.mp4 --zone 0.40 0.80

Use --localizations runs/query/localized.json for an independent query video.
Writes the video (no audio), overlay_stats.json and slip.json beside --output. Zone heights are
inputs, not measurements of the batter.

Slip: between consecutive shown frames, ground points in front of the plate are
projected with both poses and followed in the image by optical flow; the median
disagreement (px) is how much the overlay swims relative to the field. It sees
frame-to-frame error only: a constant offset of the whole map is invisible to it.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
import cv2
import numpy as np
import pycolmap

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from autoumpire_cv.zone import PLATE_XZ  # noqa: E402


class Gate:
    """Continuity gate on camera poses in metres; same limits as PlateTracker's consistent/lose."""
    def __init__(self,max_speed=10.5,max_turn_deg=750.0,reacquire=3):
        self.max_speed,self.max_turn,self.reacquire=max_speed,max_turn_deg,reacquire
        self.previous=None;self.candidates=[]

    def consistent(self,a,b):
        dt=a[0]-b[0]
        if dt<=0:return False
        angle=np.degrees(np.arccos(np.clip((np.trace(a[1]@b[1].T)-1)/2,-1,1)))
        return np.linalg.norm(a[2]-b[2])<=self.max_speed*dt and angle<=self.max_turn*dt

    def lose(self,seed=None):
        self.previous=None;self.candidates=[] if seed is None else [seed]

    def accept(self,obs):
        """obs = (t, R, centre_m) or None. Returns (shown, reason)."""
        if obs is None:
            self.lose();return False,'no-pose'
        if self.previous is not None:
            if self.consistent(obs,self.previous):
                self.previous=obs;return True,'tracking'
            self.lose(seed=obs);return False,'pose-jump'
        if self.candidates and not self.consistent(obs,self.candidates[-1]):self.candidates=[]
        self.candidates.append(obs)
        if len(self.candidates)<self.reacquire:return False,'acquiring'
        self.previous=obs;self.candidates=[];return True,'tracking'


def zone_segments(bottom,top):
    base=[np.array([x,0,z]) for x,z in PLATE_XZ];up=np.array([0,1,0])
    lo=[b+up*bottom for b in base];hi=[b+up*top for b in base]
    plate=[(base[i],base[(i+1)%5]) for i in range(5)]
    zone=[(lo[i],lo[(i+1)%5]) for i in range(5)]+[(hi[i],hi[(i+1)%5]) for i in range(5)]+[(lo[i],hi[i]) for i in range(5)]
    return plate,zone


def project(camera,R,t,X):
    Xc=X@R.T+t;pix=np.full((len(X),2),np.nan);ok=Xc[:,2]>1e-3
    if ok.any():pix[ok]=camera.img_from_cam(Xc[ok]/Xc[ok,2:3])-0.5   # back to OpenCV pixel centres
    return pix


def ground_slip(gray0,gray1,p0,p1,mask,size,min_points=8):
    """Frame-to-frame overlay slip: how far the pose-projected ground grid moves differently
    from the image content under it. Optical flow (forward-backward checked) follows the
    ground; the median disagreement with the next pose's projection is the slip in px.
    Returns [] when too few ground points are visible and trackable."""
    w,h=size;ok=np.isfinite(p0).all(1)&np.isfinite(p1).all(1)
    ok&=(p0[:,0]>=8)&(p0[:,0]<w-8)&(p0[:,1]>=8)&(p0[:,1]<h-8)
    ok[ok]&=mask[p0[ok,1].astype(int),p0[ok,0].astype(int)]>0
    if ok.sum()<min_points:return []
    a=p0[ok].astype(np.float32).reshape(-1,1,2);lk=dict(winSize=(21,21),maxLevel=3)
    b,st,_=cv2.calcOpticalFlowPyrLK(gray0,gray1,a,None,**lk)
    back,st2,_=cv2.calcOpticalFlowPyrLK(gray1,gray0,b,None,**lk)
    good=(st.ravel()==1)&(st2.ravel()==1)&(np.linalg.norm((back-a).reshape(-1,2),axis=1)<0.5)
    if good.sum()<min_points:return []
    return [float(np.median(np.linalg.norm(b.reshape(-1,2)[good]-p1[ok][good],axis=1)))]


def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--work',type=Path,required=True)
    p.add_argument('--video',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--localizations',type=Path,help='query poses (default: --work/localized.json)')
    p.add_argument('--zone',type=float,nargs=2,default=[0.40,0.80],metavar=('BOTTOM_M','TOP_M'))
    p.add_argument('--min-inliers',type=int,default=60)
    p.add_argument('--min-track',type=float,default=5.0,
                   help='median keyframes seeing the inlier map points (5: tuned on ONE bad stretch; unvalidated)')
    a=p.parse_args()
    if a.output.resolve()==a.video.resolve():p.error('Output must not overwrite the input video')
    anchor=json.loads((a.work/'anchor.json').read_text())
    loc=json.loads((a.localizations or a.work/'localized.json').read_text())
    camera=next(iter(pycolmap.Reconstruction(str(a.work/'sparse'/'0')).cameras.values()))
    mask=cv2.imread(str(a.work/'mask.png'),cv2.IMREAD_GRAYSCALE)
    unit=anchor['metres_per_unit'];world_from_plate=np.array(anchor['world_from_plate'])
    # plate metres -> map units -> world
    M=world_from_plate.copy();M[:3,:3]=M[:3,:3]/unit
    plate,zone=zone_segments(*a.zone)
    centre_plate=np.array([0.0,0.0,0.0])
    cap=cv2.VideoCapture(str(a.video));fps=cap.get(cv2.CAP_PROP_FPS)
    w,h=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if not cap.isOpened() or not np.isfinite(fps) or fps<=0:
        cap.release();p.error('Cannot open query video with a valid frame rate')
    if (w,h)!=(camera.width,camera.height) or mask is None or mask.shape!=(h,w):
        cap.release();p.error('Query video and map mask must match the map camera resolution')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    out=cv2.VideoWriter(str(a.output),cv2.VideoWriter_fourcc(*'mp4v'),fps,(w,h))
    if not out.isOpened():
        cap.release();p.error('Cannot open output video')
    gate=Gate();stats={'reasons':{},'shown':0,'frames':0};slip=[];idx=0
    to_world=lambda X:np.c_[X,np.ones(len(X))]@M.T[:,:3]
    # Ground grid over the dirt in front of the plate (x +-3 m, 10 m toward the mound): wide
    # enough that the catcher and batter cover a minority of it (a ring hugging the plate is
    # mostly catcher from the umpire's eye, and flow then follows the catcher, not the ground).
    gx,gz=np.meshgrid(np.arange(-3,3.01,0.5),np.arange(-10,1.01,0.5))
    grid=to_world(np.c_[gx.ravel(),np.zeros(gx.size),gz.ravel()])
    prev=None   # (gray, projected grid) of the previous shown frame
    while True:
        ok,frame=cap.read()
        if not ok:break
        gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
        rec=loc.get(str(idx),{'pose':None});obs=None;reason=None
        if rec['pose'] is None:reason='no-pose'
        elif rec['inliers']<a.min_inliers:reason='few-inliers'
        elif rec.get('median_track',99)<a.min_track:reason='weak-map-support'
        else:
            R=np.array(rec['pose'][0]);t=np.array(rec['pose'][1])
            obs=(idx/fps,R,(-R.T@t)*unit)
        shown,why=gate.accept(obs)
        reason=reason or why
        stats['reasons'][reason]=stats['reasons'].get(reason,0)+1
        if shown:
            stats['shown']+=1
            grid_px=project(camera,R,t,grid)
            if prev is not None:slip.extend((idx,v) for v in ground_slip(prev[0],gray,prev[1],grid_px,mask,(w,h)))
            prev=(gray,grid_px)
            for segs,col in ((plate,(0,255,0)),(zone,(0,215,255))):
                for s0,s1 in segs:
                    pts=project(camera,R,t,to_world(np.linspace(s0,s1,20)))   # sample: fisheye bends edges
                    pts=pts[~np.isnan(pts).any(1)]
                    if len(pts)>1:cv2.polylines(frame,[np.rint(pts).astype(np.int32).reshape(-1,1,2)],False,col,2,cv2.LINE_AA)
            c=project(camera,R,t,to_world(centre_plate[None]))[0]
            if np.isfinite(c).all() and 0<=c[0]<w and 0<=c[1]<h:stats['plate_in_view_frames']=stats.get('plate_in_view_frames',0)+1
        else:prev=None
        label=f'{idx/fps:6.2f}s  {"ZONE" if shown else "HIDDEN"}  {reason}  inliers {rec.get("inliers",0)}'
        cv2.putText(frame,label,(12,h-14),cv2.FONT_HERSHEY_SIMPLEX,.6,(0,0,0),4,cv2.LINE_AA)
        cv2.putText(frame,label,(12,h-14),cv2.FONT_HERSHEY_SIMPLEX,.6,(0,255,0) if shown else (0,80,255),1,cv2.LINE_AA)
        out.write(frame);idx+=1
    cap.release();out.release()
    stats['frames']=idx
    if slip:
        s=np.array([v for _,v in slip]);stats['slip_px']={'frame_pairs':len(s),'median':round(float(np.median(s)),2),
                                          'p95':round(float(np.percentile(s,95)),2),'max':round(float(s.max()),2)}
    (a.output.parent/'slip.json').write_text(json.dumps(slip))
    (a.output.parent/'overlay_stats.json').write_text(json.dumps(stats,indent=1)+'\n')
    print(json.dumps(stats,indent=1))


if __name__=='__main__':
    main()
