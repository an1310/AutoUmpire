#!/usr/bin/env python3
"""Generate 4x4 ArUco marker; print to exact physical side (include quiet border)."""
import argparse
import cv2

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--id',type=int,nargs='+',default=[0],help='One or more ids, e.g. --id 0 1 2 3 for a layout')
    p.add_argument('--pixels',type=int,default=800)
    p.add_argument('--output',default='aruco-id{id}.png',help='Path; {id} is replaced per marker')
    a=p.parse_args()
    if len(set(a.id))!=len(a.id):raise ValueError('Marker ids must be distinct')
    if len(a.id)>1 and '{id}' not in a.output:raise ValueError('--output needs {id} when generating several markers')
    d=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    for marker_id in a.id:
        if not 0<=marker_id<50:raise ValueError('DICT_4X4_50 marker id must be 0..49')
        image=cv2.aruco.generateImageMarker(d,marker_id,a.pixels)
        # White quiet zone does not count toward measured black-marker width.
        quiet=cv2.copyMakeBorder(image,a.pixels//8,a.pixels//8,a.pixels//8,a.pixels//8,cv2.BORDER_CONSTANT,value=255)
        out=a.output.replace('{id}',str(marker_id))
        if not cv2.imwrite(out,quiet):raise IOError(out)
        print(f'Generated {out}; measure BLACK EDGE printed size with ruler.')
if __name__=='__main__':main()
