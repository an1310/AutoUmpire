import test from 'node:test';
import assert from 'node:assert/strict';
import {INCH_M,PLATE_WIDTH_M,PLATE_DEPTH_M,PRESETS,plateFootprint,makeZone,makeZoneFrame} from '../src/geometry.js';
import {projectPoint,projectZone} from '../src/projection.js';

test('home plate spans exactly 17 inches across the front edge',()=>{
  const p=plateFootprint();assert.equal(p.length,5);
  assert.ok(Math.abs(p[1][0]-p[0][0]-17*INCH_M)<1e-12);
  assert.equal(PLATE_WIDTH_M,PLATE_DEPTH_M);
});
test('pentagonal prism has 10 vertices and 15 edges',()=>{
  const z=makeZone(.4,1);
  assert.equal(z.vertices.length,10);
  assert.equal(z.edges.length,15);
  assert.equal(z.vertices[0][1],.4);
  assert.equal(z.vertices[5][1],1);
});
test('5 foot and 6 foot 3 zones have distinct heights',()=>{
  const a=PRESETS.short,b=PRESETS.tall;
  assert.ok(a.heightM<b.heightM && a.topM<b.topM && a.bottomM<b.bottomM);
});
test('zone rejects inverted and invalid boundaries',()=>{
  for(const p of [[1,.9],[-.1,.4],[.4,4],[NaN,1],[.5,.5]])
    assert.throws(()=>makeZone(...p),RangeError);
});
test('calibration frame validates row-major 4x4 matrix',()=>{
  assert.equal(makeZoneFrame({bottomM:.4,topM:1}).worldFromPlate[15],1);
  assert.throws(()=>makeZoneFrame({bottomM:.4,topM:1,worldFromPlate:[1,2]}),TypeError);
});
test('camera projection uses standard pinhole intrinsics',()=>{
  const eye=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1];
  assert.deepEqual(projectPoint([0,0,2],eye,{fx:800,fy:800,cx:640,cy:360}),[640,360]);
  assert.deepEqual(projectPoint([1,0,2],eye,{fx:800,fy:800,cx:640,cy:360}),[1040,360]);
});
test('points behind camera are not projected',()=>{
  const eye=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1];
  assert.equal(projectPoint([0,0,-1],eye,{fx:1,fy:1,cx:0,cy:0}),null);
});
test('projected zone returns up to 15 line segments with a valid pose',()=>{
  // Offset world forward by 3 m in CV camera coordinates.
  const w2c=[1,0,0,0,0,-1,0,0,0,0,1,3,0,0,0,1];
  const result=projectZone(makeZone(.4,1),w2c,{fx:1000,fy:1000,cx:960,cy:540});
  assert.equal(result.length,15);
  assert.ok(result.every(([a,b])=>[...a,...b].every(Number.isFinite)));
});
