import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { ARButton } from 'three/addons/webxr/ARButton.js';
import { PRESETS, plateFootprint, makeZone, plateFromTwoPoints } from './geometry.js';
import './style.css';

const stage = document.querySelector('#stage');
const status = document.querySelector('#status');
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.xr.enabled = true;
stage.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color('#15263a');
scene.add(new THREE.HemisphereLight(0xffffff, 0x677889, 2.6));
const camera = new THREE.PerspectiveCamera(58, innerWidth / innerHeight, 0.01, 80);
camera.position.set(1.4, 1.6, 3.0);
const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 0.8, 0);
controls.enableDamping = true;
controls.update();

const ground = new THREE.Mesh(new THREE.PlaneGeometry(20,20),
  new THREE.MeshStandardMaterial({color:0x6d604d,roughness:1,side:THREE.DoubleSide}));
ground.rotation.x = -Math.PI/2; ground.position.y = -0.008;
scene.add(ground);

const grid = new THREE.GridHelper(8, 16, 0x748298, 0x525d69);
grid.position.y = -0.003; scene.add(grid);
const origin = new THREE.Group();
scene.add(origin);

function line(points, color, opacity=1) {
  const geometry = new THREE.BufferGeometry().setFromPoints(points.map(p => new THREE.Vector3(...p)));
  const material = new THREE.LineBasicMaterial({color,transparent:opacity<1,opacity,depthTest:true});
  return new THREE.LineSegments(geometry, material);
}
function segment(a,b,r,color) {
  const v1=new THREE.Vector3(...a),v2=new THREE.Vector3(...b);
  const dir=new THREE.Vector3().subVectors(v2,v1);
  const length=dir.length();
  const mesh=new THREE.Mesh(new THREE.CylinderGeometry(r,r,length,8),
    new THREE.MeshStandardMaterial({color,roughness:.85}));
  mesh.position.copy(v1).addScaledVector(dir,.5);
  mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),dir.normalize());
  return mesh;
}
function plate() {
  const pts=plateFootprint();
  const positions=pts.flatMap(([x,z])=>[x,0.002,z]);
  const geometry=new THREE.BufferGeometry();
  geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));
  geometry.setIndex([0,1,2,0,2,4,2,3,4]);
  geometry.computeVertexNormals();
  const surface=new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({color:0xf0f2f0,side:THREE.DoubleSide,roughness:.9}));
  const border=[];
  for(let i=0;i<5;i++){const a=pts[i],b=pts[(i+1)%5];border.push([a[0],.005,a[1]],[b[0],.005,b[1]]);}
  const group=new THREE.Group();
  group.add(surface,line(border,0x233241));
  return {group,surface};
}
// In AR the opaque virtual plate would hide the real one, which is the only
// visual check of alignment; keep just its outline there.
const {group:plateGroup,surface:plateSurface}=plate();
origin.add(plateGroup);

let zoneMesh=null;
let batterMesh=null;
let preset='short';
let yawRad=0;
const els={
  batter:document.querySelector('#batter'),
  bottom:document.querySelector('#bottom'),
  top:document.querySelector('#top'),
  yaw:document.querySelector('#yaw'),
  batterVisible:document.querySelector('#batterVisible')
};
function dispose(group) {
  if (!group) return;
  group.traverse(n=>{n.geometry?.dispose();if(n.material){if(Array.isArray(n.material))n.material.forEach(x=>x.dispose());else n.material.dispose();}});
  group.parent?.remove(group);
}
function silhouette(height) {
  const figure=new THREE.Group();
  figure.position.x=.73;
  const hip=height*.51, shoulder=height*.79, head=height*.91;
  const s=.042;
  const c=0x80a7ca;
  for(const [a,b,r] of [
    [[-.12,.07,0],[-.10,hip,0],s],[[.12,.07,0],[.10,hip,0],s],
    [[0,hip,0],[0,shoulder,0],.075],
    [[0,shoulder,0],[-.21,height*.62,0],s*.75],
    [[0,shoulder,0],[.21,height*.62,0],s*.75],
  ]) figure.add(segment(a,b,r,c));
  const sphere=new THREE.Mesh(new THREE.SphereGeometry(height*.060,16,12),
    new THREE.MeshStandardMaterial({color:0xc6d5e4}));
  sphere.position.y=head;
  figure.add(sphere);
  return figure;
}
function refresh() {
  const bottom=Number(els.bottom.value);
  const top=Number(els.top.value);
  if (top<=bottom) {status.textContent='Invalid zone: top must be above bottom.';return;}
  const z=makeZone(bottom,top);
  const pts=z.edges.flatMap(([a,b])=>[z.vertices[a],z.vertices[b]]);
  dispose(zoneMesh);zoneMesh=new THREE.Group();
  zoneMesh.add(line(pts,0xffcf52));
  // Upper/lower planes give depth cues; the true boundary is the 5-sided prism.
  for(const y of [bottom,top]){
    const outline=plateFootprint().map(([x,z])=>new THREE.Vector3(x,y,z));
    const polygon=new THREE.Shape(plateFootprint().map(([x,z])=>new THREE.Vector2(x,z)));
    const geometry=new THREE.ShapeGeometry(polygon);
    geometry.rotateX(Math.PI/2);
    geometry.translate(0,y,0);
    const mesh=new THREE.Mesh(geometry,new THREE.MeshBasicMaterial({
      color:0xfac950,transparent:true,opacity:.09,depthWrite:false,side:THREE.DoubleSide
    }));
    zoneMesh.add(mesh);
  }
  origin.add(zoneMesh);
  dispose(batterMesh);
  batterMesh=silhouette(PRESETS[preset].heightM);
  origin.add(batterMesh);
  batterMesh.visible=els.batterVisible.checked && !renderer.xr.isPresenting;
  plateSurface.visible=!renderer.xr.isPresenting;
  origin.rotation.y=yawRad;
  document.querySelector('#bottomOut').textContent=(bottom/0.0254).toFixed(1)+' in';
  document.querySelector('#topOut').textContent=(top/0.0254).toFixed(1)+' in';
  document.querySelector('#yawOut').textContent=els.yaw.value+'°';
}
function applyPreset(){
  const p=PRESETS[preset];
  els.bottom.value=p.bottomM;
  els.top.value=p.topM;
  refresh();
}
els.batter.value='short';
els.batter.addEventListener('change',()=>{preset=els.batter.value;applyPreset();});
for(const id of ['top','bottom','batterVisible'])
  els[id].addEventListener('input',refresh);
