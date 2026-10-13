// Source-independent calibrated pinhole projection.
// A row-major 4x4 matrix maps WORLD points into CV camera coordinates:
// X right, Y down, Z forward (meters). Intrinsics use pixels.
export function transformPoint(m, p) {
  if (!Array.isArray(m) || m.length !== 16) throw new TypeError('Expected 4x4 row-major matrix');
  const [x,y,z] = p;
  return [
    m[0]*x+m[1]*y+m[2]*z+m[3],
    m[4]*x+m[5]*y+m[6]*z+m[7],
    m[8]*x+m[9]*y+m[10]*z+m[11]
  ];
}
export function projectPoint(point, worldToCamera, {fx,fy,cx,cy}) {
  const [x,y,z]=transformPoint(worldToCamera,point);
  if (![fx,fy,cx,cy].every(Number.isFinite) || fx <= 0 || fy <= 0)
    throw new RangeError('Invalid camera intrinsics');
  if (z <= 0.001) return null;
  return [fx*x/z+cx,fy*y/z+cy];
}
export function projectZone(zone, worldToCamera, intrinsics) {
  return zone.edges.map(([i,j]) => [
    projectPoint(zone.vertices[i],worldToCamera,intrinsics),
    projectPoint(zone.vertices[j],worldToCamera,intrinsics)
  ]).filter(([a,b])=>a!==null && b!==null);
}
