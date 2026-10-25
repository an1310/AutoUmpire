#!/usr/bin/env python3
"""Step 3: localize every video frame against the field map.

For each frame: SIFT features, ratio-test matches to the features of the 4
temporally nearest keyframes that have 3D map points, then LO-RANSAC absolute
pose with the map's (fisheye) camera. Frames are never assumed continuous, so
edit cuts and whip pans do not propagate errors; continuity is judged later.

  python experiments/field_map/localize.py --work runs/seg1 --video seg1.mp4

Keyframes are paired to video frames by image correlation, not by index/fps:
on the test clip ffmpeg's fps sampling ran ~0.1 s (6-7 frames) ahead of
OpenCV's frame numbering. Writes localized.json: per frame pose, matches, inliers.
"""
from __future__ import annotations
import argparse
import json
import time
from multiprocessing import Pool
from pathlib import Path
import cv2
import numpy as np
import pycolmap

G={}   # per-process state


def small_gray(img):
    return cv2.resize(cv2.cvtColor(img,cv2.COLOR_BGR2GRAY),(160,90)).astype(np.float32)


def ncc(a,b):
    a=(a-a.mean())/(a.std()+1e-6);b=(b-b.mean())/(b.std()+1e-6);return float((a*b).mean())


def keyframe_video_index(work:Path,video:Path,fps_kf:float):
    cap=cv2.VideoCapture(str(video));fps=cap.get(cv2.CAP_PROP_FPS);thumbs=[]
    while True:
        ok,f=cap.read()
        if not ok:break
        thumbs.append(small_gray(f))
    out={}
    for path in sorted((work/'images').glob('f*.jpg')):
        i=int(path.stem[1:]);k=small_gray(cv2.imread(str(path)));guess=int(round((i-1)*fps/fps_kf))
        cand=range(max(0,guess-15),min(len(thumbs),guess+16))
        scores=[ncc(k,thumbs[j]) for j in cand];best=int(np.argmax(scores))
        if scores[best]<0.95:raise SystemExit(f'{path.name}: no video frame matches (best correlation {scores[best]:.3f})')
        out[path.name]=list(cand)[best]
    return out,len(thumbs)


def build_keyframes(work:Path,mask,k2v):
    rec=pycolmap.Reconstruction(str(work/'sparse'/'0'));sift=cv2.SIFT_create(nfeatures=4096);kf=[]
    for im in rec.images.values():
        obs=[(p.xy,p.point3D_id) for p in im.points2D if p.has_point3D()]
        xy=(np.array([o[0] for o in obs])-0.5).astype(np.float32)   # COLMAP pixel centres are +0.5
        ids=np.array([o[1] for o in obs])
        kps,des=sift.detectAndCompute(cv2.cvtColor(cv2.imread(str(work/'images'/im.name)),cv2.COLOR_BGR2GRAY),mask)
        pts=np.array([k.pt for k in kps],np.float32)
        d2=((pts[:,None,:]-xy[None,:,:])**2).sum(-1);j=d2.argmin(1);ok=d2[np.arange(len(pts)),j]<4.0
        sel=ids[j[ok]]
        kf.append((k2v[im.name],des[ok],np.array([rec.points3D[i].xyz for i in sel]),sel,
                   np.array([rec.points3D[i].track.length() for i in sel])))
    kf.sort(key=lambda x:x[0])
    return next(iter(rec.cameras.values())),kf


def init(work,mask,k2v,max_error):
    G['camera'],G['kf']=build_keyframes(work,mask,k2v)
    G['times']=np.array([k[0] for k in G['kf']]);G['mask']=mask;G['max_error']=max_error
    G['sift']=cv2.SIFT_create(nfeatures=4096);G['bf']=cv2.BFMatcher(cv2.NORM_L2)


def localize(item):
    idx,frame=item
    kps,des=G['sift'].detectAndCompute(cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY),G['mask'])
    if des is None or len(kps)<20:return idx,None,0,0,0
    near=np.argsort(np.abs(G['times']-idx))[:4];kf=G['kf']
    D=np.vstack([kf[k][1] for k in near]);X=np.vstack([kf[k][2] for k in near])
    I=np.concatenate([kf[k][3] for k in near]);T=np.concatenate([kf[k][4] for k in near])
    best={}
    for m in G['bf'].knnMatch(des,D,k=2):
        if len(m)<2 or m[0].distance>0.8*m[1].distance:continue
        pid=I[m[0].trainIdx]
        if pid not in best or m[0].distance<best[pid][0]:best[pid]=(m[0].distance,m[0].queryIdx,m[0].trainIdx)
    if len(best)<12:return idx,None,len(best),0,0
    p2=np.array([kps[v[1]].pt for v in best.values()],np.float64)+0.5
    p3=np.array([X[v[2]] for v in best.values()])
    opts=pycolmap.AbsolutePoseEstimationOptions();opts.ransac.max_error=G['max_error']
    res=pycolmap.estimate_and_refine_absolute_pose(p2,p3,G['camera'],opts)
    if res is None:return idx,None,len(best),0,0
    pose=res['cam_from_world'];inl=np.asarray(res['inlier_mask'],bool)
    # How many keyframes saw the supporting map points: short tracks = weakly constrained map region.
    track=float(np.median(np.array([T[v[2]] for v in best.values()])[inl])) if inl.any() else 0.0
    return idx,(pose.rotation.matrix().tolist(),pose.translation.tolist()),len(best),int(res['num_inliers']),track


def frames(video):
    cap=cv2.VideoCapture(str(video));i=0
    while True:
        ok,f=cap.read()
        if not ok:return
        yield i,f;i+=1


def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--work',type=Path,required=True)
    p.add_argument('--video',type=Path,required=True)
    p.add_argument('--keyframe-fps',type=float,default=4.0)
    p.add_argument('--max-error',type=float,default=4.0,help='RANSAC inlier threshold, px')
    p.add_argument('--workers',type=int,default=4)
    a=p.parse_args()
    mask=cv2.imread(str(a.work/'mask.png'),cv2.IMREAD_GRAYSCALE)
    k2v,total=keyframe_video_index(a.work,a.video,a.keyframe_fps)
    (a.work/'keyframe_to_video.json').write_text(json.dumps(k2v,indent=0))
    t=time.time();out={}
    with Pool(a.workers,initializer=init,initargs=(a.work,mask,k2v,a.max_error)) as pool:
        for idx,pose,matches,inliers,track in pool.imap(localize,frames(a.video),chunksize=8):
            out[idx]={'pose':pose,'matches':matches,'inliers':inliers,'median_track':track}
            if idx%300==0:print(f'frame {idx}/{total}: {inliers} inliers ({time.time()-t:.0f}s)',flush=True)
    (a.work/'localized.json').write_text(json.dumps(out))
    print(f'localized {sum(v["pose"] is not None for v in out.values())}/{len(out)} frames in {time.time()-t:.0f}s')


if __name__=='__main__':
    main()
