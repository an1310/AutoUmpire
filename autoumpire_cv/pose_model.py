"""Optional MediaPipe Tasks inference on batter ROI (user-specified)."""
import cv2
from .batter import propose_from_landmarks

class BatterEstimator:
    def __init__(self,model_path:str,height_m:float,roi:tuple):
        import mediapipe as mp
        self.mp=mp
        self.roi=roi
        self.height_m=height_m
        options=mp.tasks.vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=model_path),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_poses=1, min_pose_detection_confidence=.65,
            min_pose_presence_confidence=.65,min_tracking_confidence=.65)
        self.detector=mp.tasks.vision.PoseLandmarker.create_from_options(options)

    def proposal(self,frame,ms:int):
        h,w=frame.shape[:2]
        x0,y0,x1,y1=self.roi
        if not (0<=x0<x1<=1 and 0<=y0<y1<=1):raise ValueError('ROI is normalized x0,y0,x1,y1')
        crop=frame[int(h*y0):int(h*y1),int(w*x0):int(w*x1)]
        if crop.size==0:return None
        rgb=cv2.cvtColor(crop,cv2.COLOR_BGR2RGB)
        img=self.mp.Image(image_format=self.mp.ImageFormat.SRGB,data=rgb)
        poses=self.detector.detect_for_video(img,ms).pose_landmarks
        if not poses:return None
        return propose_from_landmarks(poses[0],self.height_m)

    def close(self):self.detector.close()
