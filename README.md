# AutoUmpire

**A hardware-agnostic, augmented strike-zone *visualization* prototype for umpire training.** No pitch tracking, no ball/strike decisions, and no claims of field accuracy.

![Illustrative strike-zone overlay for two different-height batters](docs/strike-zone-preview.svg)

*Concept artwork, not a device screenshot.* The two different-height batters demonstrate how the manually calibrated **top and bottom** of the strike-zone volume change with the batter. The zone is a **pentagonal 3D prism** above actual 17-inch home plate geometry—not a flat rectangle pasted on the camera.

## What you can run today

- Desktop Three.js simulator with orbit/zoom, true-scale plate, 3D zone edges and translucent top/bottom faces.
- Switch between illustrative **5′0″** and **6′3″** batter silhouettes. Drag sliders to override the strike-zone elevations individually.
- **Experimental WebXR** manual AR placement using hit-test. Tap a detected surface at the center of home plate, then set plate heading manually. This only works on supported devices/browsers via HTTPS; it does **not** detect the plate or verify alignment.
- Separate pure geometry and projection modules so input can later come from a headset, camera, GoPro, or replay file.
- Optional offline GoPro/MP4 overlay helper, when per-frame camera calibration/poses have been supplied externally.

### Run

```bash
npm install
npm test
npm run dev
```

`npm run test:ar` drives the real AR placement flow (Start AR → two taps → heading and span check) against an emulated WebXR headset ([IWER](https://www.npmjs.com/package/iwer)) in headless Chromium. Run `npx playwright install chromium` once, or set `CHROMIUM_PATH`. It cannot test the AR control-panel overlay, real tracking or rendering. iOS Safari has no WebXR AR, so test on hardware with an Android ARCore phone or a Quest.

Visit the URL printed by Vite. Use the controls on the left. On an appropriate WebXR AR device, serve over HTTPS and use the **Start AR** control when available.

### GoPro / recorded video (secondary objective)

Recorded video goes through the calibrated tracker (`tools/track_video.py`, see Phase 2 below) and is reviewed in `review.html`. The tracker logs each frame's real container timestamp, so variable-frame-rate phone video lines up correctly. The earlier `overlay_video.py` helper was removed: it ignored lens distortion, which is large on GoPro wide modes.

## Important limitations

1. These strike-zone boundaries are **illustrative**, not batter landmarks identified by CV or measurements from a league-certified rulebook.
2. WebXR hit-test only finds a physical surface point. **It does not measure home plate, determine heading, or validate anchor drift.** Headset sensor and browser behavior vary.
3. **Do not use this prototype to adjudicate live pitches.** A visually convincing but misregistered box can be worse than no overlay, especially at 90+ mph.
4. GoPro monocular video requires camera calibration plus a 6DoF camera trajectory; a 2D homography on its own is not sufficient for accurate 3D elevation.

## Project map

| Area | Role |
|---|---|
| `src/geometry.js` | Pure plate and strike-zone geometry, SI units |
| `src/projection.js` | Input-independent calibrated 3D-to-image projection |
| `src/main.js` | Three.js desktop rendering and experimental WebXR placement |
| `tools/track_video.py` | Marker tracking on recorded or live video; per-frame poses and timestamps |
| `tests/` | Unit tests for dimensions, geometry, error cases and projection |
| `docs/strike-zone-preview.svg` | Concept image showing two batter heights |
| `docs/architecture.md` | Calibration contract, validation and next milestones |
| `experiments/field_map/` | Offline experiment: markerless field map so the zone holds while the catcher hides the plate ([results](docs/experiments/field-map-umpire-pov.md)) |

**Roadmap:** automated plate detection and precise pose calibration → batter landmark detection and stance lock → confidence/fail-closed tracking → real headset validation → GoPro pose-estimation adapter.

Uses [Three.js](https://threejs.org/) and browser [WebXR hit-testing](https://developer.mozilla.org/en-US/docs/Web/API/XRSession/requestHitTestSource). Requires hardware support; experimental APIs are not universal.

## Phase 2 — Camera calibration, plate registration, and batter stance proposals

**Now available (experimental):**
- Calibrate real cameras with chessboard images via `tools/calibrate_camera.py`.
- Generate a physical ArUco reference tag; measure its rigid offset from home plate.
- Plan and use a **multi-marker layout** (4 recommended), fit jointly, with displaced-marker rejection; `tools/simulate_registration.py` predicts overlay error for a layout and viewpoint.
- Detect the marker and solve a **per-frame 6DoF** world-to-camera transform, using calibrated intrinsics, lens distortion, and physical plausibility checks. Lost tag, insufficient pixels, high reprojection error, or pose discontinuity means **hide the overlay**.
- Optional `--allow-plate-contour` white pentagon detector for unobstructed benchmark footage; **not a production tracker**.
- Manually calibrated batter top/bottom bounds; optional **MediaPipe pose-landmark proposals** within a supplied batter ROI, with 8-frame stability lock and an explicit acceptance switch. 2D body ratios are **not metric ground truth** or league-approved strike-zone measurements.
- `tools/track_video.py` takes recorded video or a webcam source and produces accepted pose metadata plus optional annotated MP4.
- `review.html` browser tool takes original video plus the generated tracking JSON and renders only accepted camera poses. Vite builds both the simulator and review page.

See **[field calibration and runbook](docs/field-calibration.md)** for measured inputs and commands.

```bash
python -m pip install -r requirements-cv.txt
python tools/generate_marker.py --id 0 1 2 3 --output marker-{id}.png
# Measure the markers and camera, then create field.json from docs/field-calibration.md
python tools/track_video.py --input practice.mp4 --config field.json \
  --output-video review.mp4 --output-json tracking.json
```

Unit and synthetic-video tests verify marker detection, physical 6DoF reconstruction, and fail-closed marker loss. **Field accuracy, wearable registration, and batter landmark agreement remain unverified.** Do not use for live pitch adjudication.
