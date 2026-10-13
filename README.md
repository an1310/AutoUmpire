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

Visit the URL printed by Vite. Use the controls on the left. On an appropriate WebXR AR device, serve over HTTPS and use the **Start AR** control when available.

### GoPro video (secondary objective)

```bash
python -m pip install opencv-python
python tools/overlay_video.py input.mp4 calibration.json output.mp4
```

This overlays a zone on a video **only if** `calibration.json` contains real camera intrinsics and a **world-to-camera 4×4 transform for every frame**. No automatic GoPro calibration, ball detection, plate tracking, SLAM, or pose estimation is provided. Missing pose frames are intentionally left without an overlay. See [architecture](docs/architecture.md) and the calibration format in the script docstring. OpenCV output currently has **no audio**.

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
| `tools/overlay_video.py` | Offline overlay with supplied frame-by-frame poses |
| `tests/` | Unit tests for dimensions, geometry, error cases and projection |
| `docs/strike-zone-preview.svg` | Concept image showing two batter heights |
| `docs/architecture.md` | Calibration contract, validation and next milestones |

**Roadmap:** automated plate detection and precise pose calibration → batter landmark detection and stance lock → confidence/fail-closed tracking → real headset validation → GoPro pose-estimation adapter.

Uses [Three.js](https://threejs.org/) and browser [WebXR hit-testing](https://developer.mozilla.org/en-US/docs/Web/API/XRSession/requestHitTestSource). Requires hardware support; experimental APIs are not universal.
