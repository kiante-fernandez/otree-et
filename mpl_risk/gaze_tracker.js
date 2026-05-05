/**
 * SimpleGazeTracker - Webcam-based gaze tracking using WebEyeTrack
 *
 * Collects gaze samples in memory and writes them into the page's hidden
 * form fields on submit, so the data is saved by oTree alongside the
 * participant's choices:
 *
 *   eyetrack_sample_count  — number of samples recorded
 *   eyetrack_gaze_data     — JSON array of samples
 *   eyetrack_init_status   — 'ok' | 'no_consent' | 'init_failed' | 'unknown'
 *
 * If WebEyeTrack fails to initialize, mock samples are generated so the rest
 * of the task remains usable for debugging. Mock samples are flagged via
 * `is_mock: true` AND the participant-level `eyetrack_init_status` is set to
 * 'init_failed' — filter on either when analyzing data.
 */
class SimpleGazeTracker {
  constructor(config) {
    config = config || {};
    this.videoElementId = config.videoElementId || 'webcam-video';

    this.allSamples = [];
    this.isTracking = false;
    this.webcamClient = null;
    this.webEyeTrackProxy = null;
    this.isInitialized = false;
    this.latestGazeResult = null;
    this.useMockData = false;
    this.initStatus = 'unknown';
  }

  async init() {
    const hasConsent = sessionStorage.getItem('eyetrack_consent') === 'true';
    if (!hasConsent) {
      console.warn('GazeTracker: No camera consent found');
      this.initStatus = 'no_consent';
      this.updateStatus('no consent', false);
      return false;
    }

    try {
      await this.waitForWebEyeTrack();

      if (!document.getElementById(this.videoElementId)) {
        throw new Error(`Video element "${this.videoElementId}" not found`);
      }

      const { WebcamClient, WebEyeTrackProxy } = window.WebEyeTrack;
      this.webcamClient = new WebcamClient(this.videoElementId);
      this.webEyeTrackProxy = new WebEyeTrackProxy(this.webcamClient);
      this.webEyeTrackProxy.onGazeResults = (gazeResult) => {
        this.handleGazeResult(gazeResult);
      };

      this.isInitialized = true;
      this.useMockData = false;
      this.initStatus = 'ok';
      this.updateStatus('initialized', true);
      return true;

    } catch (error) {
      console.error('GazeTracker: WebEyeTrack initialization failed:', error);
      console.warn('GazeTracker: Falling back to mock data — eyetrack_init_status will be "init_failed"');
      this.useMockData = true;
      this.isInitialized = true;
      this.initStatus = 'init_failed';
      this.updateStatus('mock mode', true);
      return true;
    }
  }

  async waitForWebEyeTrack(timeoutMs = 15000) {
    const startTime = Date.now();
    while (!window.WebEyeTrack) {
      if (Date.now() - startTime > timeoutMs) {
        throw new Error('WebEyeTrack library failed to load');
      }
      await new Promise(resolve => setTimeout(resolve, 100));
    }
  }

  handleGazeResult(gazeResult) {
    if (!this.isTracking) return;

    this.latestGazeResult = gazeResult;

    const normX = gazeResult.normPog[0];
    const normY = gazeResult.normPog[1];
    const screenX = (normX + 0.5) * window.innerWidth;
    const screenY = (normY + 0.5) * window.innerHeight;

    // WebEyeTrack 0.0.2 does not expose a real per-sample confidence,
    // so we record a placeholder driven by gazeState. Treat as ordinal,
    // not absolute.
    this.allSamples.push({
      x: screenX,
      y: screenY,
      norm_x: normX,
      norm_y: normY,
      gaze_state: gazeResult.gazeState,
      confidence: gazeResult.gazeState === 'open' ? 0.9 : 0.1,
      t_perf: performance.now(),
      timestamp: gazeResult.timestamp,
    });

    this.updateGazeDot(screenX, screenY);
  }

  collectMockGaze() {
    if (!this.isTracking || !this.useMockData) return;

    const centerX = window.innerWidth / 2;
    const centerY = window.innerHeight / 2;
    const noise = 50;
    const screenX = centerX + (Math.random() - 0.5) * noise * 2;
    const screenY = centerY + (Math.random() - 0.5) * noise * 2;

    const sample = {
      x: screenX,
      y: screenY,
      norm_x: (screenX / window.innerWidth) - 0.5,
      norm_y: (screenY / window.innerHeight) - 0.5,
      gaze_state: 'open',
      confidence: 0.8 + Math.random() * 0.2,
      t_perf: performance.now(),
      timestamp: performance.now(),
      is_mock: true,
    };

    this.allSamples.push(sample);
    this.latestGazeResult = { normPog: [sample.norm_x, sample.norm_y], gazeState: 'open' };
    this.updateGazeDot(screenX, screenY);

    requestAnimationFrame(() => this.collectMockGaze());
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
    const countInput = document.getElementById('eyetrack_sample_count');
    if (countInput) countInput.value = this.allSamples.length.toString();

    const gazeDataInput = document.getElementById('eyetrack_gaze_data');
    if (gazeDataInput) gazeDataInput.value = JSON.stringify(this.allSamples);

    const statusInput = document.getElementById('eyetrack_init_status');
    if (statusInput) statusInput.value = this.initStatus;
  }

  startTracking() {
    if (this.isTracking || !this.isInitialized) return;
    this.isTracking = true;
    this.updateStatus('active', true);
    if (this.useMockData) {
      this.collectMockGaze();
    }
  }

  async stopTracking() {
    if (!this.isTracking) return;
    this.isTracking = false;
    this.updateStatus('stopped', false);

    this.writeFormFields();

    const gazeDot = document.getElementById('gaze-dot');
    if (gazeDot) gazeDot.style.display = 'none';
  }

  // Get current gaze position (for calibration validation).
  getCurrentGaze() {
    if (this.latestGazeResult) {
      const normX = this.latestGazeResult.normPog[0];
      const normY = this.latestGazeResult.normPog[1];
      return {
        x: (normX + 0.5) * window.innerWidth,
        y: (normY + 0.5) * window.innerHeight,
        gazeState: this.latestGazeResult.gazeState,
      };
    }
    return null;
  }
}

window.SimpleGazeTracker = SimpleGazeTracker;
