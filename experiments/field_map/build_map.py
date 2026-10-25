#!/usr/bin/env python3
"""Step 1: build a sparse 3D map of the field from umpire-POV video (COLMAP).

Samples keyframes from the video, masks burned-in overlays, and runs incremental
structure-from-motion with a single fisheye camera whose parameters COLMAP
estimates from the footage itself (no chessboard needed for a first map).

  python experiments/field_map/build_map.py --video seg1.mp4 --work runs/seg1 \
      --fps 4 --mask-box 0 0 475 62

Outputs in --work: images/ (keyframes), mask.png, database.db, sparse/0/ (map).
Experimental; see docs/experiments/field-map-umpire-pov.md for results and limits.
"""
from __future__ import annotations
import argparse
import subprocess
import time
from pathlib import Path
import cv2
import numpy as np
import pycolmap


def extract_keyframes(video:Path,images:Path,fps:float):
    images.mkdir(parents=True,exist_ok=True)
    subprocess.run(['ffmpeg','-y','-loglevel','error','-i',str(video),'-vf',f'fps={fps}',
                    '-q:v','2',str(images/'f%04d.jpg')],check=True)
    return sorted(images.glob('f*.jpg'))


def write_mask(path:Path,size,boxes):
    w,h=size
    mask=np.full((h,w),255,np.uint8)   # COLMAP ignores features where the mask is 0
    for x0,y0,x1,y1 in boxes:mask[y0:y1,x0:x1]=0
    cv2.imwrite(str(path),mask)


def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--video',type=Path,required=True)
    p.add_argument('--work',type=Path,required=True)
    p.add_argument('--fps',type=float,default=4.0,help='keyframes per second')
    p.add_argument('--mask-box',type=int,nargs=4,action='append',default=[],metavar=('X0','Y0','X1','Y1'),
                   help='pixel box to ignore (burned-in scoreboard etc.); repeatable')
    p.add_argument('--camera-model',default='RADIAL_FISHEYE')
    p.add_argument('--camera-params',default='',help='initial guess, e.g. "580,640,360,0,0"; default: COLMAP prior')
    p.add_argument('--max-features',type=int,default=4096)
    a=p.parse_args()
    a.work.mkdir(parents=True,exist_ok=True)
    frames=extract_keyframes(a.video,a.work/'images',a.fps)
    h,w=cv2.imread(str(frames[0])).shape[:2]
    write_mask(a.work/'mask.png',(w,h),a.mask_box)
    db=a.work/'database.db'
    if db.exists():db.unlink()
    t=time.time()
    reader=pycolmap.ImageReaderOptions();reader.camera_model=a.camera_model;reader.camera_mask_path=str(a.work/'mask.png')
    if a.camera_params:reader.camera_params=a.camera_params
    extraction=pycolmap.FeatureExtractionOptions();extraction.sift.max_num_features=a.max_features
    pycolmap.extract_features(db,a.work/'images',camera_mode=pycolmap.CameraMode.SINGLE,
                              reader_options=reader,extraction_options=extraction,device=pycolmap.Device.cpu)
    pairing=pycolmap.SequentialPairingOptions();pairing.overlap=15;pairing.loop_detection=False
    pycolmap.match_sequential(db,pairing_options=pairing,device=pycolmap.Device.cpu)
    out=a.work/'sparse';out.mkdir(exist_ok=True)
    models=pycolmap.incremental_mapping(db,a.work/'images',out)
    print(f'{len(frames)} keyframes, {time.time()-t:.0f}s')
    for k,r in sorted(models.items(),key=lambda kv:-kv[1].num_reg_images()):
        cam=next(iter(r.cameras.values()))
        print(f'model {k}: {r.num_reg_images()}/{len(frames)} registered, {r.num_points3D()} points, '
              f'mean reprojection {r.compute_mean_reprojection_error():.2f}px, camera {cam.model} {np.round(cam.params,4).tolist()}')


if __name__=='__main__':
    main()
