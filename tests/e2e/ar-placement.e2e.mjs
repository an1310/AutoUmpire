// End-to-end AR placement test in headless Chromium with an emulated WebXR
// headset (Meta's IWER runtime) and a flat synthetic floor for hit-testing.
// It drives the real simulator page: Start AR, aim, tap, read the result.
//
// Not covered: dom-overlay (IWER does not emulate it, so the AR control panel
// and beforexrselect suppression still need a real device) and rendering.
//
// Run: npm run test:ar   (set CHROMIUM_PATH to use a preinstalled browser)
import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { chromium } from 'playwright';
import { PLATE_DEPTH_M } from '../../src/geometry.js';


let server, browser, baseUrl;

test.before(async () => {
  server = await createServer({ server: { port: 0, host: '127.0.0.1' }, logLevel: 'silent' });
  await server.listen();
  baseUrl = server.resolvedUrls.local[0];
  browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
});
test.after(async () => { await browser?.close(); await server?.close(); });

async function startAr() {
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.route(/\/$|index\.html$/, async route => {
    const res = await route.fetch();
    // The harness must run first so ARButton sees an AR-capable device.
    const html = (await res.text()).replace('<script type="module" src="/src/main.js">',
      '<script type="module" src="/tests/e2e/xr-harness.js"></script>\n  <script type="module" src="/src/main.js">');
    await route.fulfill({ response: res, body: html });
  });
  await page.goto(baseUrl);
  const button = page.locator('#ar-button-container button');
  await page.waitForFunction(() => /START AR/i.test(document.querySelector('#ar-button-container button')?.textContent || ''));
  await button.click();
  await page.waitForFunction(() => /BACK TIP/.test(document.querySelector('#status').textContent));
  await page.waitForFunction(() => window.__xr.activeSession?.inputSources.length > 0);
  return { page, errors };
}
const status = page => page.textContent('#status');

// Apex (back tip) and front-edge midpoint of a plate centered at (cx, cz), turned by yaw.
function plateTaps(cx, cz, yawRad, span = PLATE_DEPTH_M) {
  const at = s => [cx + s * Math.sin(yawRad), cz + s * Math.cos(yawRad)];
  return { apex: at(span / 2), front: at(-span / 2) };
}

test('two taps on a rotated plate set placement and heading', async () => {
  const { page, errors } = await startAr();
  const yawDeg = 37;
  const { apex, front } = plateTaps(0.4, -1.2, yawDeg * Math.PI / 180);
  await page.evaluate(([x, z]) => window.__aimAt(x, z), apex);
  await page.evaluate(() => window.__tap());
  assert.match(await status(page), /FRONT edge/);
  await page.evaluate(([x, z]) => window.__aimAt(x, z), front);
  await page.evaluate(() => window.__tap());
  const text = await status(page);
  assert.match(text, /AR placement set \(span error -?0\.\d in\)/, text);
  assert.equal(Number(await page.inputValue('#yaw')), yawDeg);
  assert.deepEqual(errors, []);
  await page.close();
});

test('a tapped span far from 17 in is refused and placement restarts', async () => {
  const { page, errors } = await startAr();
  const { apex, front } = plateTaps(0, -1, 0, 0.60);   // 0.60 m apart, plate is 0.43 m
  await page.evaluate(([x, z]) => window.__aimAt(x, z), apex);
  await page.evaluate(() => window.__tap());
  await page.evaluate(([x, z]) => window.__aimAt(x, z), front);
  await page.evaluate(() => window.__tap());
  assert.match(await status(page), /Tapped span off by 6\.6 in .*Not placed; tap the back tip again/);
  // The flow restarted: a correct pair now places the plate.
  const ok = plateTaps(0, -1, 0);
  await page.evaluate(([x, z]) => window.__aimAt(x, z), ok.apex);
  await page.evaluate(() => window.__tap());
  await page.evaluate(([x, z]) => window.__aimAt(x, z), ok.front);
  await page.evaluate(() => window.__tap());
  assert.match(await status(page), /AR placement set/);
  assert.equal(Number(await page.inputValue('#yaw')), 0);
  assert.deepEqual(errors, []);
  await page.close();
});
