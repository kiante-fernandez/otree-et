/**
 * SimpleGazeTracker — webcam gaze tracking for oTree, built on WebEyeTrack.
 *
 * Collects gaze samples in memory and writes them into the page's hidden form
 * fields on submit, so oTree saves them alongside the participant's choices:
 *
 *   eyetrack_sample_count  — number of samples recorded
 *   eyetrack_gaze_data     — JSON array of samples
 *   eyetrack_init_status   — 'ok' | 'no_consent' | 'init_failed' | 'unknown'
 *   eyetrack_runtime_error — why initialization failed, if it did
 *
 * Three properties this class is responsible for, each of which was previously
 * violated:
 *
 * 1. It never fabricates data. If the tracker cannot start, `init()` returns
 *    false and `eyetrack_init_status` says why. Earlier versions substituted
 *    synthetic samples around the screen centre, which are indistinguishable
 *    from a real participant staring at the middle of the screen.
 *
 * 2. `init()` resolves only once the model has actually loaded. WebEyeTrack
 *    fetches its model inside a Web Worker; a failure there used to surface as
 *    nothing at all, so the page reported 'ok' and recorded zero samples.
 *    We wait for the worker's `ready`, and treat `error` or a timeout as
 *    failure.
 *
 * 3. A frame in which no face was detected is not a gaze measurement.
 *    WebEyeTrack reports those as normPog [0, 0] with gazeState 'closed',
 *    which maps to the exact centre of the screen. Such samples are recorded
 *    with null coordinates rather than a fictitious centre fixation.
 */
class SimpleGazeTracker {
  constructor(config) {
    config = config || {};
    this.videoElementId = config.videoElementId || 'webcam-video';

    // Upstream defaults to `${origin}/web/model.json`, which oTree does not serve.
    this.modelUrl = config.modelUrl || '/static/web/model.json';

    // MediaPipe's runtime and face model. Upstream fetches both from third-party
    // CDNs in the participant's browser at run time; we serve our own copies so
    // that a study never depends on those hosts being up, and no participant's
    // IP address is disclosed to them. See tools/fetch_mediapipe_assets.sh.
    this.wasmPath = config.wasmPath || '/static/mediapipe/wasm';
    this.faceModelUrl = config.faceModelUrl || '/static/mediapipe/face_landmarker.task';

    // When set, a model personalised on an earlier page is restored from
    // IndexedDB. Model adaptation lives in the Web Worker and dies with it, so
    // without this a calibration cannot outlive the page it was performed on.
    this.calibrationKey = config.calibrationKey || null;

    // WebEyeTrack treats every click anywhere on the page as a gaze target and
    // retrains on it. On a task page that means the participant's own answers
    // drag the model toward whatever control they clicked. Off by default;
    // the calibration routine calls `calibrate()` explicitly instead.
    this.adaptOnClick = config.adaptOnClick === true;

    // Size of the calibration support set inside the worker.
    this.maxPoints = config.maxPoints;

    // Cold start is ~5s (two model fetches). Allow generous headroom before
    // declaring the model dead.
    this.readyTimeoutMs = config.readyTimeoutMs || 20000;

    // A gaze reading older than this is stale — the participant may have
    // blinked or looked away since.
    this.maxGazeAgeMs = config.maxGazeAgeMs || 400;

    this.allSamples = [];
    this.isTracking = false;
    this.isInitialized = false;
    this.webcamClient = null;
    this.proxy = null;
    this.initStatus = 'unknown';
    this.runtimeError = '';

    // Whether this page is measuring gaze with the model the participant
    // calibrated, or with the uncalibrated base model. Recorded with the data:
    // it is not something you want to discover during analysis.
    this.calibrationRestored = false;

    this.latestGaze = null;
    this.latestGazeAt = 0;
    this.lastFrameTimestamp = null;

    this.droppedNoFace = 0;
    this.droppedDuplicate = 0;

    // Sample coordinates are screen pixels, so they mean nothing without the
    // size of the screen they were measured on. Record it. A resize mid-task
    // silently rescales every subsequent sample, so record that too.
    this.viewportWidth = 0;
    this.viewportHeight = 0;
    this.viewportChanged = false;

    this._rejectReady = null;
    this._onResize = null;
  }

  hasConsent() {
    // The server-side value is authoritative; sessionStorage is a fallback for
    // pages that do not pass it. sessionStorage is lost on a new tab or a
    // browser restart, so relying on it alone silently disables tracking for a
    // participant who did consent.
    if (typeof js_vars !== 'undefined' && js_vars && 'eyetrack_consent' in js_vars) {
      return js_vars.eyetrack_consent === true;
    }
    return sessionStorage.getItem('eyetrack_consent') === 'true';
  }

