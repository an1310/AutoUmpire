# Field map from umpire-POV video (experiment)

Markerless plate localization: build a 3D map of the field, anchor home plate in it, localize every frame, draw the zone fail-closed. Results, numbers and limits: [docs/experiments/field-map-umpire-pov.md](../../docs/experiments/field-map-umpire-pov.md).

Not part of the prototype or its tests. Do not commit footage, keyframes or rendered video: they show minors and identifiable people. Keep `--work` outside the repo.

## Setup

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r experiments/field_map/requirements.txt   # pycolmap is pinned; its API moves between releases
```

`ffmpeg` must be on `PATH` (keyframe extraction).

## Run

```bash
V=seg1.mp4; W=../runs/seg1; F=experiments/field_map

# 1. Map: keyframes, mask the burned-in scoreboard, structure-from-motion (~minutes on CPU)
python $F/build_map.py --video $V --work $W --fps 4 --mask-box 0 0 475 62 --camera-params 580,640,360,0,0

# 2. Anchor the plate. Corner pixels are hand-marked in keyframes ($W/images/f*.jpg),
#    order front_left, front_right, right_side_bottom, back_tip, left_side_bottom (left = 3rd-base side)
python $F/anchor_plate.py --work $W --annotations $F/seg1_plate_corners.json

# 3. Localize every frame (~7 min for 30 s of 60 fps video on 4 cores)
python $F/localize.py --work $W --video $V

# 4. Overlay video + overlay_stats.json (shown/hidden reasons, slip)
python $F/render_overlay.py --work $W --video $V --output $W/overlay.mp4 --zone 0.40 0.80
```

`seg1_plate_corners.json` holds the corners for the keyframe names that step 1 produces from `seg1.mp4` at 4 fps. A different clip or fps needs new annotations. Check `anchor.json`: `corner_spread_cm` and `regulation_fit_residual_cm` should be a few cm, and a mirror-fit error means two corners are swapped.

| Script | Writes to `--work` |
|---|---|
| `build_map.py` | `images/`, `mask.png`, `database.db`, `sparse/0/` |
| `anchor_plate.py` | `anchor.json` |
| `localize.py` | `localized.json`, `keyframe_to_video.json` |
| `render_overlay.py` | the video, `overlay_stats.json`, `slip.json` |
