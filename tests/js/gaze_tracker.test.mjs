/**
 * Unit tests for SimpleGazeTracker's sample handling and status reporting.
 *
 * Every test here corresponds to a bug that shipped and that neither the Python
 * unit tests nor the Playwright end-to-end suite could catch.
 *
 *   node --test tests/js
 */

import test from 'node:test';
import assert from 'node:assert/strict';
import { makeDom, makeRoiElement, loadTracker, gazeResult } from './harness.mjs';

const FIELD_IDS = [
  'eyetrack_sample_count',
  'eyetrack_gaze_data',
  'eyetrack_init_status',
  'eyetrack_calibration_restored',
  'eyetrack_viewport_width',
  'eyetrack_viewport_height',
  'eyetrack_viewport_changed',
  'eyetrack_rois',
  'eyetrack_runtime_error',
];

function newTracker(opts = {}) {
  const dom = makeDom({ elementIds: FIELD_IDS, ...opts });
  const SimpleGazeTracker = loadTracker(dom);
  const tracker = new SimpleGazeTracker({});
  return { tracker, dom };
}

test('a frame with no face is not recorded as a look at the screen centre', () => {
  const { tracker } = newTracker();
  tracker.isInitialized = true;
  tracker.startTracking();

  tracker.handleGazeResult(gazeResult({ normX: 0, normY: 0, gazeState: 'closed', timestamp: 1 }));

  assert.equal(tracker.allSamples.length, 1);
  const s = tracker.allSamples[0];
  assert.equal(s.gaze_state, 'closed');
  assert.equal(s.x, null, 'x must be null, not the centre of the screen');
  assert.equal(s.y, null);
  assert.equal(s.norm_x, null);
  assert.equal(tracker.droppedNoFace, 1);
});

test('an open-eyed frame is converted to screen pixels', () => {
  const { tracker } = newTracker();
  tracker.isInitialized = true;
  tracker.startTracking();

  tracker.handleGazeResult(gazeResult({ normX: 0.1, normY: -0.2, timestamp: 1 }));

  const s = tracker.allSamples[0];
  // viewport is 1000 x 500 in the harness
  assert.equal(s.x, (0.1 + 0.5) * 1000);
  assert.equal(s.y, (-0.2 + 0.5) * 500);
  assert.equal(s.gaze_state, 'open');
});

test('a gaze estimate saturated at the screen edge is flagged as clipped', () => {
  // WebEyeTrack clips normPog to [-0.5, 0.5]. A sample at the boundary is
  // censored -- the participant was looking further out -- not a fixation
  // on the edge of the screen.
  const { tracker } = newTracker();
  tracker.isInitialized = true;
  tracker.startTracking();

  tracker.handleGazeResult(gazeResult({ normX: -0.5, normY: 0.1, timestamp: 1 }));
  tracker.handleGazeResult(gazeResult({ normX: 0.5, normY: 0.1, timestamp: 2 }));
  tracker.handleGazeResult(gazeResult({ normX: 0.2, normY: -0.5, timestamp: 3 }));
  tracker.handleGazeResult(gazeResult({ normX: 0.2, normY: 0.1, timestamp: 4 }));

  assert.deepEqual(tracker.allSamples.map(s => s.clipped), [true, true, true, false]);
  assert.equal(tracker.clippedSamples, 3);
});

test('a no-face sample is never marked clipped', () => {
  const { tracker } = newTracker();
  tracker.isInitialized = true;
  tracker.startTracking();
  tracker.handleGazeResult(gazeResult({ normX: 0, normY: 0, gazeState: 'closed', timestamp: 1 }));
  assert.equal(tracker.allSamples[0].clipped, false);
});

test('repeated camera frames are recorded once', () => {
  const { tracker } = newTracker();
  tracker.isInitialized = true;
  tracker.startTracking();

  // The library samples the video on rAF (~60Hz) while the camera runs ~30fps,
  // so the same frame arrives twice and used to be stored twice.
  tracker.handleGazeResult(gazeResult({ timestamp: 4.85 }));
  tracker.handleGazeResult(gazeResult({ timestamp: 4.85 }));
  tracker.handleGazeResult(gazeResult({ timestamp: 4.90 }));

  assert.equal(tracker.allSamples.length, 2);
  assert.equal(tracker.droppedDuplicate, 1);
});

