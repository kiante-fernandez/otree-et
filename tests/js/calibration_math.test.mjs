/**
 * Unit tests for the calibration geometry.
 *
 *   node --test tests/js
 */

import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const require = createRequire(import.meta.url);
const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const { pctToNorm, gazeError, computeRMSE, rmseFraction } = require(join(ROOT, 'mpl_risk', 'calibration_math.js'));

test('pctToNorm maps the viewport onto WebEyeTrack normalized coordinates', () => {
  assert.equal(pctToNorm(0), -0.5);
  assert.equal(pctToNorm(50), 0);
  assert.equal(pctToNorm(100), 0.5);
  // The 3x3 grid's outer points
  assert.ok(Math.abs(pctToNorm(10) - -0.4) < 1e-12);
  assert.ok(Math.abs(pctToNorm(90) - 0.4) < 1e-12);
});

test('gazeError measures the offset from the target in pixels', () => {
  const e = gazeError({ x: 110, y: 40 }, { x: 10, y: 10 }, 1000, 500);
  assert.equal(e.dx, 110 - 100);
  assert.equal(e.dy, 40 - 50);
});

test('computeRMSE is the root mean square distance', () => {
  // Two points, each 3-4-5 away from target.
  const rmse = computeRMSE([{ dx: 3, dy: 4 }, { dx: 3, dy: 4 }]);
  assert.equal(rmse, 5);
});

test('computeRMSE combines unequal errors correctly', () => {
  // distances 0 and 10 -> sqrt((0 + 100)/2)
  const rmse = computeRMSE([{ dx: 0, dy: 0 }, { dx: 6, dy: 8 }]);
  assert.ok(Math.abs(rmse - Math.sqrt(50)) < 1e-12);
});

test('computeRMSE with no measurements returns 0, which the page renders as n/a', () => {
  assert.equal(computeRMSE([]), 0);
});

test('rmseFraction expresses the error relative to the screen', () => {
  // A 265 px error on a 1512x747 window is a much bigger deal than on a 3440x1440 one.
  const laptop = rmseFraction(265, 1512, 747);
  const monitor = rmseFraction(265, 3440, 1440);
  assert.ok(Math.abs(laptop - 265 / Math.hypot(1512, 747)) < 1e-12);
  assert.ok(laptop > monitor, 'the same pixel error is worse on a smaller screen');
  assert.ok(laptop > 0.15 && laptop < 0.16, `expected ~15.7%, got ${laptop}`);
});

test('rmseFraction is 0 when the viewport is unknown, rather than dividing by zero', () => {
  assert.equal(rmseFraction(265, 0, 0), 0);
});

test('a perfect calibration has zero error and is distinguishable from no measurement', () => {
  // Both give 0. The page must therefore never treat 0 as "perfect": it renders
  // n/a. This test pins that ambiguity so it stays deliberate.
  assert.equal(computeRMSE([{ dx: 0, dy: 0 }]), 0);
  assert.equal(computeRMSE([]), 0);
});
