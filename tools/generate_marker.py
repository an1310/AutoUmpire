#!/usr/bin/env python3
"""Generate 4x4 ArUco marker; print to exact physical side (include quiet border)."""
import argparse
import cv2

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--id',type=int,default=0)
    p.add_argument('--pixels',type=int,default=800)
    p.add_argument('--output',default='aruco-id0.png')
    a=p.parse_args()
    if not 0<=a.id<50:raise ValueError('DICT_4X4_50 marker id must be 0..49')
    d=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    image=cv2.aruco.generateImageMarker(d,a.id,a.pixels)
    # White quiet zone does not count toward measured black-marker width.
    quiet=cv2.copyMakeBorder(image,a.pixels//8,a.pixels//8,a.pixels//8,a.pixels//8,cv2.BORDER_CONSTANT,value=255)
    if not cv2.imwrite(a.output,quiet):raise IOError(a.output)
    print(f'Generated {a.output}; measure BLACK EDGE printed size with ruler.')
if __name__=='__main__':main()