test('no samples are collected before startTracking()', () => {
  const { tracker } = newTracker();
  tracker.isInitialized = true;

  tracker.handleGazeResult(gazeResult({ timestamp: 1 }));

  assert.equal(tracker.allSamples.length, 0);
  // ... but the latest reading is still available, which is what the
  // calibration page needs. Requiring isTracking here is what made the
  // calibration RMSE permanently zero.
  assert.notEqual(tracker.getCurrentGaze(), null);
});

test('getCurrentGaze() returns null when no face is visible', () => {
  const { tracker } = newTracker();
  tracker.handleGazeResult(gazeResult({ gazeState: 'closed' }));
  assert.equal(tracker.getCurrentGaze(), null);
});

test('getCurrentGaze() returns null when the reading is stale', () => {
  const { tracker, dom } = newTracker();
  tracker.handleGazeResult(gazeResult());
  assert.notEqual(tracker.getCurrentGaze(), null);

  dom.advanceClock(tracker.maxGazeAgeMs + 1);
  assert.equal(tracker.getCurrentGaze(), null, 'a stale reading must not be reused');
});

test('a no-consent participant is saved as no_consent, not unknown', async () => {
  const { tracker, dom } = newTracker({ consent: null });

  const started = await tracker.init();
  assert.equal(started, false);
  assert.equal(tracker.initStatus, 'no_consent');

  // stopTracking() runs on the submit path even though tracking never started.
  await tracker.stopTracking();

  assert.equal(
    dom.elements.get('eyetrack_init_status').value,
    'no_consent',
    "must not fall back to the hidden input's 'unknown' default"
  );
  assert.equal(dom.elements.get('eyetrack_sample_count').value, '0');
  assert.equal(dom.elements.get('eyetrack_gaze_data').value, '[]');
});

test('server-side consent overrides a missing sessionStorage entry', async () => {
  // sessionStorage is lost on a new tab or browser restart. The participant
  // still consented; the server knows it.
  const { tracker } = newTracker({ consent: null, jsVars: { eyetrack_consent: true } });
  assert.equal(tracker.hasConsent(), true);

  const { tracker: denied } = newTracker({ consent: 'true', jsVars: { eyetrack_consent: false } });
  assert.equal(denied.hasConsent(), false, 'the server value is authoritative');
});

test('init() never falls back to fabricated samples', async () => {
  // No WebEyeTrackModule is ever set, so waitForWebEyeTrack times out.
  const { tracker, dom } = newTracker();
  tracker.readyTimeoutMs = 10;

  const started = await tracker.init.call(
    Object.assign(tracker, { waitForWebEyeTrack: async () => { throw new Error('bundle missing'); } })
  );

  assert.equal(started, false, 'init() must report failure, not pretend to work');
  assert.equal(tracker.initStatus, 'init_failed');
  assert.match(tracker.runtimeError, /bundle missing/);

  await tracker.stopTracking();
  assert.equal(dom.elements.get('eyetrack_gaze_data').value, '[]', 'no synthetic samples');
  assert.equal(dom.elements.get('eyetrack_init_status').value, 'init_failed');
});

test('waitForReady() resolves when the worker reports ready, and records the restore flag', async () => {
  const { tracker } = newTracker();
  tracker.proxy = { calibrate() {}, saveCalibration() {} };
  tracker.calibrationKey = 'k';
  tracker.readyTimeoutMs = 2000;

  const pending = tracker.waitForReady();
  // The worker's 'ready' message carries whether a stored calibration was found.
  tracker.proxy.onReady(true);
  await pending;   // must not hang

  assert.equal(tracker.calibrationRestored, true);
});

test('waitForReady() rejects when the worker reports an error', async () => {
  const { tracker } = newTracker();
  tracker.proxy = {};
  tracker.readyTimeoutMs = 2000;

  const pending = tracker.waitForReady();
  tracker._rejectReady(new Error('init: model 404'));

  await assert.rejects(pending, /model 404/);
});

test('a page that never restored a calibration records that fact', async () => {
  const { tracker, dom } = newTracker();
  tracker.calibrationRestored = false;
  await tracker.stopTracking();
  assert.equal(dom.elements.get('eyetrack_calibration_restored').value, '0');

  const { tracker: t2, dom: dom2 } = newTracker();
  t2.calibrationRestored = true;
  await t2.stopTracking();
  assert.equal(dom2.elements.get('eyetrack_calibration_restored').value, '1');
});

