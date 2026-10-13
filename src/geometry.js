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

// Back tip (apex) to front-edge midpoint of a regulation plate, along the plate centerline.
export const PLATE_CENTERLINE_M = PLATE_DEPTH_M;

// Plate pose from two surface points tapped in a y-up world frame: the back tip
// (apex, catcher side) and the midpoint of the front edge (pitcher side).
// Returns the center of the 17-inch bounding square and a yaw about +Y such that
// plate-local -Z (toward pitcher) points from apex to front. spanErrorM compares the
// tapped distance with the true one; a large value means a mis-tap or poor hit-test.
export function plateFromTwoPoints(apex, front) {
  if (![...apex, ...front].every(Number.isFinite) || apex.length !== 3 || front.length !== 3)
    throw new TypeError('Expected two finite [x,y,z] points');
  const dx = front[0] - apex[0], dz = front[2] - apex[2];
  const spanM = Math.hypot(dx, dz);
  if (spanM < 0.05) throw new RangeError('Tapped points are too close to define a heading');
  return {
    position: [(apex[0]+front[0])/2, (apex[1]+front[1])/2, (apex[2]+front[2])/2],
    yawRad: Math.atan2(-dx, -dz),
    spanM,
    spanErrorM: spanM - PLATE_CENTERLINE_M
  };
}
