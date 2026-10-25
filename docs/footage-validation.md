# Evaluating a footage collection

Use a collection of recordings to measure where the tracker works, where it hides the overlay, and where it displays an incorrect overlay. Keep those outcomes separate. The [October 2026 checkpoint](experiments/field-map-relocalization.md) covers short samples from one recording; it is a baseline for comparison, not a claim about a larger collection.

## Keep a source catalog outside the repository

Give every recording a stable ID. Record its source and permission context, file checksum, game and field, recording date if known, camera and lens mode if known, resolution, frame rate, transfer characteristics such as SDR or HDR, and whether it contains edits or graphics. Mark unknown values as unknown.

Keep the catalog, raw videos, annotations, extracted clips, maps, and results in an external data directory. A small CSV or JSON catalog is sufficient; Python's standard `csv`, `json`, and `hashlib` libraries provide the required functionality without another dependency.

For each query, record the source recording ID, source time interval, map ID, annotation ID, software revision, settings, and result directory. A clip's renamed filename is not sufficient provenance. Keep different encodes and overlapping excerpts linked to their original recording so they cannot silently appear on both sides of an evaluation split.

## Separate reference footage from evaluation footage

A map belongs to a physical field and its reference camera geometry. Build and anchor it using designated reference footage, preferably a pre-game survey or earlier play. Evaluate on later play excluded from map construction and plate anchoring.

Use a development subset for diagnosing failures and selecting parameters. Reserve complete recordings for a final evaluation; randomly splitting adjacent frames leaks nearly identical views across the boundary. Once parameters are chosen, freeze them before evaluating the reserved recordings. Treat threshold changes made after inspecting those results as another development iteration.

Evaluate different questions separately:

| Question | Appropriate comparison |
|---|---|
| Does a field map survive later innings? | Earlier reference footage versus later, excluded play at the same field |
| Does a field map survive surface and lighting changes? | Same-field recordings from different times or days, with the map held fixed |
| Does the workflow work at a different field? | A new reference map for that field, followed by excluded query footage |
| Does another camera work? | Reference and query footage with validated camera/lens geometry for that device |

Do not treat failure to reuse one field's geometry at a different physical field as a camera-localization accuracy test. Do not assume a matching image resolution proves matching intrinsics, lens distortion, digital crop, or stabilization.

## Sample ordinary play and difficult conditions

Start with stratified clips before processing hours end to end. Include routine pitches, catcher occlusion, a visible plate, crouching, head turns, look-down views, moving shadows, worn or disturbed dirt, motion blur, and player changes. Record edits and title graphics as separate conditions. Include night or HDR footage when available, using a compatible decoding pipeline.

Evaluate normal input intervals as well as known failures. Preserve the failing 02:00 checkpoint window in the development set so an improvement cannot conceal a regression in another condition. An aggregate percentage can hide a tracker that works between pitches but disappears during delivery.

Select clips and annotations before seeing the candidate implementation's overlays. Keep a small, representative development set for fast iteration and a broader reserved set for reporting. There is no need to annotate every frame of every recording to get useful evidence.

## Run independent queries reproducibly

The [field-map runbook](../experiments/field_map/README.md) describes mapping, anchoring, and independent-query localization. Each query must match its reference map's resolution and camera geometry. The current field-map scripts use SDR decoding; the prototype's separate HDR reader does not automatically make this experimental pipeline HDR compatible.

For a map built at 1280×720, a uniformly resized four-second query can be prepared as follows:

```bash
# Run from the checkout; choose an external data directory.
FOOTAGE_ROOT=/path/to/footage-and-runs
ffmpeg -ss 120 -i "$FOOTAGE_ROOT/source.mp4" -t 4 -vf scale=1280:720 \
  -an -c:v libx264 -crf 18 "$FOOTAGE_ROOT/query-0200.mp4"

python experiments/field_map/localize.py --work "$FOOTAGE_ROOT/reference-map" \
  --video "$FOOTAGE_ROOT/query-0200.mp4" \
  --output-dir "$FOOTAGE_ROOT/query-0200-results" --workers 2

python experiments/field_map/render_overlay.py --work "$FOOTAGE_ROOT/reference-map" \
  --video "$FOOTAGE_ROOT/query-0200.mp4" \
  --localizations "$FOOTAGE_ROOT/query-0200-results/localized.json" \
  --output "$FOOTAGE_ROOT/query-0200-results/overlay.mp4" --zone 0.40 0.80
```

Use a distinct result directory per query and implementation revision. Keep `localization_info.json`, `localized.json`, `overlay_stats.json`, `slip.json`, and the rendered video together. The videos omit audio.

Each worker owns a descriptor index. Start with one query process and a low worker count; increase concurrency only after measuring memory use. For long recordings, verify actual decoded frame counts, timestamps, and completeness of outputs. Current localization writes its result at completion and does not provide resume checkpoints.

## Measure placement independently

On frames where the plate is visible, annotate its five corners without viewing the candidate overlay. Include multiple viewpoints and distances. Record annotation uncertainty and have another annotator check a subset. About 30 varied visible-plate frames per recording is a useful starting sample, not a substitute for checking difficult conditions.

Report projected-corner errors in pixels, including median, p95, maximum, and the number of annotated frames. Report errors on displayed frames separately from failures that correctly hide the overlay. Do not derive centimeter accuracy from image width alone or report the anchor's own calibration frames as independent ground truth.

Metric accuracy needs an independently measured reference and validated camera calibration. Batter-specific top and bottom heights need their own measurement protocol; a stable plate footprint does not validate the elevated zone. Occluded-plate frames can support tracking-consistency checks, but they do not reveal the hidden plate's true pixel coordinates by themselves.

## Report failures as well as coverage

For each recording and condition, retain:

- Processed frame count and expected duration, with any gaps or decode failures.
- Overlay-enabled fraction, separated into pitch delivery, between-pitch activity, and camera looks away.
- Hide reasons, duration of hidden intervals, and time to reacquire after a loss or cut.
- Visible-plate corner errors and confidently displayed failures, with example frames.
- Slip distributions, including outliers and the number of valid frame pairs. Mark cuts, moving graphics, and foreground contamination.
- Processing time, peak memory, worker count, hardware, and whether another run competed for resources.

Summarize by recording and condition before pooling frames. A long easy recording should not conceal failures in a shorter difficult game. Keep coverage, placement accuracy, and speed as separate measures.

## Diagnose before changing thresholds

Distinguish missing reference coverage, weak feature matches, incorrect calibration, ambiguous geometry, moving objects, and decoding problems. More inliers or more registered reference images do not guarantee a physically correct map. Check camera locations, metric scale, anchor stability, and held-out projected targets before accepting a map change.

Compare candidate changes on the same development clips and preserve the existing display gates unless independent evidence supports changing them. Rerun unaffected examples as well as the original failure. Evaluate the reserved recordings with the chosen settings only after those checks pass.

This process supports decisions about map construction, confidence calibration, memory and runtime improvements, batter measurements, and device integration. It does not establish those capabilities merely by collecting more footage.
