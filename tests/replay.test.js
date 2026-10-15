import test from 'node:test';
import assert from 'node:assert/strict';
import {makeZone,plateFootprint} from '../src/geometry.js';
import {frameAtTime,projectCalibrated,projectTrackedZone,validTrackingRecord} from '../src/replayProjection.js';
const matrix=[1,0,0,0,0,1,0,0,0,0,1,3,0,0,0,1];
const K=[[1000,0,640],[0,1000,360],[0,0,1]];
test('replay pinhole projection and lens distortion',()=>{
  assert.deepEqual(projectCalibrated([0,0,0],matrix,K),[640,360]);
  assert.equal(projectCalibrated([0,0,-4],matrix,K),null);
  const p=projectCalibrated([.2,.1,0],matrix,K,[.2,0,0,0,0]);
  assert.ok(p[0]>706.6);
});
test('replay zone is 15 connected 3D segments',()=>{
  const pose={world_to_camera:matrix,reprojection_px:.5,zone:{bottom_m:.4,top_m:1}};
  assert.equal(projectTrackedZone(pose,{matrix:K,distortion:[0,0,0,0,0]}).length,15);
  assert.equal(validTrackingRecord(pose),true);
  assert.equal(validTrackingRecord({...pose,reprojection_px:3}),false);
  assert.equal(validTrackingRecord(null),false);
});
test('playback time maps to the nearest tracked frame, not frame*fps',()=>{
  // Variable-rate clip: 40, 120, 40 ms intervals.
  const times=[0,.04,.16,.2];
  assert.equal(frameAtTime(times,0),0);
  assert.equal(frameAtTime(times,.09),1);  // nearer .04 than .16
  assert.equal(frameAtTime(times,.11),2);
  assert.equal(frameAtTime(times,.2),3);
  assert.equal(Math.round(.16*25),4);      // the fixed-fps rule names a frame that does not exist
  assert.equal(frameAtTime(times,.3),-1);  // past the end
  assert.equal(frameAtTime(times,-.05),-1);
  assert.equal(frameAtTime([],0),-1);
  assert.equal(frameAtTime([.5],.5),0);
});
test('browser geometry and lens model match the shared OpenCV fixture',async()=>{
  const {readFile}=await import('node:fs/promises');
  const g=JSON.parse(await readFile(new URL('./fixtures/projection_golden.json',import.meta.url)));
  const close=(a,b,tol)=>a.forEach((v,i)=>assert.ok(Math.abs(v-b[i])<=tol,`${v} vs ${b[i]}`));
  plateFootprint().forEach((p,i)=>close(p,g.plate_xz[i],1e-12));
  const zone=makeZone(g.zone.bottom_m,g.zone.top_m);
  zone.vertices.forEach((v,i)=>close(v,g.zone_vertices[i],1e-12));
  const key=e=>[...e].sort((a,b)=>a-b).join('-');
  assert.deepEqual(zone.edges.map(key).sort(),g.edges.map(key).sort());
  g.zone_vertices.forEach((v,i)=>
    close(projectCalibrated(v,g.world_to_camera,g.camera.matrix,g.camera.distortion),g.pixels[i],1e-6));
});
