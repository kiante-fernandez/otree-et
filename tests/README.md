# Tests

Two layers, opt-in:

## 1. Unit test — `test_custom_export.py`

Pure Python, no browser, no oTree runtime needed. Verifies the
`custom_export` long-format generator against synthetic samples.

```bash
python tests/test_custom_export.py
# or, with pytest installed:
python -m pytest tests/test_custom_export.py
```

## 2. End-to-end smoke test — `smoke_e2e.py`

Headless Chromium walks the full Consent → Calibration → Decision →
Results flow with a synthetic camera stream
(Chromium's `--use-fake-device-for-media-stream`). Catches
template/wiring/fetch-shim regressions a unit test can't.

One-time setup:

```bash
pip install playwright
python -m playwright install chromium
```

In one terminal, run the dev server through the ASGI wrapper (so the
`/web/` model mount is in place):

```bash
otree resetdb --noinput
uvicorn asgi:application --port 8000
```

In another:

```bash
python tests/smoke_e2e.py
```

What it checks:

- `eyetrack_consent` hidden input flips to `'1'` after the camera test.
- Calibration loading overlay clears (WebEyeTrack model loaded from
  `/web/model.json`, served by `asgi.py`).
- All 9 calibration dots are clickable and the RMSE field is rendered.
- Decision page contains no `€€` double-printed currency.
- Results page renders a single Euro symbol per amount.
- No unexpected JS console errors (TF Lite / MediaPipe INFO chatter is
  filtered).
