/**
 * Minimal browser stubs so mpl_risk/gaze_tracker.js can be exercised under
 * plain `node --test`. No jsdom, no npm dependencies.
 *
 * Only what SimpleGazeTracker actually touches is stubbed: a few elements
 * looked up by id, sessionStorage, performance.now, and window dimensions.
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

/** A stand-in for an <input> or <div> that only ever has .value / .style / .className. */
function makeElement(id) {
  return { id, value: '', textContent: '', className: '', style: {} };
}

export function makeDom({ consent = 'true', jsVars = undefined, elementIds = [] } = {}) {
  const elements = new Map();
  for (const id of elementIds) elements.set(id, makeElement(id));

  let now = 1000;

  const win = {
    innerWidth: 1000,
    innerHeight: 500,
    addEventListener() {},
    removeEventListener() {},
  };

  const doc = {
    getElementById: (id) => elements.get(id) || null,
    addEventListener() {},
  };

  const sessionStorage = {
    _v: consent === null ? {} : { eyetrack_consent: consent },
    getItem(k) { return k in this._v ? this._v[k] : null; },
    setItem(k, v) { this._v[k] = v; },
  };

  return {
    elements,
    win,
    doc,
    sessionStorage,
    performance: { now: () => now },
    advanceClock: (ms) => { now += ms; },
    jsVars,
  };
}

/**
 * Load gaze_tracker.js against a stub DOM and return its SimpleGazeTracker.
 * The file assigns to `window.SimpleGazeTracker`; a `class` declaration inside
 * eval() is block-scoped, so we rewrite that assignment to reach our sandbox.
 */
export function loadTracker(dom) {
  const src = readFileSync(join(ROOT, 'mpl_risk', 'gaze_tracker.js'), 'utf8');

  globalThis.window = dom.win;
  globalThis.document = dom.doc;
  globalThis.sessionStorage = dom.sessionStorage;
  globalThis.performance = dom.performance;
  if (dom.jsVars === undefined) {
    delete globalThis.js_vars;
  } else {
    globalThis.js_vars = dom.jsVars;
  }

  const holder = {};
  // eslint-disable-next-line no-eval
  (0, eval)(src.replace(
    'window.SimpleGazeTracker = SimpleGazeTracker;',
    'globalThis.__SimpleGazeTracker = SimpleGazeTracker;'
  ));
  holder.SimpleGazeTracker = globalThis.__SimpleGazeTracker;
  return holder.SimpleGazeTracker;
}

/** A gaze result shaped exactly as WebEyeTrack emits one. */
export function gazeResult({ normX = 0.1, normY = -0.2, gazeState = 'open', timestamp = 1.0 } = {}) {
  return { normPog: [normX, normY], gazeState, timestamp };
}
