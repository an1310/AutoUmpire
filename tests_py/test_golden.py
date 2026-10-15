"""Cross-language guard: Python geometry/projection must match tests/fixtures/projection_golden.json.

tests/replay.test.js checks the browser code against the same file, so the plate,
zone and lens model cannot silently diverge between the two languages.
Regenerate (only for an intended change): python tests_py/test_golden.py --regenerate
"""
import json
import sys
import unittest
from pathlib import Path
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from autoumpire_cv.registration import Camera,Estimate,project_world
from autoumpire_cv.zone import PLATE_XZ,StrikeZone

FIXTURE=ROOT/'tests'/'fixtures'/'projection_golden.json'
# Skew is zero: OpenCV ignores K[0][1], and calibrateCamera never produces it.
CAMERA={'width':1920,'height':1080,'matrix':[[1450.,0.,955.],[0.,1440.,548.],[0.,0.,1.]],
        'distortion':[-0.31,0.11,0.0012,-0.0009,-0.018,0.012,0.003,0.002]}
RVEC=[2.2,0.05,-0.04]
TVEC=[1.0,0.3,2.0]  # zone toward the image edge, where the lens terms move it ~60 px
ZONE={'bottom_m':0.45,'top_m':1.05}


def compute():
    camera=Camera.from_config(CAMERA)
    zone=StrikeZone(**ZONE)
    pose=Estimate(np.array(RVEC,float).reshape(3,1),np.array(TVEC,float).reshape(3,1),0.0,0.0)
    return {'camera':CAMERA,'zone':ZONE,
            'world_to_camera':pose.world_to_camera.reshape(-1).tolist(),
            'plate_xz':[list(p) for p in PLATE_XZ],
            'zone_vertices':zone.corners.tolist(),
            'edges':[list(e) for e in zone.edges],
            'pixels':project_world(zone.corners,pose,camera).tolist()}


class GoldenProjection(unittest.TestCase):
    def test_python_matches_fixture(self):
        want=json.loads(FIXTURE.read_text());got=compute()
        np.testing.assert_allclose(got['plate_xz'],want['plate_xz'],atol=1e-12)
        np.testing.assert_allclose(got['zone_vertices'],want['zone_vertices'],atol=1e-12)
        self.assertEqual(sorted(map(sorted,got['edges'])),sorted(map(sorted,want['edges'])))
        np.testing.assert_allclose(got['world_to_camera'],want['world_to_camera'],atol=1e-12)
        np.testing.assert_allclose(got['pixels'],want['pixels'],atol=1e-6)

    def test_fixture_is_in_frame_and_distorted(self):
        want=json.loads(FIXTURE.read_text())
        px=np.array(want['pixels'])
        self.assertTrue(((px>=0)&(px<[1920,1080])).all())
        # The lens terms must actually matter, or the cross-check proves nothing.
        undistorted,_=cv2.projectPoints(np.array(want['zone_vertices']),np.array(RVEC),np.array(TVEC),
                                        np.array(CAMERA['matrix']),np.zeros(5))
        self.assertGreater(np.abs(undistorted.reshape(-1,2)-px).max(),20)


if __name__=='__main__':
    if '--regenerate' in sys.argv:
        FIXTURE.write_text(json.dumps(compute(),indent=1)+'\n');print('wrote',FIXTURE)
    else:
        unittest.main()
