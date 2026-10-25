"""Regression tests on real practice footage (iPhone HLG HDR, youth field at night).

Fixtures are full 1080x1920 frames with people blurred (tests_py/fixtures/practice).
The camera is UNCALIBRATED (focal length estimated from the plate), so these tests
pin detection behavior and pose consistency, not absolute accuracy.
"""
import json
from dataclasses import replace
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from autoumpire_cv.registration import Camera,MarkerLocation,PlateTracker,fit_pose
from autoumpire_cv.plate import WORLD,contour_candidates,detect_plate,order_pentagon
from autoumpire_cv.video import open_video,probe,tonemap_available

FIXTURES=ROOT/'tests_py'/'fixtures'/'practice'
MANIFEST=json.loads((FIXTURES/'manifest.json').read_text())
CAMERA=Camera.from_config(MANIFEST['camera'])


def fixture(name):
    entry=next(f for f in MANIFEST['fixtures'] if f['file']==name+'.jpg')
    return cv2.imread(str(FIXTURES/entry['file'])),entry


class PracticeFootage(unittest.TestCase):
    def test_each_fixture_detects_or_hides_as_recorded(self):
        for entry in MANIFEST['fixtures']:
            with self.subTest(entry['file']):
                est=detect_plate(cv2.imread(str(FIXTURES/entry['file'])),CAMERA)
                if not entry['expect_plate']:
                    self.assertIsNone(est,'occluded plate must not produce a pose')
                    continue
                self.assertIsNotNone(est)
                C=est.camera_position
                self.assertLess(np.linalg.norm(C-entry['camera_position']),0.03)
                # Handheld phone behind the catcher: physically plausible pose.
                self.assertTrue(0.8<C[1]<1.8 and 0.8<C[2]<2.5 and abs(C[0])<0.5,C)

    def test_tone_mapped_and_raw_hdr_agree(self):
        a=detect_plate(fixture('IMG_0749_tonemap_290')[0],CAMERA)
        b=detect_plate(fixture('IMG_0749_raw_290')[0],CAMERA)
        self.assertLess(np.linalg.norm(a.camera_position-b.camera_position),0.05)

    def sliver_and_plate(self):
        """Frame 72: the plate, and a small bright sliver with lower PIXEL error."""
        frame,entry=fixture('IMG_0749_tonemap_72')
        fits=[]
        for pts in contour_candidates(frame):
            ordered=order_pentagon(pts)
            est=fit_pose(WORLD,ordered,CAMERA) if ordered is not None else None
            if est is not None and est.reprojection_px<=4.0:fits.append(est)
        return min(fits,key=lambda e:e.reprojection_px),detect_plate(frame,CAMERA),entry

    def test_small_sliver_does_not_beat_the_plate(self):
        sliver,chosen,entry=self.sliver_and_plate()
        # Ranking by raw pixel error would pick a pose metres away from the truth.
        self.assertGreater(np.linalg.norm(sliver.camera_position-chosen.camera_position),1.0)
        self.assertLess(np.linalg.norm(chosen.camera_position-entry['camera_position']),0.03)

    def test_gate_rejects_a_real_outlier_pose(self):
        sliver,_,_=self.sliver_and_plate()
        plate=detect_plate(fixture('IMG_0749_tonemap_290')[0],CAMERA)
        tracker=PlateTracker(CAMERA,MarkerLocation(),reacquire_frames=3)
        for i in range(3):shown=tracker.accept(replace(plate,timestamp_s=i/30))
        self.assertIsNotNone(shown)
        self.assertIsNone(tracker.accept(replace(sliver,timestamp_s=3/30)))
        self.assertEqual(tracker.rejected,'pose-jump')


@unittest.skipUnless(tonemap_available(),'needs ffmpeg with zscale+tonemap (CI installs it)')
class HdrInput(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory()
        self.path=Path(self.dir.name)/'hlg.mp4'
        # 10 frames tagged as HLG / BT.2020, like phone and glasses HDR video. Tag the
        # frames themselves (setparams): ffmpeg 8 no longer applies -color_trc alone
        # to the stream, so the codec options are kept only as a fallback.
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc=size=64x48:rate=25','-frames:v','10',
                        '-vf','setparams=color_trc=arib-std-b67:color_primaries=bt2020:colorspace=bt2020nc',
                        '-c:v','libx264','-pix_fmt','yuv420p','-color_trc','arib-std-b67',
                        '-color_primaries','bt2020','-colorspace','bt2020nc',str(self.path)],check=True)
        transfer=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries',
                                 'stream=color_transfer','-of','csv=p=0',str(self.path)],
                                capture_output=True,text=True).stdout.strip()
        if transfer!='arib-std-b67':   # a broken fixture, not a product failure
            self.fail(f'generated clip is not tagged HLG (ffprobe color_transfer={transfer!r})')

    def tearDown(self):self.dir.cleanup()

    def test_hlg_is_detected_and_tone_mapped_with_container_times(self):
        self.assertEqual(probe(self.path).hdr,'HLG')
        video=open_video(self.path)
        frames=[]
        while True:
            ok,frame,t=video.read()
            if not ok:break
            frames.append((frame,t))
        video.release()
        self.assertTrue(video.tonemapped)
        self.assertEqual(len(frames),10)
        np.testing.assert_allclose([t for _,t in frames],np.arange(10)/25,atol=1e-6)
        frame=frames[0][0]
        self.assertEqual(frame.shape,(48,64,3))
        self.assertTrue(frame.flags.writeable)   # callers draw on frames
        cv2.putText(frame,'ok',(2,20),cv2.FONT_HERSHEY_SIMPLEX,.5,(255,255,255),1)

    def test_raw_mode_skips_the_tone_map_but_reports_hdr(self):
        video=open_video(self.path,hdr='raw')
        ok,frame,t=video.read();video.release()
        self.assertTrue(ok);self.assertFalse(video.tonemapped);self.assertEqual(video.hdr,'HLG')


if __name__=='__main__':
    unittest.main()
