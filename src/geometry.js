// Physical units and a renderer-agnostic, plate-centered coordinate system.
// +X: first-base side; +Y: up; -Z: toward pitcher; +Z: toward catcher.
// The origin is the center of home plate's bounding 17-inch square at ground level.
export const INCH_M = 0.0254;
export const PLATE_WIDTH_M = 17 * INCH_M;
export const PLATE_DEPTH_M = 17 * INCH_M;

export const PRESETS = Object.freeze({
  short: Object.freeze({ label: '5′0″', heightM: 1.524, bottomM: 0.39, topM: 0.95 }),
  tall: Object.freeze({ label: '6′3″', heightM: 1.905, bottomM: 0.50, topM: 1.19 })
});

// Illustrative boundaries, not measured body landmarks and not league-certified.
export function plateFootprint() {
  const halfW = PLATE_WIDTH_M / 2;
  const halfD = PLATE_DEPTH_M / 2;
  return [
    [-halfW, -halfD], [halfW, -halfD],
    [halfW, 0], [0, halfD], [-halfW, 0]
  ];
}

export function makeZone(bottomM, topM) {
  if (!Number.isFinite(bottomM) || !Number.isFinite(topM) ||
      bottomM < 0 || topM <= bottomM || topM > 3) {
    throw new RangeError('Zone requires 0 <= bottomM < topM <= 3, in meters');
  }
  const footprint = plateFootprint();
  const vertices = [
    ...footprint.map(([x,z]) => [x,bottomM,z]),
    ...footprint.map(([x,z]) => [x,topM,z])
  ];
  const edges = [];
  for (let i = 0; i < 5; i++) {
    const next = (i + 1) % 5;
    edges.push([i,next],[i+5,next+5],[i,i+5]);
  }
  return { bottomM, topM, vertices, edges, widthM: PLATE_WIDTH_M, depthM: PLATE_DEPTH_M };
}

// Structured adapter-friendly payload for XR, saved camera tracks and video rendering.
export function makeZoneFrame({ bottomM, topM, worldFromPlate = identity4() }) {
  if (!Array.isArray(worldFromPlate) || worldFromPlate.length !== 16 ||
      worldFromPlate.some(x => !Number.isFinite(x))) {
    throw new TypeError('worldFromPlate must be a 16-element row-major matrix');
  }
  return { coordinateSystem: 'x-right-y-up-z-toward-catcher', units: 'meters',
    worldFromPlate: [...worldFromPlate], zone: makeZone(bottomM,topM) };
}

export function identity4() { return [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]; }
