import test from 'node:test';
import assert from 'node:assert/strict';
import {projectCalibrated,projectTrackedZone,validTrackingRecord} from '../src/replayProjection.js';
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
