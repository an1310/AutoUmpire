#!/usr/bin/env python3
"""Step 2: anchor the field map to home-plate coordinates (and metres).

The map from build_map.py has arbitrary position, orientation and scale. This
fits the ground plane, projects hand-marked plate corners from several frames
onto it, checks they agree, takes scale from the plate's 17-inch front edge and
fits the regulation pentagon.

Annotation JSON: {"<keyframe name>": [[x,y] x5], ...} in pixels, corner order
front_left, front_right, right_side_bottom, back_tip, left_side_bottom as seen
from the catcher's side (left = third-base side).

  python experiments/field_map/anchor_plate.py --work runs/seg1 --annotations plate.json

Writes anchor.json: ground plane, metres per map unit, world_from_plate (map
units; plate frame x=1st-base side, y=up, z=toward catcher) and consistency stats.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
import numpy as np
import pycolmap

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from autoumpire_cv.zone import PLATE_XZ  # noqa: E402

FRONT_EDGE_M=17*0.0254


def ground_plane(points,camera_centres,threshold,iters=3000,seed=0):
    """RANSAC plane; normal oriented toward the cameras (up)."""
    rng=np.random.default_rng(seed);best=None
    for _ in range(iters):
        a,b,c=points[rng.choice(len(points),3,replace=False)]
        n=np.cross(b-a,c-a);norm=np.linalg.norm(n)
        if norm<1e-12:continue
        n/=norm;d=-n@a;inliers=int((np.abs(points@n+d)<threshold).sum())
        if best is None or inliers>best[0]:best=(inliers,n,d)
    count,n,d=best
    if np.median(camera_centres@n+d)<0:n,d=-n,-d
    return n,d,count/len(points)


def centre(image):
    pose=image.cam_from_world();R=pose.rotation.matrix()
    return -R.T@pose.translation


def to_ground(image,camera,pixels,n,d):
    pose=image.cam_from_world();R=pose.rotation.matrix();C=-R.T@pose.translation
    xy=camera.cam_from_img(np.asarray(pixels,float))
    rays=np.c_[xy,np.ones(len(xy))]@R          # world directions
    t=-(C@n+d)/(rays@n)
    if np.any(t<=0):raise ValueError(f'{image.name}: a marked corner does not hit the ground in front of the camera')
    return C+rays*t[:,None]


def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--work',type=Path,required=True)
    p.add_argument('--annotations',type=Path,required=True)
    p.add_argument('--plane-threshold',type=float,default=0.05,help='map units')
    a=p.parse_args()
    rec=pycolmap.Reconstruction(str(a.work/'sparse'/'0'));camera=next(iter(rec.cameras.values()))
    images={im.name:im for im in rec.images.values()}
    pts=np.array([q.xyz for q in rec.points3D.values()]);C=np.array([centre(im) for im in images.values()])
    n,d,frac=ground_plane(pts,C,a.plane_threshold)
    ann={k:v for k,v in json.loads(a.annotations.read_text()).items() if k in images}
    if len(ann)<2:raise SystemExit('need plate corners in at least 2 registered keyframes')
    P=np.stack([to_ground(images[k],camera,v,n,d) for k,v in ann.items()])   # frames x 5 x 3
    front=np.linalg.norm(P[:,1]-P[:,0],axis=1).mean();unit_m=FRONT_EDGE_M/front
    # In-plane basis with the plate model's handedness: (u, n, v) ~ (x, y, z).
    u=np.cross(n,[0.,0.,1.]);u/=np.linalg.norm(u);v=np.cross(u,n)
    mean=P.mean(0);q=np.c_[mean@u,mean@v]
    ref=np.array(PLATE_XZ)/unit_m
    rc,qc=ref-ref.mean(0),q-q.mean(0);U,_,Vt=np.linalg.svd(rc.T@qc);R2=(U@Vt).T
    if np.linalg.det(R2)<0:
        raise SystemExit('plate fits only as a mirror image: check left/right corner labels')
    t2=q.mean(0)-ref.mean(0)@R2.T;fitted=ref@R2.T+t2
    origin2=t2                               # plate (0,0) in plane coords
    x_dir=R2@[1,0];z_dir=R2@[0,1]
    X=x_dir[0]*u+x_dir[1]*v;Z=z_dir[0]*u+z_dir[1]*v;O=origin2[0]*u+origin2[1]*v-d*n
    world_from_plate=np.eye(4);world_from_plate[:3,0]=X;world_from_plate[:3,1]=n;world_from_plate[:3,2]=Z;world_from_plate[:3,3]=O
    cm=lambda x:round(float(100*unit_m*x),1)
    centres={k:cm(np.linalg.norm(P[i].mean(0)-mean.mean(0))) for i,k in enumerate(ann)}
    spread=np.linalg.norm(P-mean,axis=2)
    result={'ground_plane':[*n.tolist(),float(d)],'ground_inlier_fraction':round(frac,3),
            'metres_per_unit':unit_m,'world_from_plate':world_from_plate.tolist(),
            'annotated_frames':list(ann),
            'plate_centre_offset_cm':centres,
            'corner_spread_cm':{'rms':cm(np.sqrt((spread**2).mean())),'max':cm(spread.max())},
            'regulation_fit_residual_cm':[cm(e) for e in np.linalg.norm(fitted-q,axis=1)],
            'camera_height_m':{'median':round(float(np.median(C@n+d)*unit_m),2),
                               'p5':round(float(np.percentile(C@n+d,5)*unit_m),2)}}
    (a.work/'anchor.json').write_text(json.dumps(result,indent=1)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('world_from_plate','ground_plane')},indent=1))


if __name__=='__main__':
    main()