test('the viewport the gaze was measured on is recorded', async () => {
  // x and y are screen pixels. Without the screen they were measured on, they
  // cannot be compared across participants or turned into regions of interest.
  const { tracker, dom } = newTracker();
  tracker.isInitialized = true;
  tracker.startTracking();
  await tracker.stopTracking();

  assert.equal(dom.elements.get('eyetrack_viewport_width').value, '1000');
  assert.equal(dom.elements.get('eyetrack_viewport_height').value, '500');
  assert.equal(dom.elements.get('eyetrack_viewport_changed').value, '0');
});

test('a window resize during tracking is flagged', async () => {
  const { tracker, dom } = newTracker();
  tracker.isInitialized = true;
  tracker.startTracking();

  // Every sample after a resize is scaled to a different viewport.
  dom.win.innerWidth = 800;
  dom.win.innerHeight = 400;
  tracker._onResize();

  await tracker.stopTracking();

  assert.equal(dom.elements.get('eyetrack_viewport_changed').value, '1');
  assert.equal(dom.elements.get('eyetrack_viewport_width').value, '800');
});

test('regions of interest are captured at tracking start, in viewport pixels', async () => {
  const rois = [
    makeRoiElement('cell-cc', { x: 100, y: 200, w: 150, h: 60 }),
    makeRoiElement('cell-dd', { x: 300, y: 200, w: 150, h: 60 }),
  ];
  const dom = makeDom({ elementIds: FIELD_IDS, roiElements: rois });
  const SimpleGazeTracker = loadTracker(dom);
  const tracker = new SimpleGazeTracker({});
  tracker.isInitialized = true;
  tracker.startTracking();

  assert.equal(tracker.roiSnapshots.length, 1);
  const snap = tracker.roiSnapshots[0];
  assert.deepEqual(snap.items[0], { name: 'cell-cc', x: 100, y: 200, w: 150, h: 60 });
  assert.deepEqual(snap.items[1], { name: 'cell-dd', x: 300, y: 200, w: 150, h: 60 });

  await tracker.stopTracking();
  const written = JSON.parse(dom.elements.get('eyetrack_rois').value);
  assert.equal(written.length, 1, 'the snapshot reaches the form field');
  assert.equal(written[0].items.length, 2);
});

test('a scroll re-captures the ROIs once movement settles', async () => {
  // The rectangles are viewport-relative, so scrolling moves every region.
  // Mapping gaze recorded after the scroll onto the pre-scroll rectangles
  // would assign fixations to the wrong cells.
  const roi = makeRoiElement('cell-cc', { x: 100, y: 200, w: 150, h: 60 });
  const dom = makeDom({ elementIds: FIELD_IDS, roiElements: [roi] });
  const SimpleGazeTracker = loadTracker(dom);
  const tracker = new SimpleGazeTracker({});
  tracker.isInitialized = true;
  tracker.startTracking();

  roi.rect.y = 50; // the page scrolled; the cell is now higher in the viewport
  tracker._onScroll();
  await new Promise((r) => setTimeout(r, 350)); // past the 250ms settle timer

  assert.equal(tracker.roiSnapshots.length, 2);
  assert.equal(tracker.roiSnapshots[1].items[0].y, 50);
});

test('destroy() detaches the resize and scroll listeners', () => {
  // The calibration page's Recalibrate button destroys the tracker and builds
  // a new one on a page that stays alive; a listener left behind would keep
  // feeding a dead tracker, once per recalibration.
  const listeners = [];
  const dom = makeDom({ elementIds: FIELD_IDS });
  dom.win.addEventListener = (type, fn) => listeners.push([type, fn]);
  dom.win.removeEventListener = (type, fn) => {
    const i = listeners.findIndex(([t, f]) => t === type && f === fn);
    if (i !== -1) listeners.splice(i, 1);
  };
  const SimpleGazeTracker = loadTracker(dom);
  const tracker = new SimpleGazeTracker({});
  tracker.isInitialized = true;
  tracker.startTracking();
  assert.equal(listeners.length, 2, 'resize + scroll attached');

  tracker.destroy();
  assert.equal(listeners.length, 0, 'destroy() must remove both');
});

test('a page with no marked regions records no snapshots', () => {
  const { tracker } = newTracker();
  tracker.isInitialized = true;
  tracker.startTracking();
  assert.deepEqual(tracker.roiSnapshots, []);
});

test('the first uncaught page error is not overwritten by the tracker', async () => {
  const { tracker, dom } = newTracker();
  dom.elements.get('eyetrack_runtime_error').value = 'first error from the page';
  tracker.runtimeError = 'later tracker error';

  await tracker.stopTracking();

  assert.equal(dom.elements.get('eyetrack_runtime_error').value, 'first error from the page');
});
