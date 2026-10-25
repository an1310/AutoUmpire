# Architecture & validation roadmap

## Geometric truth model

Coordinate system: **meters**, origin at the center of home plate's 17-inch bounding square, X laterally toward first-base side, Y up, and Z toward catcher. The real plate's *pentagon* is extruded between measured bottom/top strike-zone bounds. The demo uses illustrative (not measured) batter presets; the user can override both heights. Actual league rules differ. Do **not** use the preset heights to make live calls.

The rendering code consumes pure `makeZone()` geometry. Camera input is a **different concern**:
- **Desktop**: Three.js orbit camera, for inspecting shape and calibration.
- **WebXR experimental**: use two hit-test taps, at the plate's back tip and front-edge midpoint, to set position and heading. A span check rejects inconsistent placement. Requires supported browser/device + HTTPS; the taps do not identify the plate or prove registration accuracy.
- **GoPro/offline**: `tools/track_video.py` estimates per-frame camera poses from measured markers; `review.html` replays them with full lens distortion (`src/replayProjection.js`), matched to video by per-frame timestamps.
- **Experimental field map**: `experiments/field_map/localize.py` estimates independent query poses against all mapped landmarks using COLMAP features. `render_overlay.py` projects the zone with the map's camera model and applies confidence and continuity gates. Its pose JSON and camera models are separate from the browser replay format. See the [current checkpoint](experiments/field-map-relocalization.md).

Adapter boundary: each input source should produce a calibrated camera/plate pose with timing and confidence, without modifying geometry. Fiducial PnP and experimental sparse-map localization are implemented; real-device tracking fusion, calibrated uncertainty, and live SLAM integration are not. A plane-only homography will not correctly position a 3D elevated strike-zone volume.

## Smart-glasses device classes

A world-locked 3D zone needs the display's **6DoF pose at display rate** (≥60 Hz, low motion-to-photon latency). Umpires move their heads while tracking a pitch. That requirement sorts glasses into three classes:

| Class | Examples (verify current SDKs) | What this project can do |
|---|---|---|
| Camera, no display | Ray-Ban Meta | Video source for the offline `track_video.py` → `review.html` pipeline. No overlay. |
| Heads-up display, no world tracking | Meta Ray-Ban Display (developer preview since May 2026; reported 600×600 right-lens panel, UI components or web apps) | Glanceable status only (zone heights, tracking OK/lost). I found no documented 6DoF world tracking, so a 3D zone cannot be world-locked. A head-fixed box would be **misleading**. |
| 6DoF passthrough or see-through | Passthrough headsets (e.g. Quest 3); see-through 6DoF glasses | The only class that can render the zone world-locked. Use the WebXR path where `immersive-ar` + `hit-test` exist. |

For the 6DoF class, the device's own tracker should drive every displayed frame. Marker registration (`autoumpire_cv`) should only **anchor and periodically correct** the plate pose. A camera pose is not the eye pose: see-through displays also need display-to-eye calibration. None of this fusion is implemented yet.

## Critical safety/integrity gates

1. Require physical calibration of plate dimensions and camera intrinsics for any real-world overlay.
2. Detect head translation/rotation and reject drift; do not treat IMU-only yaw or a single point as stable registration.
3. Independently validate overlay error against a measured target (goal under 1 inch in the plate plane; NOT established).
4. Fade/hide if tracking confidence fails. Current POC has no calibrated confidence estimates.
5. Comply with venue/rulebook guidance before wearing any device behind the plate, and avoid occluding pitches.

## Proposed experiments

- Bench: known-size checkerboard/AprilTag arrangement on the plate to measure reprojection error at multiple viewpoints.
- On field: tracked references at front/middle/back of plate; assess translation during an umpire's normal stance.
- Batter calibration: compare manually measured shoulder/pants/knee landmarks to estimated pose; freeze bounds only after stance established.
- GoPro: offline estimation with recorded camera trajectory plus time-aligned frames.
- Hardware: evaluate real 6DoF passthrough headset, then smaller displays only after registration test.

## Commands

```bash
npm install
npm test
npm run dev
npm run build
```

Open the Vite URL in a desktop browser for simulator. For WebXR AR use an HTTPS-served build on a browser with immersive-ar and hit-test support.
