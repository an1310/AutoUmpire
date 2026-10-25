# Experiment: markerless field map from umpire-POV video

**Status:** feasibility result on one clip. Not validated for officiating, not real-time, and the map was built from the same clip it localizes (see [Limits](#limits)).

The measurements below describe the original timestamp-based localizer. The current implementation uses map-wide RootSIFT matching and accepts an independent query video; see the [current runbook](../../experiments/field_map/README.md#localize-a-separate-recording). Those changes do not retroactively validate these measurements on other footage.

**Question:** can a head-worn camera find home plate when the plate is hidden behind the catcher, using no markers? The approach: build a 3D map of the field once, anchor home plate in that map, then localize each frame against the map. The overlay then follows the field (dirt texture, fences, trees, lines), not the plate, so it survives the catcher, the batter and the umpire's own crouch covering the plate.

Code: [`experiments/field_map/`](../../experiments/field_map/README.md). Footage is not in the repo (it shows minors and identifiable people).

## Input

| | |
|---|---|
| Clip | `seg1.mp4`, umpire-POV game footage supplied by the project owner |
| Format | 1280×720, 59.94 fps, 1,797 frames (30.0 s), HEVC 10-bit, BT.709 (SDR, not HDR), wide-angle (fisheye) lens |
| Content | Highlight edit with hard cuts (e.g. 14.86 → 14.91 s); burned-in scoreboard top-left; umpire stands, crouches, looks down at the plate and turns to follow play |
| Camera calibration | None. Lens parameters are estimated from the footage itself |

## Method

1. **Map** (`build_map.py`): 120 keyframes at 4 fps → COLMAP incremental structure-from-motion (pycolmap 4.2.1). Single `RADIAL_FISHEYE` camera, self-calibrated. Sequential matching, overlap 15. The scoreboard box is masked.
2. **Anchor** (`anchor_plate.py`): RANSAC ground plane through the map points. Hand-mark the 5 plate corners in 4 keyframes (`seg1_plate_corners.json`, ±3–6 px), cast them onto the plane, and check that the frames agree. Scale comes from the 17-inch front edge. The regulation pentagon is fit with a proper rotation (a mirror fit means mislabelled corners and is an error). Output: `world_from_plate` in the same frame as `autoumpire_cv.zone` (x toward 1st base, y up, z toward catcher).
3. **Localize** (`localize.py`): every one of the 1,797 video frames independently. SIFT features are ratio-test matched (0.8) to the 3D-backed features of the 4 nearest keyframes, then LO-RANSAC absolute pose with the map's camera (4 px threshold). No frame-to-frame prior, so an error or an edit cut cannot propagate.
4. **Render, fail-closed** (`render_overlay.py`): the zone is drawn only if the pose has ≥ 60 inliers, its inlier map points have median track length ≥ 5 keyframes, and it passes the same continuity and re-acquisition gate as `PlateTracker` (10.5 m/s, 750°/s, 3 frames to re-acquire). Zone heights are fixed inputs (0.40–0.80 m above the plate), not measured from the batter.

**Pitfalls found** (each was observed and fixed; they will recur in any rewrite):

- ffmpeg `fps=4` sampling ran 6–7 frames (≈ 0.1 s) ahead of OpenCV frame index × fps/4. Keyframes are paired to video frames by image correlation (all 120 ≥ 0.98 NCC), not by arithmetic.
- COLMAP pixel centres are at (0.5, 0.5) and OpenCV's at (0, 0). Converting is ±0.5 px both ways.
- The in-plane basis must be `v = u × n` to keep the plate model's handedness. With `n × u` the fit was a reflection.

## Results

### Map and anchor

| Measure | Value |
|---|---|
| Keyframes registered | 120 / 120, 31,310 map points, mean reprojection 0.45 px |
| Self-calibrated lens | f = 651.3 px, k1 = 0.054, k2 = 0.006 (a re-run gave 639.1 px; see [Run-to-run](#run-to-run-reproducibility)) |
| Ground plane | 59 % of map points within 0.05 map units |
| Plate centre, spread across the 4 annotated frames | 0.7–3.8 cm from the mean |
| Plate corners, spread across frames | rms 4.5 cm, max 9.7 cm |
| Regulation-pentagon fit residuals | 2.0–4.4 cm |
| Implied camera height | median 1.58 m standing; p5 1.14 m crouched |

The camera heights are a sanity check on scale, not a measurement: nobody measured the umpire. A 1.58 m eye-level camera and a crouch to about 70 % of standing height are plausible.

### Localization and overlay (all 1,797 frames)

| Measure | Value |
|---|---|
| Frames with a pose | 1,797 / 1,797 (437 s on 4 CPU workers, ≈ 4 fps offline) |
| RANSAC inliers | median 555, p5 336 |
| Keyframes re-localized against their own map poses | position median 0.1 cm, max 2.4 cm; rotation median 0.04°, max 0.36° |
| Zone shown | 1,665 / 1,797 (92.7 %) |
| Hidden: weak map support | 101 (mostly 13.1–14.9 s, a look-down at the plate) |
| Hidden: re-acquiring after a jump | 17 |
| Hidden: < 60 inliers | 13 |
| Hidden: pose jump | 1 |
| Slip, consecutive shown frames | median 0.10 px, p95 0.29 px, max 1.47 px (1,652 pairs) |

The keyframe re-localization row mainly confirms conventions (pixel centres, frame pairing). Those frames built the map.

**Slip** measures how much the overlay swims against the field. For each pair of consecutive shown frames, a ground grid in front of the plate (±3 m wide, 10 m toward the mound) is projected with both poses. The same points are followed in the image by optical flow with a forward-backward check, and slip is the median disagreement. To check that the metric can see errors, the same 200 frames were rerun with random rotation noise injected:

| Injected rotation noise (σ per axis) | 0° | 0.05° | 0.10° | 0.25° |
|---|---|---|---|---|
| Slip median / p95 (px) | 0.10 / 0.23 | 0.63 / 1.18 | 1.18 / 2.27 | 2.99 / 5.60 |

So frame-to-frame pose noise is below about 0.05°: the measured slip matches the clean floor. Two cautions:

- **Slip cannot see a constant error.** If the whole map or the plate anchor is off, every frame is off the same way and slip stays at zero. Slip measures smoothness, not accuracy.
- **A first version of the metric was wrong twice.** A 5-frame-median "jitter" scored 0.0 px by construction, because a median filter returns monotonic motion unchanged. Its replacement, a ring 0.3–1.2 m around the plate, reported 5–15 px "slip" that was really the catcher. From the umpire's eye the catcher covers most of that ring, so the flow followed the catcher.

### Run-to-run reproducibility

The whole pipeline was re-run from scratch with the README commands (15.6 min end to end on 4 CPU cores). COLMAP's incremental mapping is not deterministic, so the two maps differ slightly:

| Measure | Reported run | Re-run |
|---|---|---|
| Map | 31,310 points, 0.45 px reprojection | 31,369 points, 0.37 px |
| Self-calibrated focal length | 651.3 px | 639.1 px |
| Metres per map unit | 0.5617 | 0.5626 |
| Corner spread / regulation-fit residuals | rms 4.5 cm / 2.0–4.4 cm | rms 4.5 cm / 2.0–4.5 cm |
| Frames with a pose | 1,797 | 1,797 |
| Zone shown | 1,665 (92.7 %) | 1,640 (91.3 %) |
| Hidden: weak map support | 101 | 125 |
| Slip median / p95 | 0.10 / 0.29 px | 0.10 / 0.28 px |

**Where the zone lands, map against map.** The zone-corner disagreement was measured for each frame, taking the worst visible corner, with zone corners projected from each run's pose and anchor:

- **Frames that pass both runs' gates** (1,103 frames): median 1.5 px, p95 6.1 px, max 7.0 px. That is roughly a third of a baseball's width at 2 m (inferred: about 24 px per ball at f ≈ 650 px).
- **Disagreement over 20 px:** every case falls in the 14–15 s look-down, the stretch the weak-map-support gate hides. There the two maps differ by about 60 px.

That gives independent support for the gate, whose threshold was chosen on that same stretch by eye. It is still one clip.

This measures repeatability, not accuracy: two runs can agree and both be wrong.

### Occlusion

At the pitch (≈ 15.3–16.1 s, and the later pitch at ≈ 26.9–27.4 s after an edit cut) the plate is fully behind the catcher's helmet. The zone is drawn from the map alone and stays put. After the edit cut, frames where the plate is partly visible were checked by eye, and the outline lands on it.

### Absolute accuracy: not measured

No independent ground truth exists for this clip. The 4 annotated frames define the anchor, so their agreement (4.5 cm rms) is a consistency check, not a held-out test. On held-out frames the evidence is visual only. The outline lands on the visible plate after the edit cut (keyframes f0108/f0110). On a look-down frame (f0058, 14.36 s) it is roughly 15–20 cm off, judged by eye. That frame falls in the stretch the weak-map-support gate hides.

## Limits

- **In-sample map.** The map was built from the frames being localized. In use, the map would come from a pre-game walk-around or earlier innings and be tested on later play. This is the most important untested step.
- **One clip, one field, one day:** sunny, dry dirt with strong texture. Shadows move during a game, and grass, night lighting and a raked infield are untested.
- **The weak-map-support threshold (5) was tuned on one bad stretch.** It also hides about 6 % of frames that may be fine (e.g. 0–5.7 s scores 5–7, accuracy unknown). It needs validation on more footage before it means anything.
- **Not real-time:** about 4 fps offline on CPU. A glasses build would use the headset's own tracking (VIO) frame to frame and correct drift with occasional map relocalization like this one.
- **The camera was a GoPro-style action camera, not glasses.** Glasses have a different lens, HDR output and possibly electronic stabilization (which breaks a fixed-intrinsics model). Calibrate or self-calibrate per device.
- **The ground is assumed planar.** The plate is anchored to a plane fit over the whole map. Infield slope or a crowned plate area is unmodelled.
- **The overlay draws over the catcher and batter.** That is the intent for a training and augmentation aid (see the zone through the catcher), but it is a display choice, not a depth test.
- **The zone is illustrative:** fixed 0.40–0.80 m heights, not the batter's.

## Next steps (in order)

1. **Out-of-sample test.** Build the map from one half of a game (or a pre-game walk-around) and localize the other half.
2. **Ground truth.** Hand-mark the plate on about 30 held-out frames where it is visible, then report reprojection error in px and cm. Report stationary-plate-hidden frames separately.
3. **Validate the confidence gate** on several clips. Report frames hidden that were fine, and frames shown that were wrong.
4. **Glasses footage.** Self-calibration on that lens, and HDR input via `autoumpire_cv/video.py` (PR #7).
