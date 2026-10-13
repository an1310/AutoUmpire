# Field calibration / real camera capture (experimental)

**Purpose:** reproducible, measurable registration experiments. This is not a live officiating aid yet.

## Camera calibration

1. **Keep camera settings fixed.** Same resolution, focal length, lens mode, stabilization mode and crop as capture. GoPro stabilization, horizon leveling, digital zoom, changing FOV, and rolling shutter can invalidate one static intrinsics matrix. For a GoPro, prefer a fixed, calibrated lens mode and stabilization OFF during initial evaluation.
2. Print or display a known-size chessboard and capture **at least 8 diverse views** (prefer 20+) at exactly the capture resolution.
3. Run `python tools/calibrate_camera.py --images 'frames/*.jpg' --inner-cols 9 --inner-rows 6 --square-mm 25 --output camera.json`. Replace values with your own board dimensions. The tool rejects high-RMS fits (>2px), but passing this doesn't guarantee low field error.
4. Put the camera output (`matrix`, `distortion`, `width`, `height`) into `field.json`.

## Fiducial-to-plate measurement

1. Print `python tools/generate_marker.py --id 0 --output marker.png`. Mount it flat on a rigid, nonreflective surface in a **safe location outside playing territory**. Do not leave obstacles on the field during live play.
2. Measure the **black-square side**, not the white quiet border. Record `marker.side_m`.
3. World origin: center of the 17-inch home plate bounding square (at ground level). `x` positive toward first base, `z` positive toward catcher; `y` up. Measure marker center `x_m` and `z_m` from this origin. When yaw=0, TOP of printed marker faces pitcher (`-z`). Measure its orientation `yaw_deg` if rotated. Marker plane assumed coplanar with ground at `y=0`.
4. Position camera behind home plate, above the field; **camera must observe marker every frame** for marker-only tracking. Occlusion hides the overlay (by design).
5. Compare projected plate edges against **independent surveyed ground-truth reference points** across varied head positions. Reprojection RMS only measures marker-fit, not correctness of marker offset or 3D zone.

### Example `field.json`

```json
{
  "camera": {
    "width": 1920, "height": 1080,
    "matrix": [[1200,0,960],[0,1200,540],[0,0,1]],
    "distortion": [0,0,0,0,0]
  },
  "marker": {"marker_id": 0, "side_m": 0.15, "x_m": -0.8, "z_m": 0.0, "yaw_deg": 0.0},
  "zone": {"bottom_m": 0.43, "top_m": 1.05},
  "accept_pose_proposals": false
}
```

**These numeric values are placeholders.** Never use fake intrinsics or guessed offsets on real footage.

```bash
python -m pip install -r requirements-cv.txt
python tools/track_video.py --input test.mp4 --config field.json \
  --output-video reviewed.mp4 --output-json poses.json
```

The tracking JSON provides **accepted** per-frame world-to-camera transforms, zone bounds and rejection statistics. No tag visible = overlay absent. It makes a plausible pose from a *single planar reference*, not millimeter-accurate tracking. Marker tracking is the safer starting point than shape matching while catchers obscure the plate.

### Optional unmarked plate detection

Add `--allow-plate-contour` to consider light-colored convex pentagon contours when the tag isn't observed. This detector can mistake white equipment or chalk for home plate; it assumes an unobstructed plate and a viewpoint from behind the catcher. **Use it for benchmark clips only; do not rely on it for game conditions.**

## Batter-specific calibration

You can always manually enter strike-zone bounds for each batter using `zone.bottom_m` and `zone.top_m`. Actual top/bottom landmarks vary by ruleset; do not assume a fixed fraction of standing height is league-correct.

There is also an **explicitly opt-in** MediaPipe pose proposal path, requiring a locally downloaded `pose_landmarker.task` file and `pip install mediapipe` (no weight is included in this repository). Put this in the config:

```json
{
  "batter": {"model_path": "pose_landmarker.task", "height_m": 1.75,
             "roi": [0.05, 0.05, 0.43, 0.98]},
  "accept_pose_proposals": true
}
```

The normalized rectangle `roi` **must isolate the BATTER** so the catcher is not mistaken for the hitter. Select the correct camera-side batter box and actual height, then invoke `--auto-zone`. At least 8 consistent proposal frames (3.5cm tolerance, landmark visibility ≥0.75) are required to **lock** top and bottom; a reset is required to change batter. Use `--reset-at <frame numbers>` for batter changes. Pose landmarks are 2D pixel references, not metric ground truth. Head/ankle extrapolation and perspective cause systematic errors. A locked *proposal* still needs manual comparison to your league's definition before meaningful use.

## Hard limitations

- This is not a 6DoF world tracker on any commercial glasses yet. It estimates pose independently on observed 2D fiducials in camera frames; camera-loss / tag-loss are not interpolated.
- No automatic marker-to-plate measurement or precise batter-person association; the human must measure and select ROI.
- In the no-fiducial case the heuristic pentagon detector has not been validated.
- Video encoding strips source audio. Calibration isn't transferrable when GoPro lens mode/crop/stabilization changes.
- Before real game use: test drift vs surveyed references under catcher occlusion, stadium lighting, 90+ mph pitches and realistic masks. Disable when uncertain. Check league and local device rules.
