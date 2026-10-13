#!/usr/bin/env python3
"""Render the same pentagonal zone on video using EXTERNALLY calibrated camera poses.

Usage:
  pip install opencv-python
  python tools/overlay_video.py input.mp4 calibration.json output.mp4

Calibration JSON example:
{
  "camera": {"fx": 1100, "fy": 1100, "cx": 960, "cy": 540},
  "zone": {"bottom_m": 0.39, "top_m": 0.95},
  "poses": [
    {"frame": 0, "world_to_camera": [1,0,0,0, 0,-1,0,0, 0,0,1,3, 0,0,0,1]}
  ]
}
A pose is REQUIRED per frame. No tracking or calibration is inferred.
Coordinates: X right, Y down, Z forward in CAMERA space; world frame in docs.
"""
import json
import sys
from pathlib import Path

INCH = 0.0254
HALF = 17 * INCH / 2
FOOT = [(-HALF,-HALF),(HALF,-HALF),(HALF,0),(0,HALF),(-HALF,0)]

def segments(bottom, top):
    if not 0 <= bottom < top <= 3:
        raise ValueError("Bad strike zone limits")
    points = [(x,y,z) for y in (bottom,top) for x,z in FOOT]
    edges=[]
    for i in range(5):
        j=(i+1)%5
        edges.extend(((i,j),(i+5,j+5),(i,i+5)))
    return points,edges

def project(point,m,c):
    x,y,z=point
    px=m[0]*x+m[1]*y+m[2]*z+m[3]
    py=m[4]*x+m[5]*y+m[6]*z+m[7]
    pz=m[8]*x+m[9]*y+m[10]*z+m[11]
    if pz <= .001: return None
    return (round(c["fx"]*px/pz+c["cx"]),round(c["fy"]*py/pz+c["cy"]))

def main():
    if len(sys.argv)!=4:
        raise SystemExit("Usage: overlay_video.py input.mp4 calibration.json output.mp4")
    try: import cv2
    except ImportError as exc: raise SystemExit("pip install opencv-python") from exc
    source,calfile,target=map(Path,sys.argv[1:])
    if source.resolve()==target.resolve(): raise SystemExit("Refusing input/output overwrite")
    conf=json.loads(calfile.read_text())
    c=conf["camera"]; z=conf["zone"]
    pts,edges=segments(float(z["bottom_m"]),float(z["top_m"]))
    poses={}
    for item in conf["poses"]:
        m=item["world_to_camera"]
        if len(m)!=16: raise ValueError("Pose matrix must be 16-element row-major")
        poses[int(item["frame"])]=m
    capture=cv2.VideoCapture(str(source))
    if not capture.isOpened(): raise SystemExit("Cannot open input")
    width=int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height=int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps=capture.get(cv2.CAP_PROP_FPS) or 30.0
    writer=cv2.VideoWriter(str(target),cv2.VideoWriter_fourcc(*"mp4v"),fps,(width,height))
    if not writer.isOpened(): raise SystemExit("Cannot open output")
    idx=0; missing=0
    try:
        while True:
            ok,frame=capture.read()
            if not ok: break
            m=poses.get(idx)
            if m is None:
                missing+=1
            else:
                pix=[project(p,m,c) for p in pts]
                for a,b in edges:
                    if pix[a] is not None and pix[b] is not None:
                        cv2.line(frame,pix[a],pix[b],(70,205,255),2,cv2.LINE_AA)
            writer.write(frame)
            idx+=1
    finally:
        capture.release(); writer.release()
    print(f"Processed {idx} frames; {missing} lacked camera poses (left unmarked).")
    print("Note: OpenCV VideoWriter does NOT preserve the original audio track.")

if __name__=="__main__":
    main()
