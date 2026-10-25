"""Video input that yields display-oriented 8-bit BGR frames with real timestamps.

HDR (HLG or PQ) is the normal case for phone and smart-glasses cameras. OpenCV
decodes it without tone mapping, which clips highlights and washes dirt toward
the plate's white (measured on iPhone HLG practice footage), so HDR files are
decoded by ffmpeg with an explicit HDR->SDR tone map instead. SDR files and live
cameras use OpenCV directly.
"""
from __future__ import annotations
import json
import math
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Optional
import cv2
import numpy as np

HDR_TRANSFERS={'arib-std-b67':'HLG','smpte2084':'PQ'}
# Linearize at the HDR reference white (203 nits), map to BT.709, Hable curve.
TONEMAP_FILTER=('zscale=t=linear:npl=203,format=gbrpf32le,zscale=p=bt709,'
                'tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=bgr24')


@dataclass(frozen=True)
class VideoInfo:
    width:int            # as displayed, after any rotation metadata
    height:int
    fps:float
    transfer:str         # e.g. 'bt709', 'arib-std-b67', 'unknown'

    @property
    def hdr(self) -> Optional[str]:
        return HDR_TRANSFERS.get(self.transfer)


def _ffprobe(args):
    out=subprocess.run(['ffprobe','-v','error',*args],capture_output=True,text=True,check=True).stdout
    return out


def probe(path) -> VideoInfo:
    data=json.loads(_ffprobe(['-select_streams','v:0','-show_streams','-of','json',str(path)]))
    s=data['streams'][0]
    w,h=int(s['width']),int(s['height'])
    rotation=0
    for side in s.get('side_data_list',[]):
        if 'rotation' in side:rotation=int(side['rotation'])
    if 'rotate' in s.get('tags',{}):rotation=int(s['tags']['rotate'])
    if abs(rotation)%180==90:w,h=h,w
    num,_,den=s.get('avg_frame_rate','0/1').partition('/')
    fps=float(num)/float(den or 1) if float(den or 1) else 0.0
    return VideoInfo(w,h,fps or 30.0,s.get('color_transfer','unknown'))


def container_times(path) -> list[float]:
    """Presentation time of every video frame, ascending (from packets; no decode)."""
    out=_ffprobe(['-select_streams','v:0','-show_entries','packet=pts_time','-of','csv=p=0',str(path)])
    return sorted(float(v.strip(',')) for v in out.split() if v.strip(',') not in ('','N/A'))


def tonemap_available() -> bool:
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):return False
    filters=subprocess.run(['ffmpeg','-hide_banner','-filters'],capture_output=True,text=True).stdout
    return ' zscale ' in filters and ' tonemap ' in filters


class FrameClock:
    """Presentation time of each decoded frame, in seconds.

    Files: the container timestamp (CAP_PROP_POS_MSEC). frame_index/fps is wrong
    for variable-frame-rate video, which phones commonly record. Live cameras:
    a monotonic wall clock. A missing or non-increasing container time falls back
    to previous + 1/fps and is counted, so it is visible in the output.
    """
    def __init__(self,cap,live:bool,fps:float):
        self.cap,self.live,self.fps=cap,live,fps
        self.source='wallclock' if live else 'container'
        self.previous=None;self.fallbacks=0;self.start=time.monotonic()

    def __call__(self) -> float:
        if self.live:
            t=time.monotonic()-self.start
        else:
            t=self.cap.get(cv2.CAP_PROP_POS_MSEC)/1000
            if not math.isfinite(t) or t<0 or (self.previous is not None and t<=self.previous):
                self.fallbacks+=1
                t=0.0 if self.previous is None else self.previous+1/self.fps
        self.previous=t
        return t


class OpenCVSource:
    """SDR files and live cameras."""
    def __init__(self,source):
        self.live=isinstance(source,int)
        self.cap=cv2.VideoCapture(source)
        if not self.cap.isOpened():raise RuntimeError(f'Cannot open camera/video: {source}')
        self.fps=self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.clock=FrameClock(self.cap,self.live,self.fps)
        self.hdr=None;self.tonemapped=False

    @property
    def timestamp_source(self):return self.clock.source
    @property
    def timestamp_fallbacks(self):return self.clock.fallbacks

    def read(self):
        ok,frame=self.cap.read()
        return (ok,frame,self.clock()) if ok else (False,None,None)

    def release(self):self.cap.release()


class TonemappedSource:
    """HDR files decoded by ffmpeg to tone-mapped BGR, one raw frame at a time."""
    def __init__(self,path,info:VideoInfo):
        self.info,self.fps,self.hdr,self.tonemapped=info,info.fps,info.hdr,True
        self.times=container_times(path);self.index=0;self.timestamp_fallbacks=0
        self.timestamp_source='container'
        self.frame_bytes=info.width*info.height*3
        # ffmpeg applies rotation metadata itself (autorotate), matching probe().
        self.proc=subprocess.Popen(['ffmpeg','-v','error','-i',str(path),'-map','0:v:0',
                                    '-vf',TONEMAP_FILTER,'-fps_mode','passthrough',
                                    '-f','rawvideo','-pix_fmt','bgr24','-'],
                                   stdout=subprocess.PIPE)

    def read(self):
        buf=self.proc.stdout.read(self.frame_bytes)
        if len(buf)<self.frame_bytes:return False,None,None
        # Copy: frombuffer views are read-only, and callers draw on frames.
        frame=np.frombuffer(buf,np.uint8).reshape(self.info.height,self.info.width,3).copy()
        if self.index<len(self.times):
            t=self.times[self.index]
        else:   # more decoded frames than packets: should not happen; stay visible
            self.timestamp_fallbacks+=1
            t=(self.times[-1] if self.times else 0.0)+(self.index-len(self.times)+1)/self.fps
        self.index+=1
        return True,frame,t

    def release(self):
        if self.proc.poll() is None:self.proc.kill()
        self.proc.stdout.close()
        self.proc.wait()


def open_video(source,*,hdr:str='tonemap'):
    """Open a file path or camera index. ``hdr``: 'tonemap' (default) or 'raw'.

    'raw' decodes HDR with OpenCV as-is (clipped, washed out); use it only to
    compare. Tone mapping needs ffmpeg built with zscale (libzimg).
    """
    if isinstance(source,int) or str(source).isdigit():
        return OpenCVSource(int(source))
    if not shutil.which('ffprobe'):
        print('WARNING: ffprobe not found; cannot detect HDR input',file=sys.stderr)
        return OpenCVSource(str(source))
    info=probe(source)
    if info.hdr and hdr=='tonemap':
        if not tonemap_available():
            raise RuntimeError(f'{info.hdr} HDR input needs ffmpeg with the zscale and tonemap filters '
                               "(libzimg); install it, or pass hdr='raw' to decode without tone mapping")
        return TonemappedSource(source,info)
    src=OpenCVSource(str(source));src.hdr=info.hdr
    return src
