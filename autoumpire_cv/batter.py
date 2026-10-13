"""Human-reviewable height proposal using image landmarks and known stature.

This is NOT a rulebook strike-zone estimator or metric 3D pose solution.
It only estimates relative standing heights from an apparent body pixel span.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
import statistics
import math

# MediaPipe Pose Landmark indices: nose=0; shoulders=11/12; hips=23/24;
# knees=25/26; ankles=27/28.
INDEXES = {'nose':(0,), 'shoulder':(11,12), 'hip':(23,24),
           'knee':(25,26), 'ankle':(27,28)}

@dataclass(frozen=True)
class Proposal:
    bottom_m:float
    top_m:float
    visibility:float


def propose_from_landmarks(landmarks,stature_m:float,min_visibility=.75):
    """Approximate joint elevations by pixel span (not valid for deep perspective).

    Landmark rows can be MediaPipe objects with .y/.visibility, or dicts.
    Height estimated from nose-to-ankle span, with heuristic head correction;
    bent knees/torso foreshortening can substantially bias the result.
    """
    if not (.6<=stature_m<=2.5): raise ValueError('Implausible stature')
    observations={}
    for name,ids in INDEXES.items():
        samples=[]
        for idx in ids:
            lm=landmarks[idx]
            y=float(lm['y'] if isinstance(lm,dict) else lm.y)
            v=float(lm.get('visibility',0) if isinstance(lm,dict) else getattr(lm,'visibility',0))
            if math.isfinite(y) and 0<=y<=1 and v>=min_visibility:
                samples.append((y,v))
        if not samples:return None
        observations[name]=(statistics.mean(p[0] for p in samples),min(p[1] for p in samples))
    nose=observations['nose'][0]
    ankle=observations['ankle'][0]
    span=ankle-nose
    if span<.15:return None
    # Nominal forehead lies 5% of apparent body above nose; feet 2% below ankle.
    head_top=nose-.05*span
    feet=ankle+.02*span
    scale=stature_m/(feet-head_top)
    shoulder=observations['shoulder'][0]
    hip=observations['hip'][0]
    knee=observations['knee'][0]
    if not (nose<shoulder<hip<knee<ankle):return None
    top=(feet-(shoulder+hip)/2)*scale
    bottom=(feet-knee)*scale
    if not (.12<=bottom<top<1.7):return None
    return Proposal(bottom,top,min(v for _,v in observations.values()))


class StanceLock:
    """Accept only stable, high-visibility proposals; lock until explicit reset.

    A proposal is *always* a suggestion; caller must explicitly opt in.
    """
    def __init__(self,frames=8,tolerance_m=.035):
        if frames<2:raise ValueError('frames must be >= 2')
        self.history=deque(maxlen=frames)
        self.frames,self.tolerance_m=frames,tolerance_m
        self.locked=None

    def reset(self):
        self.history.clear();self.locked=None

    def update(self,proposal):
        if self.locked is not None:return self.locked
        if proposal is None:
            self.history.clear();return None
        self.history.append(proposal)
        if len(self.history)!=self.frames:return None
        bottoms=[p.bottom_m for p in self.history]
        tops=[p.top_m for p in self.history]
        if max(bottoms)-min(bottoms)>self.tolerance_m or max(tops)-min(tops)>self.tolerance_m:
            return None
        self.locked=Proposal(statistics.median(bottoms),statistics.median(tops),
                             min(p.visibility for p in self.history))
        return self.locked