els.yaw.addEventListener('input',()=>{yawRad=THREE.MathUtils.degToRad(Number(els.yaw.value));refresh();});
applyPreset();

// AR placement is two taps: the plate's back tip, then the midpoint of its front
// edge. That fixes position AND heading, and the tapped span is checked against
// the real 17-inch centerline. Hit results are surface points, NOT recognition of
// home plate or a calibrated plate pose.
const MAX_SPAN_ERROR_M=0.03;
let hitSource=null,requesting=false,placed=false,apexTap=null;
const reticle=new THREE.Mesh(new THREE.RingGeometry(.09,.11,32),
  new THREE.MeshBasicMaterial({color:0x7be7ff,side:THREE.DoubleSide}));
reticle.rotation.x=-Math.PI/2;
reticle.visible=false;
scene.add(reticle);

const controller=renderer.xr.getController(0);
scene.add(controller);
controller.addEventListener('select',()=>{
  if(placed || !reticle.visible) return;
  const tap=reticle.position.toArray();
  tap[1]-=.006;
  if(!apexTap){
    apexTap=tap;
    status.textContent='Back tip set. Now tap the MIDDLE of the plate\'s FRONT edge (pitcher side).';
    return;
  }
  let pose;
  try { pose=plateFromTwoPoints(apexTap,tap); }
  catch(err){ apexTap=null; status.textContent=err.message+'. Tap the back tip again.'; return; }
  apexTap=null;
  const errIn=(pose.spanErrorM/0.0254).toFixed(1);
  if(Math.abs(pose.spanErrorM)>MAX_SPAN_ERROR_M){
    status.textContent=`Tapped span off by ${errIn} in (limit ${(MAX_SPAN_ERROR_M/0.0254).toFixed(1)} in). Not placed; tap the back tip again.`;
    return;
  }
  origin.position.set(...pose.position);
  yawRad=pose.yawRad;
  els.yaw.value=Math.round(THREE.MathUtils.radToDeg(yawRad));
  refresh();
  origin.visible=true;
  reticle.visible=false;
  placed=true;
  status.textContent=`AR placement set (span error ${errIn} in). Zone bounds are MANUAL. Re-enter AR to re-place.`;
});
renderer.xr.addEventListener('sessionstart',()=>{
  controls.enabled=false;
  ground.visible=false;grid.visible=false;scene.background=null;
  origin.visible=false;reticle.visible=false;
  requesting=false;hitSource=null;placed=false;apexTap=null;
  refresh();
  status.textContent='AR: aim at the BACK TIP of home plate (catcher side); tap when the cyan reticle is on it.';
});
renderer.xr.addEventListener('sessionend',()=>{
  hitSource?.cancel();hitSource=null;requesting=false;placed=false;apexTap=null;
  controls.enabled=true;
  ground.visible=true;grid.visible=true;scene.background=new THREE.Color('#15263a');
  origin.visible=true;origin.position.set(0,0,0);reticle.visible=false;
  refresh();
  status.textContent='Desktop simulation: drag to orbit, scroll to zoom.';
});
// Make the control panel the WebXR DOM overlay so the sliders stay usable in AR.
// Without this, three's ARButton supplies an overlay holding only an exit button.
const panel=document.querySelector('.panel');
// Touches on the panel must not also count as placement taps.
panel.addEventListener('beforexrselect',e=>e.preventDefault());
try {
  document.querySelector('#ar-button-container').appendChild(
    ARButton.createButton(renderer,{requiredFeatures:['hit-test'],
      optionalFeatures:['local-floor','dom-overlay'],domOverlay:{root:panel}})
  );
} catch (error) {
  status.textContent='AR unavailable in this browser: '+error.message;
}

async function ensureHitTest(session) {
  if (requesting || hitSource) return;
  requesting=true;
  try {
    const viewer=await session.requestReferenceSpace('viewer');
    hitSource=await session.requestHitTestSource({space:viewer});
  } catch(err){status.textContent='Hit-test setup failed: '+err.message;}
}
renderer.setAnimationLoop((_,frame)=>{
  if(frame && !placed){
    const session=renderer.xr.getSession();
    if(session) {
      if(!hitSource) {void ensureHitTest(session);}
      else {
        const hits=frame.getHitTestResults(hitSource);
        if(hits.length){
          const pose=hits[0].getPose(renderer.xr.getReferenceSpace());
          if(pose){
            reticle.position.set(pose.transform.position.x,pose.transform.position.y+.006,pose.transform.position.z);
            reticle.visible=true;
          }
        } else reticle.visible=false;
      }
    }
  }
  if(!renderer.xr.isPresenting) controls.update();
  renderer.render(scene,camera);
});
window.addEventListener('resize',()=>{
  camera.aspect=innerWidth/innerHeight;camera.updateProjectionMatrix();
  renderer.setSize(innerWidth,innerHeight);
});