  async init() {
    if (!this.hasConsent()) {
      console.warn('GazeTracker: no camera consent');
      this.initStatus = 'no_consent';
      this.updateStatus('no consent', false);
      return false;
    }

    try {
      await this.waitForWebEyeTrack();

      if (!document.getElementById(this.videoElementId)) {
        throw new Error(`Video element "${this.videoElementId}" not found`);
      }

      const { WebcamClient, WebEyeTrackProxy } = window.WebEyeTrackModule;
      this.webcamClient = new WebcamClient(this.videoElementId);
      this.proxy = new WebEyeTrackProxy(this.webcamClient, {
        modelUrl: this.modelUrl,
        wasmPath: this.wasmPath,
        faceModelUrl: this.faceModelUrl,
        calibrationKey: this.calibrationKey || undefined,
        adaptOnClick: this.adaptOnClick,
        maxPoints: this.maxPoints,
      });

      this.proxy.onGazeResults = (gazeResult) => this.handleGazeResult(gazeResult);
      this.proxy.onError = (phase, message) => {
        const err = new Error(`${phase}: ${message}`);
        if (this._rejectReady) this._rejectReady(err);
        else console.error('GazeTracker:', err.message);
      };

      await this.waitForReady();

      this.isInitialized = true;
      this.initStatus = 'ok';
      this.updateStatus('initialized', true);
      return true;

    } catch (error) {
      // No mock fallback. A research instrument that silently substitutes
      // fabricated measurements is worse than one that plainly stops.
      console.error('GazeTracker: initialization failed:', error);
      this.initStatus = 'init_failed';
      this.runtimeError = String((error && error.message) || error).slice(0, 1000);
      this.updateStatus('unavailable', false);
      return false;
    }
  }

  // `window.WebEyeTrackModule` is set by webeyetrack-loader.js once the bundle
  // has loaded AND its exports have been checked. Do not poll for upstream's
  // `window.WebEyeTrack`: the UMD bundle sets that to a class the moment the
  // script runs, so polling it races the export check.
  async waitForWebEyeTrack(timeoutMs = 15000) {
    const startTime = Date.now();
    while (!window.WebEyeTrackModule) {
      if (Date.now() - startTime > timeoutMs) {
        throw new Error('WebEyeTrack library failed to load');
      }
      await new Promise(resolve => setTimeout(resolve, 100));
    }
  }

