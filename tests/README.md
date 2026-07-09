# Tests

Three layers, opt-in:

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
- All 9 calibration dots are clickable and the RMSE field is rendered.
- Decision page contains no `€€` double-printed currency.
- Results page renders a single Euro symbol per amount.
- No unexpected JS console errors (TF Lite / MediaPipe INFO chatter is
  filtered).

**Known gap.** Chromium's synthetic camera shows a test pattern with no face,
so the tracker returns `gaze_state: 'closed'` at screen centre for every
sample. This suite therefore cannot validate calibration accuracy or gaze
quality — only that the data path is wired up. Validating those needs one
session with a real webcam.
