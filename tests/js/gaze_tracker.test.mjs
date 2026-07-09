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
import { makeDom, loadTracker, gazeResult } from './harness.mjs';

const FIELD_IDS = [
  'eyetrack_sample_count',
  'eyetrack_gaze_data',
  'eyetrack_init_status',
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

test('the first uncaught page error is not overwritten by the tracker', async () => {
  const { tracker, dom } = newTracker();
  dom.elements.get('eyetrack_runtime_error').value = 'first error from the page';
  tracker.runtimeError = 'later tracker error';

  await tracker.stopTracking();

  assert.equal(dom.elements.get('eyetrack_runtime_error').value, 'first error from the page');
});
