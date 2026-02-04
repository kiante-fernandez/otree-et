/**
 * WebEyeTrack Loader
 * Loads WebEyeTrack from esm.sh CDN and exposes it globally for non-module scripts.
 */

let WebEyeTrackModule = null;
let loadingPromise = null;

export async function loadWebEyeTrack() {
  // Return cached module if already loaded
  if (WebEyeTrackModule) {
    return WebEyeTrackModule;
  }

  // Return existing promise if already loading
  if (loadingPromise) {
    return loadingPromise;
  }

  loadingPromise = (async () => {
    try {
      console.log('WebEyeTrack: Loading from CDN...');

      const module = await import('https://esm.sh/webeyetrack');

      // Debug: log what we got
      console.log('WebEyeTrack: Module keys:', Object.keys(module));

      // Handle different export structures
      let WebcamClient = module.WebcamClient;
      let WebEyeTrackProxy = module.WebEyeTrackProxy;

      // Check if they're wrapped in .default
      if (WebcamClient && WebcamClient.default) {
        WebcamClient = WebcamClient.default;
      }
      if (WebEyeTrackProxy && WebEyeTrackProxy.default) {
        WebEyeTrackProxy = WebEyeTrackProxy.default;
      }

      // Check if module itself has a default with the classes
      if (!WebcamClient && module.default) {
        WebcamClient = module.default.WebcamClient;
        WebEyeTrackProxy = module.default.WebEyeTrackProxy;
      }

      console.log('WebEyeTrack: WebcamClient type:', typeof WebcamClient);
      console.log('WebEyeTrack: WebEyeTrackProxy type:', typeof WebEyeTrackProxy);

      WebEyeTrackModule = { WebcamClient, WebEyeTrackProxy };

      // Expose globally for non-module scripts (like gaze_tracker.js)
      window.WebEyeTrack = WebEyeTrackModule;

      console.log('WebEyeTrack: Loaded successfully');
      return WebEyeTrackModule;

    } catch (error) {
      console.error('WebEyeTrack: Failed to load from CDN:', error);
      loadingPromise = null;
      throw error;
    }
  })();

  return loadingPromise;
}

// Check if WebEyeTrack is loaded
export function isLoaded() {
  return WebEyeTrackModule !== null;
}

// Get the module (null if not loaded)
export function getModule() {
  return WebEyeTrackModule;
}
