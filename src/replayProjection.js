/** Independently calibrated Brown-Conrady projection for tracking JSON replay.
 * Matrices are row-major. World axes: X right, Y up, Z catcher.
 */
import { makeZone } from './geometry.js';

export function projectCalibrated(p, worldToCamera, K, distortion = [0,0,0,0,0]) {
  if (!Array.isArray(worldToCamera) || worldToCamera.length !== 16 ||
      !Array.isArray(K) || K.length !== 3 || !K.every(r=>Array.isArray(r)&&r.length===3))
    throw new TypeError('Invalid camera matrix/pose');
  const [x,y,z]=p;
  const a=worldToCamera;
  const px=a[0]*x+a[1]*y+a[2]*z+a[3];
  const py=a[4]*x+a[5]*y+a[6]*z+a[7];
  const pz=a[8]*x+a[9]*y+a[10]*z+a[11];
  if (pz<=.001 || !Number.isFinite(pz)) return null;
  const nx=px/pz, ny=py/pz;
  const r2=nx*nx+ny*ny,r4=r2*r2,r6=r4*r2;
  const [k1=0,k2=0,p1=0,p2=0,k3=0,k4=0,k5=0,k6=0]=distortion;
  const denominator=1+k4*r2+k5*r4+k6*r6;
  if (Math.abs(denominator)<1e-9) return null;
  const radial=(1+k1*r2+k2*r4+k3*r6)/denominator;
  const xd=nx*radial+2*p1*nx*ny+p2*(r2+2*nx*nx);
  const yd=ny*radial+p1*(r2+2*ny*ny)+2*p2*nx*ny;
  const u=K[0][0]*xd+K[0][1]*yd+K[0][2];
  const v=K[1][0]*xd+K[1][1]*yd+K[1][2];
  return Number.isFinite(u)&&Number.isFinite(v)?[u,v]:null;
}
export function projectTrackedZone(record, camera) {
  if(!record || !record.zone || !record.world_to_camera)return [];
  const z=makeZone(record.zone.bottom_m,record.zone.top_m);
  const corners=z.vertices.map(p=>projectCalibrated(p,record.world_to_camera,camera.matrix,camera.distortion));
  return z.edges.filter(([i,j])=>corners[i]&&corners[j]).map(([i,j])=>[corners[i],corners[j]]);
}
export function validTrackingRecord(record) {
  return !!(record?.world_to_camera?.length===16 &&
    Number.isFinite(record?.reprojection_px) && record.reprojection_px <= 2.5 &&
    record?.zone?.top_m > record?.zone?.bottom_m);
}
