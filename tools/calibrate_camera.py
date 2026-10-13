#!/usr/bin/env python3
"""Chessboard camera calibration. Keep camera focal length, crop and resolution fixed.

Example: python tools/calibrate_camera.py --images 'frames/*.jpg' \
  --inner-cols 9 --inner-rows 6 --square-mm 25 --output camera.json
"""
import argparse
import glob
import json
from pathlib import Path
import cv2
import numpy as np


def calibrate(paths,cols,rows,square_m):
    if cols<3 or rows<3 or square_m<=0:raise ValueError('Bad chessboard pattern')
    board=np.zeros((rows*cols,3),np.float32)
    board[:,:2]=np.mgrid[:cols,:rows].T.reshape(-1,2)*square_m
    obj=[];images=[];size=None
    for path in paths:
        im=cv2.imread(str(path))
        if im is None:continue
        sz=(im.shape[1],im.shape[0])
        if size is None:size=sz
        if size!=sz:raise ValueError('All images must share resolution')
        ok,corners=cv2.findChessboardCornersSB(cv2.cvtColor(im,cv2.COLOR_BGR2GRAY),(cols,rows))
        if ok:obj.append(board.copy());images.append(corners)
    if len(obj)<8:raise ValueError(f'Need >=8 valid checkerboard views; got {len(obj)}')
    error,K,D,_,_=cv2.calibrateCamera(obj,images,size,None,None)
    if not np.isfinite(error) or error>2.0:raise ValueError(f'High calibration RMS {error:.2f}px')
    return {'width':size[0],'height':size[1], 'matrix':K.tolist(),
            'distortion':D.ravel().tolist(), 'calibration_rms_px':float(error),
            'valid_views':len(obj)}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--images',required=True)
    p.add_argument('--inner-cols',type=int,default=9)
    p.add_argument('--inner-rows',type=int,default=6)
    p.add_argument('--square-mm',type=float,required=True)
    p.add_argument('--output',required=True)
    args=p.parse_args()
    conf=calibrate(sorted(glob.glob(args.images)),args.inner_cols,args.inner_rows,args.square_mm/1000)
    Path(args.output).write_text(json.dumps(conf,indent=2)+'\n')
    print(f"Camera calibration saved: {conf['valid_views']} frames, RMS {conf['calibration_rms_px']:.2f} px")

if __name__=='__main__':main()
