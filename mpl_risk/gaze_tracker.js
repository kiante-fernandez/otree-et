// OTAI SECTION: header

/**
 * SimpleGazeTracker - Webcam-based gaze tracking using WebEyeTrack
 * Integrates with WebEyeTrack library for real gaze estimation
 * Falls back to mock data if WebEyeTrack fails to initialize
 */
class SimpleGazeTracker {
  constructor(config) {
    this.participantCode = config.participantCode;
    this.sessionCode = config.sessionCode;
    this.pageName = config.pageName;
    this.flushIntervalMs = config.flushIntervalMs || 1000;
    this.videoElementId = config.videoElementId || 'webcam-video';

    this.samples = [];
    this.allSamples = [];  // Keep all samples for form submission
    this.isTracking = false;
    this.webcamClient = null;
    this.webEyeTrackProxy = null;
    this.flushTimer = null;
    this.isInitialized = false;
    this.latestGazeResult = null;
    this.useMockData = false;
    this.totalSamplesSent = 0;
  }

  async init() {
    // Check if we have camera consent from previous page
    const hasConsent = sessionStorage.getItem('eyetrack_consent') === 'true';
    if (!hasConsent) {
      console.warn('GazeTracker: No camera consent found');
      this.updateStatus('no consent', false);
      return false;
    }

    try {
      // Wait for WebEyeTrack to be available
      await this.waitForWebEyeTrack();

      // Get video element reference
      const videoElement = document.getElementById(this.videoElementId);
      if (!videoElement) {
        throw new Error(`Video element "${this.videoElementId}" not found`);
      }

      // Initialize WebcamClient and WebEyeTrackProxy
      const { WebcamClient, WebEyeTrackProxy } = window.WebEyeTrack;

      this.webcamClient = new WebcamClient(this.videoElementId);
      this.webEyeTrackProxy = new WebEyeTrackProxy(this.webcamClient);

      // Set up gaze results callback
      this.webEyeTrackProxy.onGazeResults = (gazeResult) => {
        this.handleGazeResult(gazeResult);
      };

      this.isInitialized = true;
      this.useMockData = false;
      this.updateStatus('initialized', true);
      console.log('GazeTracker: WebEyeTrack initialized successfully');
      return true;

    } catch (error) {
      console.error('GazeTracker: WebEyeTrack initialization failed:', error);
      console.log('GazeTracker: Falling back to mock data');
      this.useMockData = true;
      this.isInitialized = true;
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

    // Convert normalized PoG [-0.5, 0.5] to screen pixels
    // normPog[0] is X, normPog[1] is Y
    // Origin is screen center, positive Y is down, positive X is right
    const normX = gazeResult.normPog[0];
    const normY = gazeResult.normPog[1];

    const screenX = (normX + 0.5) * window.innerWidth;
    const screenY = (normY + 0.5) * window.innerHeight;

    const sample = {
      x: screenX,
      y: screenY,
      norm_x: normX,
      norm_y: normY,
      gaze_state: gazeResult.gazeState,
      confidence: gazeResult.gazeState === 'open' ? 0.9 : 0.1,
      t_perf: performance.now(),
      timestamp: gazeResult.timestamp
    };

    this.samples.push(sample);
    this.allSamples.push(sample);  // Keep for form submission

    // Update visual gaze dot if present
    this.updateGazeDot(screenX, screenY);
  }

  collectMockGaze() {
    if (!this.isTracking || !this.useMockData) return;

    // Generate mock gaze data near screen center with some noise
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
      is_mock: true
    };

    this.samples.push(sample);
    this.allSamples.push(sample);  // Keep for form submission
    this.latestGazeResult = { normPog: [sample.norm_x, sample.norm_y], gazeState: 'open' };

    // Update visual gaze dot
    this.updateGazeDot(screenX, screenY);

    // Continue collecting
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

  updateSampleCountInput() {
    const countInput = document.getElementById('eyetrack_sample_count');
    if (countInput) {
      countInput.value = this.totalSamplesSent.toString();
    }
  }

  updateGazeDataInput() {
    const gazeDataInput = document.getElementById('eyetrack_gaze_data');
    if (gazeDataInput) {
      gazeDataInput.value = JSON.stringify(this.allSamples);
    }
  }

  startTracking() {
    if (this.isTracking || !this.isInitialized) return;

    this.isTracking = true;
    this.updateStatus('active', true);
    this.recordEvent('tracking_started');

    // If using mock data, start the mock collection loop
    if (this.useMockData) {
      this.collectMockGaze();
    }

    // Start periodic flush to server
    this.flushTimer = setInterval(() => this.flush(), this.flushIntervalMs);
  }

  async flush() {
    if (this.samples.length === 0) return;

    const samplesToSend = this.samples.slice();
    this.samples = [];

    try {
      const response = await fetch('/record_gaze/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          participant_code: this.participantCode,
          session_code: this.sessionCode,
          page: this.pageName,
          samples: samplesToSend
        })
      });

      if (!response.ok) {
        // Put samples back in buffer for retry
        this.samples = samplesToSend.concat(this.samples);
        console.warn('GazeTracker: Flush failed, will retry');
      } else {
        // Update total samples sent counter
        this.totalSamplesSent += samplesToSend.length;
        this.updateSampleCountInput();
      }
    } catch (error) {
      // Put samples back in buffer for retry
      this.samples = samplesToSend.concat(this.samples);
      console.error('GazeTracker: Flush error:', error);
    }
  }

  async recordEvent(eventType) {
    try {
      await fetch('/record_event/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          participant_code: this.participantCode,
          session_code: this.sessionCode,
          page: this.pageName,
          event_type: eventType
        })
      });
    } catch (error) {
      console.error('GazeTracker: Event recording failed:', error);
    }
  }

  async stopTracking() {
    if (!this.isTracking) return;

    this.isTracking = false;
    this.updateStatus('stopped', false);

    // Clear flush timer
    if (this.flushTimer) {
      clearInterval(this.flushTimer);
      this.flushTimer = null;
    }

    // Final flush
    await this.flush();
    await this.recordEvent('tracking_stopped');

    // Ensure final sample count and gaze data are set in form fields
    this.updateSampleCountInput();
    this.updateGazeDataInput();

    // Hide gaze dot
    const gazeDot = document.getElementById('gaze-dot');
    if (gazeDot) {
      gazeDot.style.display = 'none';
    }
  }

  // Get current gaze position (for calibration validation)
  getCurrentGaze() {
    if (this.latestGazeResult) {
      const normX = this.latestGazeResult.normPog[0];
      const normY = this.latestGazeResult.normPog[1];
      return {
        x: (normX + 0.5) * window.innerWidth,
        y: (normY + 0.5) * window.innerHeight,
        gazeState: this.latestGazeResult.gazeState
      };
    }
    return null;
  }
}

// OTAI SECTION: functions

// Export for use in templates
window.SimpleGazeTracker = SimpleGazeTracker;

// OTAI SECTION: footer
