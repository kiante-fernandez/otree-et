/**
 * Calibration routine.
 *
 * Two phases, both driven by the participant clicking a dot they are looking at.
 *
 *   1. Calibration. Each click adapts the gaze model to that screen location.
 *   2. Validation. Held-out points: gaze error is measured, the model is not
 *      touched. `eyetrack_calibration_rmse` is the error on these points, which
 *      is why it means something — error measured on the points the model was
 *      fit to would be optimistic by construction.
 *
 * The personalised model is then saved to IndexedDB under `calibration_key`, so
 * the pages that follow can restore it. Model adaptation lives inside a Web
 * Worker that is destroyed on every oTree page navigation; without saving and
 * restoring, calibration cannot reach the task at all.
 */

const CALIBRATION_POINTS = js_vars.calibration_points;
const VALIDATION_POINTS = js_vars.validation_points;
const ALL_POINTS = CALIBRATION_POINTS.concat(VALIDATION_POINTS);

const { pctToNorm, gazeError, computeRMSE } = window.calibrationMath;

// How many times the tracker may fail to see a face before we offer the
// participant a way out. Without an escape they cannot advance the dot and
// there is no Next button on this page.
const NO_FACE_ATTEMPTS_BEFORE_ESCAPE = 3;

let gazeTracker = null;
let currentPointIndex = 0;
let validationErrors = [];   // px error at each held-out point
let busy = false;            // guards against re-entrant clicks
let noFaceAttempts = 0;

function buildCalibrationDots() {
  const overlay = docQuerySelectorStrict('#calibration-overlay');
  // The overlay also holds the phase label, the hint, and the escape button,
  // so test for the dots themselves rather than for any children at all.
  if (overlay.querySelector('.calibration-point')) return;
  for (const p of ALL_POINTS) {
    const dot = document.createElement('div');
    dot.className = 'calibration-point';
    dot.style.left = p.x + '%';
    dot.style.top = p.y + '%';
    dot.addEventListener('click', handlePointClick);
    overlay.appendChild(dot);
  }
}

function showCalibrationPoint(index) {
  const allDots = docQuerySelectorAllStrict('.calibration-point');
  allDots.forEach(d => d.classList.remove('active'));
  // The sequence is driven from a setTimeout, so guard the bound rather than
  // letting a stray index throw on allDots[index].
  if (index < 0 || index >= allDots.length) return;
  allDots[index].classList.add('active');

  const phase = index < CALIBRATION_POINTS.length ? 'Calibrating' : 'Checking accuracy';
  const label = document.getElementById('calibration-phase');
  if (label) label.textContent = `${phase} — point ${index + 1} of ${ALL_POINTS.length}`;
}

function showHint(message) {
  const hint = document.getElementById('calibration-live-hint');
  if (!hint) return;
  hint.textContent = message || '';
  hint.classList.toggle('hidden', !message);
}

async function handlePointClick(event) {
  // Only the active dot counts, and only one click at a time. Without both
  // guards a double-click advances the sequence twice: the second click records
  // the *next* point's target against the gaze captured for this one, and the
  // skipped dot is never shown.
  if (busy) return;
  const dots = docQuerySelectorAllStrict('.calibration-point');

  // Capture the element now, synchronously. `event.currentTarget` is only set
  // while the event is being dispatched; the first `await` below returns
  // control to the browser, which resets it to null.
  const dot = event.currentTarget;
  if (dot !== dots[currentPointIndex]) return;

  busy = true;
  try {
    const point = ALL_POINTS[currentPointIndex];
    const gaze = gazeTracker ? gazeTracker.getCurrentGaze() : null;

    if (!gaze) {
      // No face, eyes closed, or a stale reading. Recording the point anyway
      // would either fabricate a measurement or adapt the model to noise.
      noFaceAttempts++;
      showHint('Face not detected — look at the camera and click the dot again.');
      if (noFaceAttempts >= NO_FACE_ATTEMPTS_BEFORE_ESCAPE) {
        const escape = document.getElementById('calibration-escape');
        if (escape) escape.classList.remove('hidden');
      }
      return;
    }
    noFaceAttempts = 0;
    showHint('');

    const isCalibration = currentPointIndex < CALIBRATION_POINTS.length;

    if (isCalibration) {
      const adapted = await gazeTracker.calibrate(pctToNorm(point.x), pctToNorm(point.y));
      if (!adapted) {
        showHint('Could not use that point — hold still and click the dot again.');
        return;
      }
    } else {
      // Held out: measure, do not adapt.
      validationErrors.push(gazeError(gaze, point, window.innerWidth, window.innerHeight));
    }

    // Stop it pulsing immediately. Otherwise the recorded dot stays `active`
    // for the whole inter-dot delay and a quick participant clicks it twice.
    dot.classList.remove('active');
    dot.classList.add('clicked');
    currentPointIndex++;

    if (currentPointIndex < ALL_POINTS.length) {
      setTimeout(() => showCalibrationPoint(currentPointIndex), js_vars.delay_ms);
    } else {
      setTimeout(finishCalibration, js_vars.delay_ms);
    }
  } finally {
    busy = false;
  }
}

