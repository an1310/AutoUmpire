#!/usr/bin/env python3
"""Localize an independent video against a fixed COLMAP field map.

Uses original map SIFT descriptors and the same COLMAP extractor for queries.
OpenCV FLANN searches all mapped landmarks, independent of timestamps.
Ratio-test competitors must be different 3D landmarks, not repeated views of
the same point. Display gates remain in render_overlay.py.

  python experiments/field_map/localize.py --work runs/map --video query.mp4 \
      --output-dir runs/query

Query resolution must match the map. Writes localized.json (unchanged pose
schema) and localization_info.json. Reference images/frame pairing are not needed.
"""
from __future__ import annotations
import argparse
from contextlib import closing
import json
from multiprocessing import Pool
from pathlib import Path
import time
import sqlite3
import cv2
import numpy as np
import pycolmap

G = {}  # Per-worker extractor, index and pose-estimation options.
DESCRIPTOR_RATIO = .9


class MapIndex:
    """Map-wide search with one correspondence per 3D landmark."""

    def __init__(self, descriptors, point_ids, xyz, tracks):
        self.descriptors = np.ascontiguousarray(descriptors, dtype=np.float32)
        self.point_ids = np.asarray(point_ids)
        self.xyz = np.asarray(xyz, dtype=np.float64)
        self.tracks = np.asarray(tracks)
        self.distinct_points = len(np.unique(self.point_ids))
        self.matcher = cv2.FlannBasedMatcher(dict(algorithm=1, trees=4), dict(checks=128))
        if len(self.descriptors):
            self.matcher.add([self.descriptors])
            self.matcher.train()

    def correspondences(self, xy, descriptors):
        """Return query pixels, world points and track lengths for unique matches."""
        empty = (np.empty((0, 2)), np.empty((0, 3)), np.empty(0))
        if descriptors is None or not len(descriptors) or self.distinct_points < 2:
            return empty
        query = np.ascontiguousarray(descriptors, dtype=np.float32)
        pending = np.arange(len(query))
        count = min(32, len(self.descriptors))
        best = {}
        while len(pending):
            retry = []
            for query_idx, matches in zip(pending, self.matcher.knnMatch(query[pending], k=count)):
                first = matches[0]
                point_id = self.point_ids[first.trainIdx]
                other = next((m for m in matches[1:]
                              if self.point_ids[m.trainIdx] != point_id), None)
                if other is None:
                    # Long tracks can fill a neighbor list with ONE landmark.
                    # Expand only affected queries until a real rival is found.
                    if count < len(self.descriptors):
                        retry.append(query_idx)
                    continue
                if first.distance >= DESCRIPTOR_RATIO * other.distance:
                    continue
                if point_id not in best or first.distance < best[point_id][0]:
                    best[point_id] = (first.distance, query_idx, first.trainIdx)
            pending = np.asarray(retry, dtype=int)
            count = min(count * 4, len(self.descriptors))
        if not best:
            return empty
        query_rows = [m[1] for m in best.values()]
        map_rows = [m[2] for m in best.values()]
        return np.asarray(xy)[query_rows], self.xyz[map_rows], self.tracks[map_rows]


def load_map(work):
    """Read exact database observation indices, without pixel reassociation."""
    database = work/'database.db'
    if not database.is_file():
        raise ValueError(f'Map feature database is missing: {database}')
    rec = pycolmap.Reconstruction(str(work/'sparse'/'0'))
    if len(rec.cameras) != 1:
        raise ValueError('Expected a field map with exactly one camera')
    camera = next(iter(rec.cameras.values()))
    descriptors, ids, xyz, tracks = [], [], [], []
    # COLMAP's opener initializes SQLite schema and takes write locks even for
    # readers. Stdlib SQLite read-only mode supports immutable/shared maps.
    with closing(sqlite3.connect(database.resolve().as_uri()+'?mode=ro', uri=True)) as db:
        for image in sorted(rec.images.values(), key=lambda im: im.name):
            source = db.execute('SELECT name FROM images WHERE image_id=?', (image.image_id,)).fetchone()
            if source is None or source[0] != image.name:
                raise ValueError('Feature database does not belong to this reconstruction')
            observations = [(i, p.point3D_id) for i, p in enumerate(image.points2D)
                            if p.has_point3D()]
            if not observations:
                continue
            rows, point_ids = zip(*observations)
            # Native queries and database descriptors share COLMAP's quantized
            # RootSIFT representation, including its scale and observation rows.
            descriptor = db.execute('SELECT type, rows, cols, data FROM descriptors WHERE image_id=?',
                                    (image.image_id,)).fetchone()
            if (descriptor is None or descriptor[0] != pycolmap.FeatureExtractorType.SIFT.value
                    or descriptor[1:3] != (len(image.points2D), 128)
                    or descriptor[3] is None or len(descriptor[3]) != descriptor[1]*128):
                raise ValueError(f'{image.name}: missing or incompatible SIFT descriptors')
            data = np.frombuffer(descriptor[3], dtype=np.uint8).reshape(descriptor[1], 128)
            keypoint = db.execute('SELECT rows, cols, data FROM keypoints WHERE image_id=?',
                                  (image.image_id,)).fetchone()
            if (keypoint is None or keypoint[0] != len(image.points2D) or keypoint[1] < 2
                    or keypoint[2] is None or len(keypoint[2]) != keypoint[0]*keypoint[1]*4):
                raise ValueError(f'{image.name}: missing database observation rows')
            keypoints = np.frombuffer(keypoint[2], dtype=np.float32).reshape(keypoint[0], keypoint[1])
            expected = np.array([p.xy for p in image.points2D])
            if keypoints.shape[0] != len(expected) or not np.allclose(keypoints[:, :2], expected, rtol=0, atol=1e-3):
                raise ValueError(f'{image.name}: database observation rows differ from the reconstruction')
            descriptors.append(data[list(rows)].astype(np.float32))
            ids.extend(point_ids)
            xyz.extend(rec.points3D[p].xyz for p in point_ids)
            tracks.extend(rec.points3D[p].track.length() for p in point_ids)
    if len(set(ids)) < 12:
        raise ValueError('Map needs at least 12 distinct landmarks with SIFT descriptors')
    return camera, np.vstack(descriptors), np.asarray(ids), np.asarray(xyz), np.asarray(tracks)