  // The worker emits `ready` only after its model has loaded, and `ready` is
  // what starts the camera. No `ready` means no frames will ever arrive.
  waitForReady() {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error(`eye-tracking model did not load within ${this.readyTimeoutMs}ms`)),
        this.readyTimeoutMs
      );
      const settle = (fn) => (arg) => {
        clearTimeout(timer);
        this._rejectReady = null;
        fn(arg);
      };

      this._rejectReady = settle(reject);

      this.proxy.onReady = settle((calibrationRestored) => {
        this.calibrationRestored = calibrationRestored === true;
        if (this.calibrationKey && !this.calibrationRestored) {
          console.warn(
            `GazeTracker: no stored calibration under "${this.calibrationKey}"; ` +
            'gaze on this page comes from the uncalibrated base model.'
          );
        }
        resolve();
      });
    });
  }

  handleGazeResult(gazeResult) {
    // Record the latest reading even when not collecting samples: the
    // calibration page needs it, and it must not depend on `isTracking`.
    this.latestGaze = gazeResult;
    this.latestGazeAt = performance.now();

    if (!this.isTracking) return;

    // One gaze result per unique camera frame. The library samples the video on
    // requestAnimationFrame (~60Hz) while the camera runs at ~30fps, so roughly
    // a third of results re-process the previous frame. Storing them inflates
    // the sample count and any dwell-time measure computed from it.
    if (gazeResult.timestamp === this.lastFrameTimestamp) {
      this.droppedDuplicate++;
      return;
    }
    this.lastFrameTimestamp = gazeResult.timestamp;

    const seen = gazeResult.gazeState === 'open';
    if (!seen) this.droppedNoFace++;

    // `frame_time` is the camera's clock, in SECONDS since the stream started.
    // `t_perf` is milliseconds since page load. They are different clocks; use
    // t_perf for anything that needs a monotonic timeline.
    const normX = seen ? gazeResult.normPog[0] : null;
    const normY = seen ? gazeResult.normPog[1] : null;

    this.allSamples.push({
      x: seen ? (normX + 0.5) * window.innerWidth : null,
      y: seen ? (normY + 0.5) * window.innerHeight : null,
      norm_x: normX,
      norm_y: normY,
      gaze_state: gazeResult.gazeState,
      t_perf: performance.now(),
      frame_time: gazeResult.timestamp,
    });

    if (seen) {
      this.updateGazeDot((normX + 0.5) * window.innerWidth, (normY + 0.5) * window.innerHeight);
    }
  }

  /**
   * The current gaze point in screen pixels, or null when there is no usable
   * reading — no face detected, eyes closed, or the last reading is stale.
   * Callers must treat null as "ask the participant to reposition", never as
   * a look at the centre of the screen.
   */
  getCurrentGaze() {
    if (!this.latestGaze) return null;
    if (this.latestGaze.gazeState !== 'open') return null;
    if (performance.now() - this.latestGazeAt > this.maxGazeAgeMs) return null;

    const [normX, normY] = this.latestGaze.normPog;
    return {
      x: (normX + 0.5) * window.innerWidth,
      y: (normY + 0.5) * window.innerHeight,
      normX,
      normY,
      gazeState: this.latestGaze.gazeState,
    };
  }

  /** Adapt the model to a target the participant is looking at right now. */
  calibrate(normX, normY) {
    if (!this.proxy) return Promise.resolve(false);
    return new Promise((resolve) => {
      this.proxy.onCalibrationPoint = (adapted) => resolve(adapted);
      this.proxy.calibrate(normX, normY);
    });
  }

  /** Persist the personalised model so later pages can restore it. */
  saveCalibration(calibrationKey) {
    if (!this.proxy) return Promise.reject(new Error('tracker not initialized'));
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('saveCalibration timed out')), 10000);
      this.proxy.onCalibrationSaved = () => { clearTimeout(timer); resolve(calibrationKey); };
      this.proxy.onError = (phase, message) => { clearTimeout(timer); reject(new Error(`${phase}: ${message}`)); };
      this.proxy.saveCalibration(calibrationKey);
    });
  }

  updateGazeDot(x, y) {
    const gazeDot = document.getElementById('gaze-dot');
    if (gazeDot) {
      gazeDot.style.left = x + 'px';
      gazeDot.style.top = y + 'px';
      gazeDot.style.display = 'block';
    }
  }

  updateStatus(text, isActive) {
    const statusEl = document.getElementById('tracking-status');
    if (statusEl) {
      statusEl.textContent = 'Eye tracking: ' + text;
      statusEl.className = isActive ? 'status-active' : 'status-inactive';
    }
  }

  writeFormFields() {
    const set = (id, value) => {
      const el = document.getElementById(id);
      if (el) el.value = value;
    };
    set('eyetrack_sample_count', this.allSamples.length.toString());
    set('eyetrack_gaze_data', JSON.stringify(this.allSamples));
    set('eyetrack_init_status', this.initStatus);
    set('eyetrack_calibration_restored', this.calibrationRestored ? '1' : '0');
    set('eyetrack_viewport_width', this.viewportWidth.toString());
    set('eyetrack_viewport_height', this.viewportHeight.toString());
    set('eyetrack_viewport_changed', this.viewportChanged ? '1' : '0');

    // The page records the first uncaught error there. Do not overwrite it:
    // whatever failed first is the more informative diagnosis.
    if (this.runtimeError) {
      const el = document.getElementById('eyetrack_runtime_error');
      if (el && !el.value) el.value = this.runtimeError;
    }
  }

  startTracking() {
    if (this.isTracking || !this.isInitialized) return;
    this.isTracking = true;

    this.viewportWidth = window.innerWidth;
    this.viewportHeight = window.innerHeight;
    this._onResize = () => {
      this.viewportChanged = true;
      this.viewportWidth = window.innerWidth;
      this.viewportHeight = window.innerHeight;
    };
    window.addEventListener('resize', this._onResize);

    this.updateStatus('active', true);
  }

  /**
   * Stop collecting and write the form fields. This runs on every submit path,
   * including one where tracking never started: otherwise a no-consent or
   * failed-init participant is saved as 'unknown', which is documented to mean
   * something else entirely.
   */
  async stopTracking() {
    this.isTracking = false;
    if (this.isInitialized) this.updateStatus('stopped', false);

    if (this._onResize) {
      window.removeEventListener('resize', this._onResize);
      this._onResize = null;
    }

    this.writeFormFields();

    const gazeDot = document.getElementById('gaze-dot');
    if (gazeDot) gazeDot.style.display = 'none';
  }

  /** Release the camera, the worker, and the library's click listener. */
  destroy() {
    try {
      if (this.proxy) this.proxy.destroy();
    } catch (err) {
      console.warn('GazeTracker: proxy teardown failed', err);
    }
    try {
      if (this.webcamClient && typeof this.webcamClient.stopWebcam === 'function') {
        this.webcamClient.stopWebcam();
      }
    } catch (err) {
      console.warn('GazeTracker: webcam teardown failed', err);
    }
    this.proxy = null;
    this.webcamClient = null;
    this.isInitialized = false;
    this.isTracking = false;
  }
}

window.SimpleGazeTracker = SimpleGazeTracker;
