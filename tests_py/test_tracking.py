"""Geometry, stance locking, synthetic calibrated marker detections, rejection tests."""
import unittest
import numpy as np
import cv2
from autoumpire_cv.registration import Camera,MarkerLocation,PlateTracker,fit_pose,project_world
from autoumpire_cv.zone import StrikeZone,PLATE_HALF_M
from autoumpire_cv.batter import StanceLock,Proposal,propose_from_landmarks
from autoumpire_cv.plate import order_pentagon, detect_plate
from autoumpire_cv.zone import PLATE_XZ

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

    def fake_frame(self):
        marker=cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50),0,500)
        corners,_=cv2.projectPoints(self.marker.points(),self.rvec,self.T,self.cam.matrix,self.cam.distortion)
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
        tr=PlateTracker(self.cam,self.marker)
        frame=self.fake_frame()
        est=tr.track(frame)
        self.assertIsNotNone(est,msg=f'failure: {tr.rejected}')
        self.assertLess(est.reprojection_px,2.5)
        self.assertIsNone(tr.track(np.full_like(frame,115)))
        self.assertEqual(tr.rejected,'marker-not-visible')
        self.assertIsNone(tr.previous)

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
