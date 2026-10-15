// Loaded by ar-placement.e2e.mjs before src/main.js (served by Vite so the bare
// import resolves). Emulates a WebXR AR headset so ARButton offers AR, and
// exposes __aimAt / __tap for the test to drive placement.
import { XRDevice, metaQuest3 } from 'iwer';
// Minimal Synthetic Environment Module: one infinite floor at y = 0.
class FloorSEM {
  version = 'floor-test';
  planesVisible = false; boundingBoxesVisible = false; meshesVisible = false;
  render() {} loadEnvironment() {} async loadDefaultEnvironment() {} deleteAll() {}
  get environmentCanvas() { return document.createElement('canvas'); }
  get trackedPlanes() { return new Set(); }
  get trackedMeshes() { return new Set(); }
  computeDepthBuffer() { return null; }
  computeHitTestResults(m) {           // m: column-major ray pose; ray is its -Z axis
    const o = [m[12], m[13], m[14]], d = [-m[8], -m[9], -m[10]];
    if (d[1] > -1e-6 || o[1] <= 0) return [];
    const t = -o[1] / d[1];
    const hit = new Float32Array([1,0,0,0, 0,1,0,0, 0,0,1,0, o[0]+t*d[0], 0, o[2]+t*d[2], 1]);
    return [hit];
  }
}
const device = new XRDevice(metaQuest3);
device.installRuntime({ forceInstall: true });
device.installSEM(FloorSEM);
window.__xr = device;
// Look straight down from 1.5 m above a floor point, so the viewer ray hits it.
window.__aimAt = (x, z) => {
  device.position.set(x, 1.5, z);
  device.quaternion.set(-Math.SQRT1_2, 0, 0, Math.SQRT1_2);
};
const frames = n => new Promise(r => { const f = () => (--n <= 0 ? r() : requestAnimationFrame(f)); requestAnimationFrame(f); });
// Press and release the trigger of the controller three.js listens to (input source 0).
window.__tap = async () => {
  const hand = device.activeSession.inputSources[0].handedness;
  const c = device.controllers[hand];
  await frames(4);                      // let the hit-test reticle settle on the new aim
  c.updateButtonValue('trigger', 1); await frames(3);
  c.updateButtonValue('trigger', 0); await frames(3);
};
