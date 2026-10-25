# Field map from umpire-POV video (experiment)

Markerless plate localization: build a 3D map of the field, anchor home plate in it, localize every frame, draw the zone fail-closed. Results, numbers and limits: [docs/experiments/field-map-umpire-pov.md](../../docs/experiments/field-map-umpire-pov.md).

Separate from the prototype; synthetic localization/rendering regressions run in CI. Keep raw footage, full-frame keyframes, rendered videos, `--work`, and query results outside the repository. The main README uses only tightly cropped plate-area examples without identifiable people.

Current measured results: [independent-video checkpoint](../../docs/experiments/field-map-relocalization.md). For a larger collection, use the [footage-validation guide](../../docs/footage-validation.md).

## Setup

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r experiments/field_map/requirements.txt   # pycolmap is pinned; its API moves between releases
```

`ffmpeg` must be on `PATH` (keyframe extraction).

## Run

```bash
V=seg1.mp4; W=../runs/seg1; F=experiments/field_map

# 1. Map: keyframes, mask the burned-in scoreboard, structure-from-motion (~8 min on 4 cores; the map varies slightly run to run)
python $F/build_map.py --video $V --work $W --fps 4 --mask-box 0 0 475 62 --camera-params 580,640,360,0,0

# 2. Anchor the plate. Corner pixels are hand-marked in keyframes ($W/images/f*.jpg),
#    order front_left, front_right, right_side_bottom, back_tip, left_side_bottom (left = 3rd-base side)
python $F/anchor_plate.py --work $W --annotations $F/seg1_plate_corners.json

# 3. Localize every frame against all mapped landmarks (offline CPU processing)
python $F/localize.py --work $W --video $V

# 4. Overlay video + overlay_stats.json (shown/hidden reasons, slip)
python $F/render_overlay.py --work $W --video $V --output $W/overlay.mp4 --zone 0.40 0.80
```

`seg1_plate_corners.json` holds the corners for the keyframe names that step 1 produces from `seg1.mp4` at 4 fps. A different clip or fps needs new annotations. Check `anchor.json`: `corner_spread_cm` and `regulation_fit_residual_cm` should be a few cm, and a mirror-fit error means two corners are swapped.

## Localize a separate recording

The map is a reference, not a timeline. The localizer searches every mapped landmark with OpenCV FLANN and extracts query features with COLMAP's own RootSIFT extractor. It reads the original descriptors from `database.db`, using their exact observation indices in `sparse/0`; keep those files together. Reference JPEGs and knowledge of the query's position in the original recording are unnecessary.

Several descriptors can be observations of one 3D landmark. The 0.9 ratio test compares the best match with the nearest **different landmark**, expanding the search when a long landmark track fills the neighbor list. This admits less distinctive candidates for the unchanged 4-pixel RANSAC check; it does not lower the renderer's acceptance thresholds. A landmark supplies at most one pose correspondence; identical descriptors belonging to different landmarks are ambiguous and rejected.

Feature loading uses Python's standard SQLite reader in read-only mode. COLMAP's database opener initializes the schema and takes write locks even when used to read features; read-only access allows concurrent queries and maps on read-only storage. This reader targets the pinned COLMAP 4.2.1 schema and validates descriptor type, dimensions, image names, and observation coordinates against the reconstruction.

Use an independent result directory for each query:

```bash
W=../runs/seg1; Q=../runs/later-play; F=experiments/field_map
python $F/localize.py --work "$W" --video later-play.mp4 --output-dir "$Q"
python $F/render_overlay.py --work "$W" --video later-play.mp4 \
  --localizations "$Q/localized.json" --output "$Q/overlay.mp4" --zone 0.40 0.80
```

The query must have the map's image resolution and lens geometry. For a full-frame 3840×2160 source and a map made from its 1280×720 version, resize uniformly without cropping:

```bash
ffmpeg -i source.mp4 -vf scale=1280:720 -an -c:v libx264 -crf 18 query.mp4
```

Resizing does not compensate for a different camera, lens mode, digital crop or changing electronic stabilization. The localizer rejects a resolution mismatch. The field-map scripts currently decode SDR through OpenCV; use the prototype's separate HDR reader for HDR work.

`--max-features` defaults to COLMAP's 8192; `--workers` defaults to 4. Each worker keeps its own descriptor index, so memory and processing cost grow with map size and worker count. Reduce `--workers` if memory pressure rises, and run queries sequentially before adding parallel query processes. Localization is offline. `localization_info.json` records the source map, query, resolution and extraction/pose settings.

The renderer retains its 60-inlier, map-support, continuity and reacquisition gates. Better retrieval does not guarantee adequate map coverage, correct calibration or absolute plate accuracy. Validate on footage excluded from both mapping and anchoring; report hidden frames as well as enabled frames. The historical results in the experiment write-up describe the earlier timestamp-based matcher, not this implementation.

Run the synthetic regressions with:

```bash
python -W error::ResourceWarning -m unittest discover -s experiments/field_map/tests -v
```

| Script | Writes to `--work` |
|---|---|
| `build_map.py` | `images/`, `mask.png`, `database.db`, `sparse/0/` |
| `anchor_plate.py` | `anchor.json` |
| `localize.py` | `localized.json`, `localization_info.json` in `--output-dir` (default: `--work`) |
| `render_overlay.py` | the video, `overlay_stats.json`, `slip.json` beside `--output` |
