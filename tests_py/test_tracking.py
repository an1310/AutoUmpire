"""Geometry, stance locking, synthetic calibrated marker detections, rejection tests."""
import sys
import unittest
from pathlib import Path
import numpy as np
import cv2
from autoumpire_cv.registration import Camera,MarkerLocation,PlateTracker,fit_pose,project_world
from autoumpire_cv.zone import StrikeZone,PLATE_HALF_M
from autoumpire_cv.batter import StanceLock,Proposal,propose_from_landmarks
from autoumpire_cv.plate import order_pentagon, detect_plate
from autoumpire_cv.zone import PLATE_XZ
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from track_video import FrameClock,validate_config
from simulate_registration import simulate

class Tests(unittest.TestCase):
    def setUp(self):
        self.cam=Camera.from_config({'width':1280,'height':720,'fx':950,'fy':950,'cx':640,'cy':360})
        self.marker=MarkerLocation(marker_id=0,side_m=.15,x_m=-.8,z_m=0)
        # Physical camera behind plate at (0,1.75,2.2), looking towards pitcher.
        eye=np.array([0,1.75,2.2]);target=np.array([0,.5,-.2]);
        forward=(target-eye);forward/=np.linalg.norm(forward)
        right=np.cross(forward,np.array([0,1.,0]));right/=np.linalg.norm(right)
        down=np.cross(forward,right) # right x down -> forward
        self.R=np.stack([right,down,forward]);self.T=-self.R@eye
        self.rvec,_=cv2.Rodrigues(self.R)

    def test_zone_plate_geometry(self):
        z=StrikeZone(.35,1.05)
        self.assertEqual(len(z.corners),10)
        self.assertEqual(len(z.edges),15)
        self.assertAlmostEqual(z.corners[1,0]-z.corners[0,0],2*PLATE_HALF_M)
        with self.assertRaises(ValueError): StrikeZone(1,.5)

    def test_marker_registration_from_ideal_corners(self):
        corners,_=cv2.projectPoints(self.marker.points(),self.rvec,self.T,self.cam.matrix,self.cam.distortion)
        est=fit_pose(self.marker.points(),corners.reshape(-1,2),self.cam)
        self.assertIsNotNone(est)
        self.assertLess(est.reprojection_px,0.001)
        self.assertLess(np.linalg.norm(est.camera_position-[0,1.75,2.2]),.005)

    def fake_frame(self,rvec=None,T=None):
        rvec=self.rvec if rvec is None else rvec
        T=self.T if T is None else T
        marker=cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50),0,500)
        corners,_=cv2.projectPoints(self.marker.points(),rvec,T,self.cam.matrix,self.cam.distortion)
        # Render a border of white quiet zone surrounding the synthetic marker.
        # Warp flat marker pixels into four projected corners on a gray field.
        img=np.full((720,1280,3),115,dtype=np.uint8)
        pts=corners.reshape(4,2).astype('float32')
        src=np.array([[0,0],[499,0],[499,499],[0,499]],np.float32)
        H=cv2.getPerspectiveTransform(src,pts)
        warped=cv2.warpPerspective(marker,H,(1280,720),borderValue=115)
        stencil=cv2.warpPerspective(np.ones_like(marker)*255,H,(1280,720))
        img[stencil>0]=cv2.cvtColor(warped,cv2.COLOR_GRAY2BGR)[stencil>0]
        return img

    def test_tracker_detects_synthetic_marker_and_fails_closed(self):
        tr=PlateTracker(self.cam,self.marker,reacquire_frames=3)
        frame=self.fake_frame()
        for _ in range(2):
            self.assertIsNone(tr.track(frame))
            self.assertEqual(tr.rejected,'acquiring')
        est=tr.track(frame)
        self.assertIsNotNone(est,msg=f'failure: {tr.rejected}')
        self.assertLess(est.reprojection_px,2.5)
        self.assertIsNone(tr.track(np.full_like(frame,115)))
        self.assertEqual(tr.rejected,'marker-not-visible')
        self.assertIsNone(tr.previous)

    def test_pose_jump_needs_full_reacquisition(self):
        tr=PlateTracker(self.cam,self.marker,reacquire_frames=3)
        a=self.fake_frame()
        # Same orientation, camera shifted 0.6 m sideways: too fast for one 30 fps frame.
        b=self.fake_frame(self.rvec,self.T-self.R@np.array([.6,0,0]))
        for _ in range(3):tr.track(a)
        self.assertIsNotNone(tr.previous)
        self.assertIsNone(tr.track(b));self.assertEqual(tr.rejected,'pose-jump')
        # Previously the very next frame was accepted with no continuity check.
        self.assertIsNone(tr.track(b));self.assertEqual(tr.rejected,'acquiring')
        self.assertIsNotNone(tr.track(b))
        # An alternating outlier never reaches the display.
        tr=PlateTracker(self.cam,self.marker,reacquire_frames=3)
        self.assertTrue(all(tr.track(f) is None for f in [a,b,a,b,a,b]))

    BOARD=[MarkerLocation(i,.15,x,z) for i,(x,z) in enumerate([(-.8,0),(.8,0),(-.8,-.9),(.8,-.9)])]

    def board_frame(self,markers):
        img=np.full((720,1280,3),115,dtype=np.uint8)
        d=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        src=np.array([[0,0],[499,0],[499,499],[0,499]],np.float32)
        for m in markers:
            c,_=cv2.projectPoints(m.points(),self.rvec,self.T,self.cam.matrix,self.cam.distortion)
            H=cv2.getPerspectiveTransform(src,c.reshape(4,2).astype('float32'))
            mk=cv2.aruco.generateImageMarker(d,m.marker_id,500)
            warped=cv2.warpPerspective(mk,H,(1280,720))
            stencil=cv2.warpPerspective(np.full_like(mk,255),H,(1280,720))
            img[stencil>0]=cv2.cvtColor(warped,cv2.COLOR_GRAY2BGR)[stencil>0]
        return img

    def acquire(self,tracker,frame):
        for _ in range(tracker.reacquire_frames-1):self.assertIsNone(tracker.track(frame))
        est=tracker.track(frame)
        self.assertIsNotNone(est,msg=f'failure: {tracker.rejected}')
        return est

    def test_board_fits_all_markers_and_tolerates_occlusion(self):
        est=self.acquire(PlateTracker(self.cam,self.BOARD),self.board_frame(self.BOARD))
        self.assertEqual(est.markers_used,(0,1,2,3))
        self.assertLess(np.linalg.norm(est.camera_position-[0,1.75,2.2]),.02)
        # Marker 1 hidden (e.g. under the batter's foot): the rest still register.
        est=self.acquire(PlateTracker(self.cam,self.BOARD),self.board_frame(self.BOARD[:1]+self.BOARD[2:]))
        self.assertEqual(est.markers_used,(0,2,3))
        self.assertEqual(est.markers_dropped,())

    def test_board_drops_displaced_marker(self):
        # Marker 3 was kicked 10 cm but the layout still lists its measured spot.
        moved=self.BOARD[:3]+[MarkerLocation(3,.15,.9,-.9)]
        est=self.acquire(PlateTracker(self.cam,self.BOARD),self.board_frame(moved))
        self.assertEqual(est.markers_used,(0,1,2))
        self.assertEqual(est.markers_dropped,(3,))
        self.assertLess(np.linalg.norm(est.camera_position-[0,1.75,2.2]),.02)

    def test_board_hides_with_too_few_markers(self):
        tr=PlateTracker(self.cam,self.BOARD)  # default min_markers=3 for a 4-marker layout
        self.assertIsNone(tr.track(self.board_frame(self.BOARD[:2])))
        self.assertEqual(tr.rejected,'insufficient-observation')
        # Three visible, one displaced: two agreeing markers are not enough.
        tr=PlateTracker(self.cam,self.BOARD)
        self.assertIsNone(tr.track(self.board_frame(self.BOARD[:2]+[MarkerLocation(3,.15,.9,-.9)])))
        self.assertEqual(tr.rejected,'markers-inconsistent')
        with self.assertRaises(ValueError):PlateTracker(self.cam,[self.BOARD[0],self.BOARD[0]])
        with self.assertRaises(ValueError):PlateTracker(self.cam,self.BOARD,min_markers=5)

    def test_config_accepts_one_marker_or_a_layout(self):
        cam={'width':1280,'height':720,'fx':950,'fy':950,'cx':640,'cy':360}
        zone={'bottom_m':.45,'top_m':1.05}
        one={'marker_id':0,'side_m':.15,'x_m':-.8,'z_m':0}
        _,markers,_=validate_config({'camera':cam,'zone':zone,'marker':one})
        self.assertEqual(len(markers),1)
        _,markers,_=validate_config({'camera':cam,'zone':zone,'markers':[one,{**one,'marker_id':1,'x_m':.8}]})
        self.assertEqual([m.marker_id for m in markers],[0,1])
        for bad in [{'marker':one,'markers':[one]},{},{'markers':[]},{'markers':[{'side_m':.15,'x_m':0,'z_m':0}]}]:
            with self.assertRaises(ValueError):validate_config({'camera':cam,'zone':zone,**bad})

    def test_layout_simulation_reports_visibility_and_board_advantage(self):
        zone=StrikeZone(.45,1.05)
        args=((0,1.75,2.2),(0,.5,-.2),[1.0])
        single=simulate(self.cam,[self.BOARD[0]],zone,*args,trials=200)
        board=simulate(self.cam,self.BOARD,zone,*args,trials=200)
        self.assertTrue(all(m['usable'] for m in board['markers'].values()))
        self.assertLess(board['noise'][1.0]['zone_err_px_p95'],single['noise'][1.0]['zone_err_px_p95']/3)
        # Close behind the plate the side markers leave the frame; report, do not guess.
        near=simulate(self.cam,self.BOARD,zone,(0.3,1.35,0.9),(0,.6,-.5),[1.0],trials=10)
        self.assertIn('error',near)
        self.assertFalse(near['markers'][0]['in_frame'])

    def test_continuity_limits_are_per_second(self):
        tr=PlateTracker(self.cam,self.marker,reacquire_frames=1)
        a=self.fake_frame()
        b=self.fake_frame(self.rvec,self.T-self.R@np.array([.6,0,0]))
        # 0.6 m in 1/30 s (18 m/s) is a jump; the same move over 0.1 s (6 m/s) is not.
        self.assertIsNotNone(tr.track(a,0.0))
        self.assertIsNone(tr.track(b,1/30));self.assertEqual(tr.rejected,'pose-jump')
        tr=PlateTracker(self.cam,self.marker,reacquire_frames=1)
        self.assertIsNotNone(tr.track(a,0.0))
        self.assertIsNotNone(tr.track(b,0.1))
        # A repeated or backwards timestamp cannot vouch for continuity.
        self.assertIsNone(tr.track(b,0.1));self.assertEqual(tr.rejected,'pose-jump')

    def test_frame_clock_uses_container_time_and_counts_fallbacks(self):
        class Cap:
            def __init__(self,ms):self.ms=iter(ms)
            def get(self,prop):return next(self.ms)
        clock=FrameClock(Cap([0,40,160,160,float('nan'),240]),live=False,fps=25)
        times=[clock() for _ in range(6)]
        np.testing.assert_allclose(times,[0,.04,.16,.2,.24,.24+.04])
        # 160 repeated, NaN, then 240 colliding with the 0.24 s guess: three fallbacks.
        self.assertEqual(clock.fallbacks,3)
        self.assertEqual(clock.source,'container')

    def test_resolution_mismatch_rejected(self):
        tracker=PlateTracker(self.cam,self.marker)
        with self.assertRaises(ValueError):tracker.track(np.zeros((720,720,3),dtype=np.uint8))

    def test_stance_lock_requires_stable_samples_and_reset(self):
        lock=StanceLock(frames=8,tolerance_m=.035)
        for i in range(7):self.assertIsNone(lock.update(Proposal(.42,.99,.95)))
        v=lock.update(Proposal(.42,.99,.95))
        self.assertIsNotNone(v)
        self.assertEqual(lock.update(None),v)
        lock.reset()
        self.assertIsNone(lock.locked)
        for i in range(8):self.assertIsNone(lock.update(Proposal(.4,1.+.1*(i%2),.96)))

    def test_landmark_proposal_needs_visible_stance(self):
        ymap={0:.13,11:.29,12:.3,23:.53,24:.54,25:.73,26:.74,27:.95,28:.96}
        lms=[{'y':0,'visibility':0} for i in range(33)]
        for k,v in ymap.items():lms[k]={'y':v,'visibility':.99}
        p=propose_from_landmarks(lms,1.75)
        self.assertIsNotNone(p)
        self.assertLess(p.bottom_m,p.top_m)
        lms[0]['visibility']=.4
        self.assertIsNone(propose_from_landmarks(lms,1.75))

    def test_pentagon_order(self):
        pts=np.array([[10,10],[100,10],[100,50],[55,95],[10,50]],dtype=float)
        for roll in range(5):
            ordered=order_pentagon(np.roll(pts,roll,axis=0))
            np.testing.assert_allclose(ordered,pts)
            np.testing.assert_allclose(order_pentagon(np.roll(pts[::-1],roll,axis=0)),pts)

    def test_optional_white_pentagon_on_clean_synthetic_image(self):
        pts=np.array([[x,0,z] for x,z in PLATE_XZ])
        pix,_=cv2.projectPoints(pts,self.rvec,self.T,self.cam.matrix,self.cam.distortion)
        frame=np.full((720,1280,3),100,dtype=np.uint8)
        cv2.fillConvexPoly(frame,np.rint(pix.reshape(-1,2)).astype(np.int32),(242,242,242))
        found=detect_plate(frame,self.cam)
        self.assertIsNotNone(found)
        self.assertLess(found.reprojection_px,2.5)
        self.assertEqual(found.method,'plate-contour')

if __name__=='__main__':unittest.main()
