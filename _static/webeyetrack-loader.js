/**
 * WebEyeTrack Loader
 *
 * Loads the vendored WebEyeTrack bundle from this project's own static files.
 * Nothing is fetched from a third-party CDN, so a participant's browser cannot
 * be stranded by an outage, and no request leaks to an external host.
 *
 * See `_static/webeyetrack/VENDOR.md` for provenance and the one local change
 * (the model URL), and `tools/vendor_webeyetrack.sh` to regenerate the bundle.
 *
 * The bundle is a UMD build: loading it copies its exports (`WebcamClient`,
 * `WebEyeTrackProxy`, `WebEyeTrack`, ...) straight onto `window`. Note that
 * `window.WebEyeTrack` is upstream's *class*, not this module's return value —
 * hence the distinct `window.WebEyeTrackModule` below, which callers should use.
 */

const DEFAULT_SRC = '/static/webeyetrack/webeyetrack.js';

let loadedModule = null;
let pending = null;

function injectScript(src) {
  return new Promise((resolve, reject) => {
    const el = document.createElement('script');
    el.src = src;
    el.async = true;
    el.dataset.webeyetrack = '';
    el.onload = () => resolve();
    el.onerror = () => {
      el.remove(); // let a retry re-add it
      reject(new Error(`Failed to load the WebEyeTrack bundle from ${src}`));
    };
    document.head.appendChild(el);
  });
}

export async function loadWebEyeTrack(src = DEFAULT_SRC) {
  if (loadedModule) return loadedModule;
  if (pending) return pending;

  pending = (async () => {
    await injectScript(src);

    const { WebcamClient, WebEyeTrackProxy } = window;
    if (typeof WebcamClient !== 'function' || typeof WebEyeTrackProxy !== 'function') {
      throw new Error(
        'The WebEyeTrack bundle loaded but did not expose WebcamClient / WebEyeTrackProxy. ' +
        'Re-run tools/vendor_webeyetrack.sh.'
      );
    }

    loadedModule = { WebcamClient, WebEyeTrackProxy };
    window.WebEyeTrackModule = loadedModule;
    return loadedModule;
  })();

  try {
    return await pending;
  } catch (err) {
    // A failed load must not be memoized: callers on a later page, or a retry
    // after a transient failure, would otherwise receive the same rejection
    // forever with no way to recover short of a full reload.
    pending = null;
    throw err;
  }
}