async function finishCalibration() {
  const overlay = docQuerySelectorStrict('#calibration-overlay');
  const completion = docQuerySelectorStrict('#calibration-complete');
  overlay.style.display = 'none';
  completion.classList.remove('hidden');

  const rmse = computeRMSE(validationErrors);

  const rmseInput = document.getElementById('eyetrack_calibration_rmse');
  if (rmseInput) rmseInput.value = rmse.toString();

  const rmseDisplay = document.getElementById('calibration-rmse-value');
  if (rmseDisplay) {
    rmseDisplay.textContent = rmse > 0 ? rmse.toFixed(0) : 'n/a';
    // Quality bands are heuristic. Tune in your own study.
    rmseDisplay.className =
      rmse <= 0   ? '' :
      rmse <= 100 ? 'rmse-good' :
      rmse <= 200 ? 'rmse-ok'   :
                    'rmse-poor';
    if (rmse > 200) {
      const hint = document.getElementById('calibration-rmse-hint');
      if (hint) hint.classList.remove('hidden');
    }
  }

  // Persist the personalised model for the pages that follow. If this fails the
  // task still runs, but its gaze will come from an uncalibrated model, so say
  // so rather than let the data look calibrated.
  const saveStatus = document.getElementById('calibration-save-status');
  try {
    await gazeTracker.saveCalibration(js_vars.calibration_key);
    if (saveStatus) saveStatus.textContent = 'Calibration saved.';
  } catch (error) {
    console.error('Failed to save calibration:', error);
    if (saveStatus) {
      saveStatus.textContent =
        'Calibration could not be saved; the task will run without it.';
      saveStatus.className = 'text-danger';
    }
  }

  revealProceed();
}

async function initializeGazeTracker() {
  gazeTracker = new SimpleGazeTracker({
    videoElementId: 'webcam-video',
    modelUrl: js_vars.model_url,
    // Start from the base model: a recalibration should not build on a previous
    // attempt. The adapted model is written out at the end instead.
    calibrationKey: null,
    // Calibration drives adaptation explicitly through calibrate(), which is not
    // debounced. Leaving the library's click listener on would also adapt to the
    // Next button and to any stray click.
    adaptOnClick: false,
    maxPoints: js_vars.max_calibration_points,
  });
  return gazeTracker.init();
}

async function startCalibration() {
  const startBtn = docQuerySelectorStrict('#start-calibration-btn');
  startBtn.disabled = true;

  if (!gazeTracker || !gazeTracker.isInitialized) {
    const ok = await initializeGazeTracker();
    if (!ok) {
      startBtn.disabled = false;
      showTrackerUnavailable(gazeTracker ? gazeTracker.runtimeError : 'unknown error');
      return;
    }
    gazeTracker.startTracking();
  }

  docQuerySelectorStrict('#calibration-overlay').style.display = 'block';
  docQuerySelectorStrict('#pre-calibration').classList.add('hidden');
  currentPointIndex = 0;
  validationErrors = [];
  busy = false;
  showCalibrationPoint(0);
}

function revealProceed() {
  const proceed = document.getElementById('proceed');
  if (proceed) proceed.classList.remove('hidden');
}

function showTrackerUnavailable(message) {
  docQuerySelectorStrict('#pre-calibration').classList.add('hidden');
  const box = document.getElementById('tracker-unavailable');
  if (box) box.classList.remove('hidden');
  const detail = document.getElementById('tracker-unavailable-detail');
  if (detail) detail.textContent = message || '';
  // The participant must always have a way out of this page.
  revealProceed();
}

async function recalibrate() {
  docQuerySelectorStrict('#calibration-complete').classList.add('hidden');
  for (const d of docQuerySelectorAllStrict('.calibration-point')) {
    d.classList.remove('clicked');
    d.classList.remove('active');
  }
  showHint('');
  // Rebuild the tracker so the model starts from the base weights again.
  if (gazeTracker) gazeTracker.destroy();
  gazeTracker = null;
  docQuerySelectorStrict('#pre-calibration').classList.remove('hidden');
  await startCalibration();
}

/**
 * Abandon calibration. The task still runs; its gaze will come from an
 * uncalibrated model, and eyetrack_calibration_rmse stays empty, which is how
 * the analyst tells these participants apart.
 */
function skipCalibration() {
  docQuerySelectorStrict('#calibration-overlay').style.display = 'none';
  if (gazeTracker) gazeTracker.destroy();
  gazeTracker = null;
  showTrackerUnavailable('Calibration was skipped.');
}

buildCalibrationDots();
docQuerySelectorStrict('#start-calibration-btn').addEventListener('click', startCalibration);

const skipBtn = document.getElementById('skip-calibration-btn');
if (skipBtn) skipBtn.addEventListener('click', skipCalibration);

const recalibrateBtn = document.getElementById('recalibrate-btn');
if (recalibrateBtn) recalibrateBtn.addEventListener('click', recalibrate);

window.addEventListener('beforeunload', () => {
  if (gazeTracker) gazeTracker.destroy();
});
