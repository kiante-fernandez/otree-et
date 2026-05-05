const calibrationPoints = js_vars.calibration_points;
let currentPointIndex = 0;
let calibrationData = [];
let gazeTracker = null;

function buildCalibrationDots() {
  const overlay = docQuerySelectorStrict('#calibration-overlay');
  // Inject dots once, positioned from js_vars (the same list __init__.py uses).
  if (overlay.children.length === 0) {
    for (const p of calibrationPoints) {
      const dot = document.createElement('div');
      dot.className = 'calibration-point';
      dot.style.left = p.x + '%';
      dot.style.top = p.y + '%';
      dot.addEventListener('click', handlePointClick);
      overlay.appendChild(dot);
    }
  }
}

async function initializeGazeTracker() {
  gazeTracker = new SimpleGazeTracker({ videoElementId: 'webcam-video' });

  const initialized = await gazeTracker.init();
  if (!initialized) {
    console.warn('GazeTracker initialization failed, calibration will proceed without gaze capture');
  }
  return initialized;
}

function calculateCalibrationRMSE(data) {
  if (data.length === 0) return 0;

  let sumSquaredError = 0;
  let validSamples = 0;

  for (const point of data) {
    if (point.gaze_x !== undefined && point.gaze_y !== undefined) {
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

  sessionStorage.setItem('calibration_data', JSON.stringify(calibrationData));

  const rmse = calculateCalibrationRMSE(calibrationData);
  sessionStorage.setItem('calibration_rmse', rmse.toString());

  const rmseInput = document.getElementById('eyetrack_calibration_rmse');
  if (rmseInput) {
    rmseInput.value = rmse.toString();
  }

  const rmseDisplay = document.getElementById('calibration-rmse-value');
  if (rmseDisplay) {
    rmseDisplay.textContent = rmse > 0 ? rmse.toFixed(0) : 'n/a';
    // Quality bands are heuristic. Tune in your own study.
    rmseDisplay.className =
      rmse <= 0       ? '' :
      rmse <= 100     ? 'rmse-good' :
      rmse <= 200     ? 'rmse-ok'   :
                        'rmse-poor';
    if (rmse > 200) {
      const hint = document.getElementById('calibration-rmse-hint');
      if (hint) hint.classList.remove('hidden');
    }
  }
}

function handlePointClick(event) {
  const target = event.currentTarget;
  const pointData = calibrationPoints[currentPointIndex];

  const currentGaze = gazeTracker ? gazeTracker.getCurrentGaze() : null;

  calibrationData.push({
    target_x: pointData.x,
    target_y: pointData.y,
    gaze_x: currentGaze ? currentGaze.x : undefined,
    gaze_y: currentGaze ? currentGaze.y : undefined,
    gaze_state: currentGaze ? currentGaze.gazeState : undefined,
    t: performance.now(),
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
  for (const p of docQuerySelectorAllStrict('.calibration-point')) {
    p.classList.remove('clicked');
  }
  startCalibration();
}

function showCalibrationPoint(index) {
  const allPoints = docQuerySelectorAllStrict('.calibration-point');
  allPoints.forEach(p => p.classList.remove('active'));
  allPoints[index].classList.add('active');
}

async function startCalibration() {
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

buildCalibrationDots();

docQuerySelectorStrict('#start-calibration-btn').addEventListener('click', startCalibration);

const recalibrateBtn = document.getElementById('recalibrate-btn');
if (recalibrateBtn) {
  recalibrateBtn.addEventListener('click', recalibrate);
}
