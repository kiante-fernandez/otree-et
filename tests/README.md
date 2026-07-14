# Tests

Four layers. Everything except the browser tests runs in under a second:

```bash
python -m pytest tests/          # Python units
node --test tests/js/*.test.mjs  # JavaScript units, no browser
```

## 0. JavaScript unit tests — `tests/js/`

`gaze_tracker.test.mjs` exercises `SimpleGazeTracker` against a stub DOM under
plain `node --test`. No jsdom, no npm dependencies. It pins the properties that
matter for data quality and that a browser test cannot cheaply check:

- a frame with no face is recorded with empty coordinates, never as a fixation
  at the centre of the screen
- repeated camera frames are collapsed to one sample
- the latest gaze reading is available before `startTracking()`, which is what
  the calibration page depends on
- a stale reading is not reused
- a no-consent participant is saved as `no_consent`, not `unknown`
- the server's record of consent beats a lost `sessionStorage` entry
- `init()` reports failure rather than substituting fabricated samples

`calibration_math.test.mjs` covers the calibration geometry and the RMSE.

The suite grew alongside the tracker; the original core of it was written
against a tracker that failed most of these tests, and each later test was
checked to fail against the code before its fix.

---

The three original layers:

## 1. Unit test — `test_payoff.py`

Pure Python. Verifies the MPL price ladder (row 1 is `SAFE_MIN`, the top row
is exactly `SAFE_MAX`, the ladder is strictly increasing, and a risk-neutral
participant's switch row falls strictly inside the ladder) and the payoff rule
(Option A pays that row's safe amount, Option B resolves the lottery, and a row
the participant never answered pays nothing rather than silently resolving the
lottery).

```bash
python tests/test_payoff.py
# or, with pytest installed:
python -m pytest tests/test_payoff.py
```

## 2. Unit test — `test_custom_export.py`

Pure Python. Verifies the `custom_export` long-format generator against
synthetic samples, including malformed `eyetrack_gaze_data`. That field is
written by the participant's browser, so anything that parses as JSON can
reach the export; one malformed row must not abort the whole session's export.

```bash
python tests/test_custom_export.py
# or:
python -m pytest tests/test_custom_export.py
```

## 2b. Unit test — `test_matrix_game.py`

Pure Python. Verifies the matrix game is a genuine Prisoner's Dilemma
(temptation > reward > punishment > sucker, and cooperation jointly efficient),
that the payoff matrix covers all four outcomes, and that the drawn opponent
decision is recorded so every payoff can be audited.

## 3. End-to-end smoke test — `smoke_e2e.py`

Headless Chromium walks the full Consent → Calibration → Decision →
Results flow with a synthetic camera stream
(Chromium's `--use-fake-device-for-media-stream`). Catches
template and wiring regressions a unit test can't.

One-time setup:

```bash
pip install playwright
python -m playwright install chromium
```

In one terminal:

```bash
otree devserver
```

(Not `otree resetdb` first — `devserver` manages its own database, and rejects
one that `resetdb` created.)

In another:

```bash
python tests/smoke_e2e.py
```

What it checks:

- `eyetrack_consent` hidden input flips to `'1'` after the camera test.
- Calibration loading overlay clears (the gaze model loaded from
  `/static/web/model.json`).
- With no face in frame, calibration refuses: the hint appears, the dot does
  not advance, and no point is recorded.
- After repeated failures the participant is offered a way past the page, and
  taking it works. Nothing else on the calibration page can move them forward.
- On the Decision page: `init_status == 'ok'`, samples were actually collected,
  no-face samples carry empty coordinates, and there is exactly one sample per
  camera frame.
- Decision page contains no `€€` double-printed currency.
- Results page renders a single Euro symbol per amount.
- No unexpected JS console errors. MediaPipe's own INFO chatter is filtered;
  `404` and `WebEyeTrack` deliberately are not, because those are what a broken
  model mount emits.

## 4. Calibration persistence — `test_calibration_persistence.py`

Drives Consent → Calibration → Decision and asserts the personalised model is
written to IndexedDB and restored on the next page, under a key derived from the
participant. This is the property the integration rests on: gaze-model
adaptation lives in a Web Worker that every oTree page load destroys.

```bash
otree devserver                              # in one terminal
python tests/test_calibration_persistence.py # in another
```

## 5. Matrix game end-to-end — `test_matrix_e2e.py`

Walks the `matrix_game` demo on the shared `eyetrack` app: a second task with
no eye-tracking code of its own beyond the include and the field block. Asserts
the payoff cells' `data-eyetrack-roi` rectangles are captured and posted, and
that the Results payoff matches the recorded choices and the matrix.

## 6. Task battery end-to-end — `test_battery_e2e.py`

Walks the `task_battery` config: consent, one calibration save, then BOTH
tasks. Asserts each task page reports `calibrationRestored === true` under the
same participant key — the calibrate-once-track-everywhere claim, exercised
across two real app boundaries — and that neither page silently fell back to
the base model.

## 7. Scanpath visualizer — `test_visualizer.py`

Drives `tools/gaze_visualizer.html` in headless Chromium against a real
`all_apps_wide` export (fetched from a running server, or pass a CSV path):
participants and tasks discovered, the scanpath actually drawn to canvas, the
ROI dwell table populated, playback advancing, scrubbing redrawing.

**Known gap.** Chromium's synthetic camera shows a test pattern with no face,
so the tracker returns `gaze_state: 'closed'` for every sample and `calibrate()`
has nothing to adapt to. The browser suites therefore verify the data path, the
refusal behaviour, and the persistence mechanism — but not calibration
*accuracy*. That needs one session with a real webcam.