def init(camera, descriptors, ids, xyz, tracks, mask, max_error, max_features):
    cv2.setNumThreads(1)
    options = pycolmap.FeatureExtractionOptions()
    options.num_threads = 1
    options.sift.max_num_features = max_features
    G['extractor'] = pycolmap.FeatureExtractor.create(options, device=pycolmap.Device.cpu)
    G['index'] = MapIndex(descriptors, ids, xyz, tracks)
    G['camera'], G['mask'] = camera, mask
    G['pose_options'] = pycolmap.AbsolutePoseEstimationOptions()
    G['pose_options'].ransac.max_error = max_error


def localize(item):
    idx, frame = item
    camera = G['camera']
    if frame.shape[:2] != (camera.height, camera.width):
        raise ValueError('Query frame resolution must match the map camera')
    bitmap = pycolmap.Bitmap.from_array(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
    keypoints, descriptors = G['extractor'].extract(bitmap)
    if not keypoints:
        return idx, None, 0, 0, 0
    xy = np.array([[p.x, p.y] for p in keypoints])
    # COLMAP features already use half-pixel centers. Only mask lookup needs
    # integer indices; the pose solver receives native xy unchanged.
    pixels = np.floor(xy).astype(int)
    keep = ((pixels[:, 0] >= 0) & (pixels[:, 0] < camera.width)
            & (pixels[:, 1] >= 0) & (pixels[:, 1] < camera.height))
    keep[keep] &= G['mask'][pixels[keep, 1], pixels[keep, 0]] > 0
    p2, p3, tracks = G['index'].correspondences(xy[keep], descriptors.data[keep])
    if len(p2) < 12:
        return idx, None, len(p2), 0, 0
    result = pycolmap.estimate_and_refine_absolute_pose(p2, p3, camera, G['pose_options'])
    if result is None:
        return idx, None, len(p2), 0, 0
    pose = result['cam_from_world']
    inliers = np.asarray(result['inlier_mask'], dtype=bool)
    track = float(np.median(tracks[inliers])) if inliers.any() else 0.
    return idx, (pose.rotation.matrix().tolist(), pose.translation.tolist()), len(p2), int(result['num_inliers']), track


def frames(video):
    cap = cv2.VideoCapture(str(video))
    try:
        if not cap.isOpened():
            raise ValueError(f'Cannot open query video: {video}')
        idx = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            yield idx, frame
            idx += 1
    finally:
        cap.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--work', type=Path, required=True, help='reference map directory')
    parser.add_argument('--video', type=Path, required=True, help='independent query video')
    parser.add_argument('--output-dir', type=Path, help='query results (default: --work)')
    parser.add_argument('--max-error', type=float, default=4., help='RANSAC threshold, pixels')
    parser.add_argument('--max-features', type=int, default=8192)
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    if args.workers < 1 or args.max_features < 12 or not np.isfinite(args.max_error) or args.max_error <= 0:
        parser.error('workers must be positive, max-features >= 12, max-error finite and positive')
    # Validate in the parent so a malformed map cannot cause worker respawns.
    map_data = load_map(args.work)
    camera = map_data[0]
    mask = cv2.imread(str(args.work/'mask.png'), cv2.IMREAD_GRAYSCALE)
    if mask is None or mask.shape != (camera.height, camera.width):
        parser.error('Map mask is missing or does not match the map camera')
    cap = cv2.VideoCapture(str(args.video))
    try:
        if not cap.isOpened():
            parser.error(f'Cannot open query video: {args.video}')
        size = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total, fps = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), cap.get(cv2.CAP_PROP_FPS)
    finally:
        cap.release()
    if size != (camera.width, camera.height):
        parser.error(f'Query is {size[0]}x{size[1]}; resize to map resolution {camera.width}x{camera.height} without cropping')
    output = args.output_dir or args.work
    output.mkdir(parents=True, exist_ok=True)
    started, records = time.monotonic(), {}
    with Pool(args.workers, initializer=init,
              initargs=(*map_data, mask, args.max_error, args.max_features)) as pool:
        for idx, pose, matches, inliers, track in pool.imap(localize, frames(args.video), chunksize=8):
            records[idx] = {'pose': pose, 'matches': matches, 'inliers': inliers, 'median_track': track}
            if idx % 300 == 0:
                print(f'frame {idx}/{total}: {inliers} inliers ({time.monotonic()-started:.0f}s)', flush=True)
        pool.close()
        pool.join()
    (output/'localized.json').write_text(json.dumps(records))
    info = {'reference_map': str(args.work.resolve()), 'query_video': str(args.video.resolve()),
            'method': 'COLMAP RootSIFT; map-wide FLANN; distinct-landmark ratio test',
            'width': camera.width, 'height': camera.height, 'fps': fps,
            'frames': len(records), 'max_features': args.max_features,
            'descriptor_ratio': DESCRIPTOR_RATIO,
            'max_error_px': args.max_error, 'seconds': time.monotonic()-started}
    (output/'localization_info.json').write_text(json.dumps(info, indent=2)+'\n')
    print(f'localized {sum(v["pose"] is not None for v in records.values())}/{len(records)} frames in {info["seconds"]:.0f}s')


if __name__ == '__main__':
    main()
