/**
 * WebEyeTrack Loader
 *
 * Loads WebEyeTrack from the esm.sh CDN and exposes it globally for
 * non-module scripts. Pinned to @0.0.2 — newer versions may change the
 * model-loading internals; bump deliberately and re-test.
 *
 * The model files (`model.json` + weights) live in `_static/web/` and are
 * served at `/web/...` by the minimal ASGI wrapper in `asgi.py`. WebEyeTrack
 * 0.0.2 fetches them from a hardcoded `${origin}/web/model.json` inside a
 * Web Worker, so the path has to be served at the network layer — a
 * `window.fetch` patch in the main thread does not reach the worker.
 */

const WEBEYETRACK_VERSION = '0.0.2';
const WEBEYETRACK_CDN_URL = `https://esm.sh/webeyetrack@${WEBEYETRACK_VERSION}`;

let WebEyeTrackModule = null;
let loadingPromise = null;

export async function loadWebEyeTrack() {
  if (WebEyeTrackModule) return WebEyeTrackModule;
  if (loadingPromise) return loadingPromise;

  loadingPromise = (async () => {
    const module = await import(WEBEYETRACK_CDN_URL);

    let WebcamClient = module.WebcamClient;
    let WebEyeTrackProxy = module.WebEyeTrackProxy;
    if (!WebcamClient && module.default) {
      WebcamClient = module.default.WebcamClient;
      WebEyeTrackProxy = module.default.WebEyeTrackProxy;
    }

    WebEyeTrackModule = { WebcamClient, WebEyeTrackProxy };
    window.WebEyeTrack = WebEyeTrackModule;
    return WebEyeTrackModule;
  })();

  return loadingPromise;
}

export function isLoaded() {
  return WebEyeTrackModule !== null;
}

export function getModule() {
  return WebEyeTrackModule;
}
