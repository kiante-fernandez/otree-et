/**
 * Pure geometry for the calibration routine. No DOM, no library, no globals —
 * so it can be unit tested without a browser.
 *
 * Wrapped in an IIFE: oTree includes each `include_sibling` script into the
 * same global scope, so a bare `function pctToNorm` here would collide with
 * calibration.js's `const { pctToNorm } = ...` and throw a SyntaxError that
 * takes the whole page down.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.calibrationMath = api;
})(typeof window !== 'undefined' ? window : null, function () {

  /** Percentage of the viewport -> WebEyeTrack's normalized coordinates. */
  function pctToNorm(pct) {
    return (pct / 100) - 0.5;
  }

  /** Screen-pixel offset of a gaze point from the target it should have hit. */
  function gazeError(gaze, targetPct, viewportWidth, viewportHeight) {
    return {
      dx: gaze.x - (targetPct.x / 100) * viewportWidth,
      dy: gaze.y - (targetPct.y / 100) * viewportHeight,
    };
  }

  /**
   * Root-mean-square distance, in pixels, over a list of {dx, dy} errors.
   * Zero errors means "not measured", which callers render as n/a rather than
   * as a perfect score.
   */
  function computeRMSE(errors) {
    if (!errors.length) return 0;
    const sumSquares = errors.reduce((acc, e) => acc + e.dx * e.dx + e.dy * e.dy, 0);
    return Math.sqrt(sumSquares / errors.length);
  }

  return { pctToNorm, gazeError, computeRMSE };
});
