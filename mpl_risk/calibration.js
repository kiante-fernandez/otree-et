// OTAI SECTION: header

const calibrationPoints = js_vars.calibration_points;
let currentPointIndex = 0;
let calibrationData = [];
let gazeTracker = null;

// OTAI SECTION: functions

async function waitForWebEyeTrack(timeoutMs = 15000) {
  const startTime = Date.now();
  while (!window.WebEyeTrack) {
    if (Date.now() - startTime > timeoutMs) {
      throw new Error('WebEyeTrack failed to load');
    }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
}

async function initializeGazeTracker() {
  // Wait for WebEyeTrack to load from CDN
  await waitForWebEyeTrack();

  // Create tracker for calibration (doesn't send to server, just for local use)
  gazeTracker = new SimpleGazeTracker({
    participantCode: 'calibration',
    sessionCode: 'calibration',
    pageName: 'Calibration',
    videoElementId: 'webcam-video',
    flushIntervalMs: 60000 // Don't flush during calibration
  });

  const initialized = await gazeTracker.init();
  if (!initialized) {
    console.warn('GazeTracker initialization failed, calibration will proceed without gaze capture');
  }
  return initialized;
}

function calculateCalibrationRMSE(data) {
  // Calculate root mean square error between target and gaze positions
  if (data.length === 0) return 0;

  let sumSquaredError = 0;
  let validSamples = 0;

  for (const point of data) {
    if (point.gaze_x !== undefined && point.gaze_y !== undefined) {
      // Convert target percentage to pixels
      const targetX = (point.target_x / 100) * window.innerWidth;
      const targetY = (point.target_y / 100) * window.innerHeight;
      const dx = point.gaze_x - targetX;
      const dy = point.gaze_y - targetY;
      sumSquaredError += dx * dx + dy * dy;
      validSamples++;
    }
  }

  return validSamples > 0 ? Math.sqrt(sumSquaredError / validSamples) : 0;
}

function finishCalibration() {
  const overlay = docQuerySelectorStrict('#calibration-overlay');
  const completion = docQuerySelectorStrict('#calibration-complete');
  overlay.style.display = 'none';
  completion.classList.remove('hidden');

  // Store calibration data including gaze samples
  sessionStorage.setItem('calibration_data', JSON.stringify(calibrationData));

  // Calculate and store calibration quality metrics
  const rmse = calculateCalibrationRMSE(calibrationData);
  sessionStorage.setItem('calibration_rmse', rmse.toString());
  console.log('Calibration RMSE:', rmse, 'pixels');

  // Set hidden form field for oTree to save
  const rmseInput = document.getElementById('eyetrack_calibration_rmse');
  if (rmseInput) {
    rmseInput.value = rmse.toString();
  }
}

function handlePointClick(event) {
  const target = event.currentTarget;
  const pointData = calibrationPoints[currentPointIndex];

  // Capture current gaze position at click time
  const currentGaze = gazeTracker ? gazeTracker.getCurrentGaze() : null;

  calibrationData.push({
    target_x: pointData.x,
    target_y: pointData.y,
    gaze_x: currentGaze ? currentGaze.x : undefined,
    gaze_y: currentGaze ? currentGaze.y : undefined,
    gaze_state: currentGaze ? currentGaze.gazeState : undefined,
    t: performance.now()
  });

  target.classList.add('clicked');
  currentPointIndex++;

  if (currentPointIndex < calibrationPoints.length) {
    setTimeout(() => showCalibrationPoint(currentPointIndex), js_vars.delay_ms);
  } else {
    setTimeout(finishCalibration, js_vars.delay_ms);
  }
}

function recalibrate() {
  docQuerySelectorStrict('#calibration-complete').classList.add('hidden');
  const allPoints = docQuerySelectorAllStrict('.calibration-point');
  for (let p of allPoints) {
    p.classList.remove('clicked');
  }
  startCalibration();
}

function showCalibrationPoint(index) {
  const allPoints = docQuerySelectorAllStrict('.calibration-point');
  allPoints.forEach(p => p.classList.remove('active'));
  const point = allPoints[index];
  point.classList.add('active');
}

async function startCalibration() {
  // Initialize gaze tracker if not already done
  if (!gazeTracker) {
    try {
      await initializeGazeTracker();
    } catch (error) {
      console.warn('Could not initialize gaze tracker:', error);
    }
  }

  const overlay = docQuerySelectorStrict('#calibration-overlay');
  const preCalib = docQuerySelectorStrict('#pre-calibration');
  overlay.style.display = 'block';
  preCalib.classList.add('hidden');
  currentPointIndex = 0;
  calibrationData = [];
  showCalibrationPoint(0);
}

// OTAI SECTION: footer

docQuerySelectorStrict('#start-calibration-btn').addEventListener('click', startCalibration);

const recalibrateBtn = docQuerySelectorStrict('#recalibrate-btn');
if (recalibrateBtn) {
  recalibrateBtn.addEventListener('click', recalibrate);
}

// Attach click handlers to all calibration points
const allCalibrationPoints = docQuerySelectorAllStrict('.calibration-point');
allCalibrationPoints.forEach(point => {
  point.addEventListener('click', handlePointClick);
});
