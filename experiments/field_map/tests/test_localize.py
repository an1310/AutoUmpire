"""Synthetic map regressions; no game imagery or learned weights required."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import cv2
import numpy as np
import pycolmap

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import localize


class MapMatching(unittest.TestCase):
    def index(self, descriptors, ids):
        self.assertTrue(hasattr(localize, 'MapIndex'),
                        'Localization needs a timestamp-independent map index')
        xyz = np.column_stack([ids, np.zeros(len(ids)), np.full(len(ids), 5.)])
        return localize.MapIndex(descriptors, np.asarray(ids), xyz,
                                 np.full(len(ids), 10.))

    def test_searches_landmarks_beyond_the_first_reference_frames(self):
        rng = np.random.default_rng(7)
        descriptors = rng.uniform(0, 100, (2048, 128)).astype(np.float32)
        index = self.index(descriptors, np.arange(2048))
        xy = np.column_stack([np.arange(64), np.ones(64)])
        p2, p3, tracks = index.correspondences(xy, descriptors[-64:].copy())
        self.assertEqual(len(p2), 64)
        np.testing.assert_array_equal(p3[:, 0], np.arange(1984, 2048))
        np.testing.assert_array_equal(tracks, np.full(64, 10.))

    def test_repeated_observations_do_not_make_one_landmark_ambiguous(self):
        rng = np.random.default_rng(8)
        unique = rng.uniform(0, 100, (64, 128)).astype(np.float32)
        # More than 32 nearest descriptors can be observations of ONE point.
        descriptors = np.vstack([np.repeat(unique[:1], 80, axis=0), unique[1:]])
        ids = np.r_[np.zeros(80, dtype=int), np.arange(1, 64)]
        index = self.index(descriptors, ids)
        p2, p3, _ = index.correspondences(np.array([[123., 234.]]), unique[:1])
        np.testing.assert_array_equal(p2, [[123., 234.]])
        np.testing.assert_array_equal(p3, [[0., 0., 5.]])

    def test_identical_descriptors_at_different_landmarks_are_rejected(self):
        descriptor = np.full((1, 128), 30., np.float32)
        index = self.index(np.repeat(descriptor, 2, axis=0), [10, 20])
        p2, _, _ = index.correspondences(np.array([[12., 23.]]), descriptor)
        self.assertEqual(len(p2), 0)

    def test_a_landmark_cannot_supply_two_pose_correspondences(self):
        rng = np.random.default_rng(9)
        descriptors = rng.uniform(0, 100, (64, 128)).astype(np.float32)
        index = self.index(descriptors, np.arange(64))
        queries = np.vstack([descriptors[0] + .01, descriptors[0]])
        p2, p3, _ = index.correspondences(np.array([[10., 20.], [30., 40.]]), queries)
        np.testing.assert_array_equal(p2, [[30., 40.]])
        self.assertEqual(len(p3), 1)


def synthetic_map(work):
    """Independent pinhole projection plus real COLMAP keypoints/descriptors."""
    rng = np.random.default_rng(42)
    gray = rng.integers(0, 256, (384, 512), dtype=np.uint8)
    gray = cv2.GaussianBlur(gray, (3, 3), .6)
    options = pycolmap.FeatureExtractionOptions()
    options.num_threads = 1
    extractor = pycolmap.FeatureExtractor.create(options, device=pycolmap.Device.cpu)
    keypoints, descriptors = extractor.extract(pycolmap.Bitmap.from_array(gray))
    xy = np.array([[k.x, k.y] for k in keypoints])
    depth = rng.uniform(4, 8, len(xy))
    xyz = np.column_stack([(xy[:, 0]-256)*depth/500,
                           (xy[:, 1]-192)*depth/500, depth])
    model = work/'sparse'/'0'
    model.mkdir(parents=True)
    (model/'cameras.txt').write_text('1 PINHOLE 512 384 500 500 256 192\n')
    observations = ' '.join(f'{x} {y} {i+1}' for i, (x, y) in enumerate(xy))
    (model/'images.txt').write_text('1 1 0 0 0 0 0 0 1 reference.jpg\n'+observations+'\n')
    (model/'points3D.txt').write_text(''.join(
        f'{i+1} {x} {y} {z} 100 100 100 0 1 {i}\n'
        for i, (x, y, z) in enumerate(xyz)))
    db = pycolmap.Database.open(work/'database.db')
    try:
        camera = pycolmap.Camera(camera_id=1, model='PINHOLE', width=512,
                                 height=384, params=[500, 500, 256, 192])
        db.write_camera(camera, use_camera_id=True)
        db.write_image(pycolmap.Image(image_id=1, camera_id=1, name='reference.jpg'),
                       use_image_id=True)
        db.write_keypoints(1, xy.astype(np.float32))
        db.write_descriptors(1, descriptors)
    finally:
        db.close()
    cv2.imwrite(str(work/'mask.png'), np.full(gray.shape, 255, np.uint8))
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


class SeparateVideo(unittest.TestCase):
    def test_reference_feature_database_can_be_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            synthetic_map(root)
            database = root/'database.db'
            database.chmod(0o444)
            try:
                data = localize.load_map(root)
                self.assertGreater(len(data[1]), 100)
            finally:
                database.chmod(0o644)

    def test_rejects_a_feature_database_with_different_observation_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            synthetic_map(root)
            path = root/'sparse'/'0'/'images.txt'
            lines = path.read_text().splitlines()
            observations = lines[1].split()
            observations[0] = str(float(observations[0]) + 10)
            path.write_text(lines[0]+'\n'+' '.join(observations)+'\n')
            with self.assertRaisesRegex(ValueError, 'observation'):
                localize.load_map(root)

    def test_renders_separate_results_without_overwriting_the_reference_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            frame = synthetic_map(root)
            video = root/'query.avi'
            writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'MJPG'), 30, (512, 384))
            self.assertTrue(writer.isOpened())
            for _ in range(4):
                writer.write(frame)
            writer.release()
            transform = np.eye(4)
            transform[:3, 3] = [0, 0, 5]
            (root/'anchor.json').write_text(json.dumps({
                'metres_per_unit': 1, 'world_from_plate': transform.tolist()}))
            output = root/'query-results'
            output.mkdir()
            poses = {i: {'pose': [np.eye(3).tolist(), [0, 0, 0]],
                         'inliers': 100, 'median_track': 10} for i in range(4)}
            (output/'localized.json').write_text(json.dumps(poses))
            result = subprocess.run([sys.executable,
                                     str(Path(localize.__file__).with_name('render_overlay.py')),
                                     '--work', str(root), '--video', str(video),
                                     '--localizations', str(output/'localized.json'),
                                     '--output', str(output/'overlay.mp4')],
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            stats = json.loads((output/'overlay_stats.json').read_text())
            self.assertEqual(stats['frames'], 4)
            self.assertEqual(stats['shown'], 2)  # Existing three-frame reacquisition.
            self.assertFalse((root/'overlay_stats.json').exists())
            # Rerendering the same destination must replace every result sidecar.
            (output/'slip.json').write_text('[[999, 123.0]]')
            (output/'localized.json').write_text(json.dumps({
                i: {'pose': None} for i in range(4)}))
            hidden = subprocess.run([sys.executable,
                                     str(Path(localize.__file__).with_name('render_overlay.py')),
                                     '--work', str(root), '--video', str(video),
                                     '--localizations', str(output/'localized.json'),
                                     '--output', str(output/'overlay.mp4')],
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(hidden.returncode, 0, hidden.stderr)
            self.assertEqual(json.loads((output/'slip.json').read_text()), [])

    def test_localizes_a_separate_video_without_reference_images_or_timestamps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            frame = synthetic_map(root)
            video = root/'query.avi'
            writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'MJPG'), 30, (512, 384))
            self.assertTrue(writer.isOpened())
            unrelated = np.random.default_rng(99).integers(0, 256, frame.shape, dtype=np.uint8)
            for image in [frame, frame, np.zeros_like(frame), unrelated]:
                writer.write(image)
            writer.release()
            # No images/ directory and a query video unrelated to map filenames.
            output = root/'query-results'
            result = subprocess.run([sys.executable, str(Path(localize.__file__)),
                                     '--work', str(root), '--video', str(video),
                                     '--output-dir', str(output), '--workers', '1'],
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads((output/'localized.json').read_text())
            self.assertEqual(len(data), 4)
            self.assertGreater(data['0']['inliers'], 100)
            self.assertIsNone(data['2']['pose'])
            self.assertLess(data['3']['inliers'], 60)  # Unrelated texture must not earn an overlay.
            R, t = data['0']['pose']
            np.testing.assert_allclose(R, np.eye(3), atol=.003)
            np.testing.assert_allclose(t, [0, 0, 0], atol=.015)


if __name__ == '__main__':
    unittest.main()
