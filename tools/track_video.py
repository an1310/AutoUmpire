#!/usr/bin/env python3
"""Source-neutral registered strike-zone video and camera-pose log.

Usage:
 python tools/track_video.py --input clip.mp4 --config field.json \
     --output-video tracked.mp4 --output-json tracked.json

An ArUco marker with measured world offset anchors plate. No marker or
ambiguous pose -> no zone; camera reacquisition never predicts through gaps.
Optional MediaPipe batter ROI proposals must be explicitly enabled and are NOT
league-validated. Video output does not retain the original audio.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import cv2
import numpy as np

# Allow direct script execution without installing as a package.
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autoumpire_cv.registration import Camera,MarkerLocation,PlateTracker
from autoumpire_cv.plate import detect_plate
from autoumpire_cv.zone import StrikeZone
from autoumpire_cv.batter import StanceLock


def validate_config(config):
    camera=Camera.from_config(config['camera'])
    marker_data=config.get('marker')
    if not isinstance(marker_data,dict) or not all(k in marker_data for k in ('side_m','x_m','z_m')):
        raise ValueError('Marker dimensions and plate offset must be physically measured')
    marker=MarkerLocation(**marker_data)
    manual=StrikeZone(**config['zone'])
    return camera,marker,manual


def run(args):
    config=json.loads(Path(args.config).read_text())
    camera,marker,manual=validate_config(config)
    cap=cv2.VideoCapture(int(args.input) if args.input.isdigit() else args.input)
    if not cap.isOpened():raise RuntimeError(f'Cannot open camera/video: {args.input}')
    fps=cap.get(cv2.CAP_PROP_FPS) or 30.0
    writer=None; estimator=None
    poses=[]; diagnostics={}; lock=StanceLock()
    try:
        if args.output_video:
            path=Path(args.output_video)
            if not args.input.isdigit() and path.resolve()==Path(args.input).resolve():
                raise ValueError('Refusing overwrite of input video')
            writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'mp4v'),fps,
                                   (camera.width,camera.height))
            if not writer.isOpened():raise RuntimeError('Could not open output video')
        if args.auto_zone:
            if not config.get('accept_pose_proposals',False):
                raise ValueError('Automatic pose proposals require accept_pose_proposals=true in config')
            cfg=config.get('batter')
            if not cfg or not cfg.get('model_path') or not cfg.get('roi') or not cfg.get('height_m'):
                raise ValueError('batter.model_path, roi and height_m required with --auto-zone')
            from autoumpire_cv.pose_model import BatterEstimator
            estimator=BatterEstimator(cfg['model_path'],float(cfg['height_m']),tuple(cfg['roi']))
        tracker=PlateTracker(camera,marker)
        frame_index=0;active=manual
        while True:
            ok,frame=cap.read()
            if not ok:break
            camera.validate_frame(frame)
            if frame_index in args.reset_at:
                lock.reset();active=manual
            if estimator is not None and lock.locked is None:
                timestamp_ms=int(round(frame_index*1000/fps))
                suggestion=estimator.proposal(frame,timestamp_ms)
                accepted=lock.update(suggestion)
                if accepted is not None:
                    active=StrikeZone(accepted.bottom_m,accepted.top_m)
            pose=tracker.track(frame)
            if pose is None and args.allow_plate_contour:
                # Using a shape-based fallback can latch onto unrelated bright polygons.
                # Require explicit opt-in and still apply physical/reprojection gates.
                pose=detect_plate(frame,camera)
                if pose is not None and tracker.previous is not None:
                    # Tracker's continuity gate only applies between ArUco frames.
                    # Do not switch estimator sources without manual validation.
                    pose=None
            status=(tracker.rejected or 'no-pose') if pose is None else pose.method
            diagnostics[status]=diagnostics.get(status,0)+1
            if pose is not None:
                active.draw(frame,camera,pose)
                poses.append({'frame':frame_index,'timestamp_s':frame_index/fps,
                              'world_to_camera':pose.world_to_camera.reshape(-1).tolist(),
                              'zone':{'bottom_m':active.bottom_m,'top_m':active.top_m},
                              'source':pose.method,'reprojection_px':pose.reprojection_px})
            # Diagnostics are deliberately separate from the strike zone overlay.
            color=(80,220,90) if pose is not None else (50,75,235)
            cv2.putText(frame,f'AutoUmpire {status}'+(' [stance locked]' if lock.locked else ''),
                        (14,28),cv2.FONT_HERSHEY_SIMPLEX,.6,color,2,cv2.LINE_AA)
            if writer is not None:writer.write(frame)
            frame_index+=1
            if args.max_frames and frame_index>=args.max_frames:break
    finally:
        cap.release()
        if writer is not None:writer.release()
        if estimator is not None:estimator.close()
    result={'schema':'autoumpire-tracking-v1','source':args.input,
            'camera':{'width':camera.width,'height':camera.height,
                      'matrix':camera.matrix.tolist(),'distortion':camera.distortion.ravel().tolist()},
            'marker':vars(marker),'frames_processed':frame_index,'fps':fps,'poses':poses,
            'diagnostics':diagnostics,
            'limitations':['No marker/plate -> no overlay; no predictive extrapolation',
                           'Monocular pose and image landmarks lack validated real-world overlay accuracy',
                           'Manual marker offset + known camera intrinsics required',
                           'Video output has no audio track']}
    if args.output_json:Path(args.output_json).write_text(json.dumps(result,indent=2)+'\n')
    print(f"Processed {frame_index}; overlay {len(poses)} frames; hidden {frame_index-len(poses)}; reasons: {diagnostics}")
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True,help='Video file, camera index e.g. 0, or compatible stream URL')
    p.add_argument('--config',required=True,help='Camera intrinsics, marker location, manual zone, optional pose configuration')
    p.add_argument('--output-video',help='Annotated MP4; does not preserve audio')
    p.add_argument('--output-json',help='Per-frame accepted 6DoF poses and zones')
    p.add_argument('--max-frames',type=int,default=0)
    p.add_argument('--reset-at',type=int,nargs='*',default=[],help='Frames starting new batter/plate appearance')
    p.add_argument('--auto-zone',action='store_true',help='Opt in to MediaPipe proposal after stance stability gate')
    p.add_argument('--allow-plate-contour',action='store_true',help='Unvalidated white plate detection when marker absent')
    args=p.parse_args()
    if not(args.output_video or args.output_json):p.error('At least one output required')
    run(args)

if __name__=='__main__':main()
