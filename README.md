# oTree — Webcam Eye Tracking Example

> Part of the **[Webcam Eye Tracking Guide](https://kiante-fernandez.github.io/webcam-eyetracking/)** — see the
> parent site for an overview of webcam-based gaze estimation in
> behavioral experiments and examples in other frameworks. This repository
> is the worked example for **[oTree](https://www.otree.org/)** experiments.

The integration is small: a 25-line ASGI wrapper that mounts
[WebEyeTrack](https://github.com/RedForestAI/WebEyeTrack)'s model files at
`/web/`, a 200-line `SimpleGazeTracker` class, and four hidden form fields.
No streaming server, no custom data endpoints — gaze samples ride the
standard form submit.

The demo task is a **Multiple Price List (MPL)** risk-elicitation
experiment, the standard tool for measuring risk preferences in behavioral
economics. Walk the demo to see the pieces in action; then copy the
eye-tracking files into your own oTree app.

---

## Try the demo

You'll need:

- **Python 3.11+** (the environment file pins 3.11 explicitly)
- **A working webcam** and a Chromium-based or Firefox browser. WebEyeTrack
  has not been tested on Safari.
- ~5 minutes for first run (the WebEyeTrack module is fetched from CDN the
  first time the calibration page loads).

```bash
git clone https://github.com/kiante-fernandez/otree-et
cd otree-et

# Option A: conda
conda env create -f environment.yml
conda activate otree-env

# Option B: venv
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

otree resetdb --noinput
uvicorn asgi:application --port 8000
```

Open <http://localhost:8000>, click **Demo → mpl_risk**, and grant the
browser camera permission when prompted. The demo walks you through the
four pages described below in 1–2 minutes.

> ⚠️ **Use `uvicorn`, not `otree devserver`.** WebEyeTrack 0.0.2 fetches
> its model from a hardcoded `/web/...` path inside a Web Worker, and the
> minimal wrapper in [`asgi.py`](asgi.py) is what serves that path. If you
> run `otree devserver` instead, the page loads but the model 404s and the
> tracker silently falls back to mock samples. See
> [What's specific to oTree](#whats-specific-to-otree) for the full story.

### Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| Status badge says **"mock mode"** | You're running `otree devserver` instead of `uvicorn asgi:application`, or your browser can't reach the WebEyeTrack CDN. |
| **Camera permission prompt never appears** | Some browsers remember a previous "deny" — clear the site permissions for `localhost`, then refresh. |
| **`getUserMedia` not supported** | Camera APIs only work over `localhost` or HTTPS. If you're tunneling through ngrok/etc, use the HTTPS URL. |
| **`otree resetdb` complains about a stale schema** | Run `rm db.sqlite3 && otree resetdb --noinput`. |
| **Calibration RMSE shows `n/a`** | WebEyeTrack didn't capture any samples — usually means the camera couldn't see a face. Adjust lighting/position and recalibrate. |

## What you'll see

| Page | What happens |
|------|-------------|
| **Consent** | Asks for camera permission. The *Next* button only appears once permission is granted. |
| **Calibration** | 9-dot click-to-fixate calibration. Reports RMSE in pixels with a green/yellow/red quality band. |
| **Decision** | The 10-row MPL task. A small webcam preview is in the corner; the floating red dot shows real-time gaze. |
| **Results** | Random row is selected for payment; shows the realized payoff. |

Visit <http://localhost:8000/admin> to see the data: each participant has
their MPL choice columns plus per-participant gaze fields, and the
**Custom** export gives a long-format CSV with one row per gaze sample.

## What's specific to oTree

oTree 5+ uses Starlette's ASGI routing rather than Django URL routing —
adding `urls.py` entries is silently ignored. Two things follow:

- **Static-file path mismatch.** WebEyeTrack 0.0.2 fetches its TF.js model
  from a hardcoded `${origin}/web/model.json` *inside a Web Worker*. oTree
  serves project static files at `/static/`, and a `window.fetch` patch in
  the main thread cannot reach the worker. The fix is the minimal ASGI
  wrapper in [`asgi.py`](asgi.py) that mounts `_static/web/` at `/web/` at
  the network layer (~25 lines, one route). Everything else passes through
  to oTree's normal app.
- **Form-based persistence.** Gaze samples ride the standard form submit
  via a hidden `LongStringField`, so there's no streaming endpoint to
  deploy. A `custom_export` then unpacks the JSON into long-format CSV
  for analysis.

## Add eye tracking to your own oTree app

Three files, six fields, one hidden-input block.

**1. Copy these into your project:**

- [`_static/web/`](_static/web/) — TF.js model files (~700 KB)
- [`_static/webeyetrack-loader.js`](_static/webeyetrack-loader.js) — CDN module loader
- [`mpl_risk/gaze_tracker.js`](mpl_risk/gaze_tracker.js) — `SimpleGazeTracker`
- [`asgi.py`](asgi.py) — 25-line ASGI wrapper that serves `_static/web/` at `/web/`

**2. Add six fields to your `Player` model:**

```python
eyetrack_consent           = models.BooleanField(initial=False)
eyetrack_calibration_rmse  = models.FloatField(blank=True)
eyetrack_sample_count      = models.IntegerField(initial=0)
eyetrack_gaze_data         = models.LongStringField(blank=True)
eyetrack_init_status       = models.StringField(initial='unknown')
eyetrack_runtime_error     = models.LongStringField(blank=True)
```

**3. Gate the experiment behind camera consent.** Use the bundled
[`Consent.html`](mpl_risk/Consent.html) +
[`consent.js`](mpl_risk/consent.js), or merge the camera test into your
existing intro page. The contract is: set
`sessionStorage.eyetrack_consent = 'true'` once permission is granted,
and submit the `eyetrack_consent` hidden input as `'1'`.

**4. Calibrate.** Use [`Calibration.html`](mpl_risk/Calibration.html) +
[`calibration.js`](mpl_risk/calibration.js). The calibration grid is
defined in `get_calibration_points()` in
[`__init__.py`](mpl_risk/__init__.py) and rendered into the page from
`js_vars` — change one place to alter the layout.

**5. Track on the page(s) you care about.** Mirror the pattern in
[`Decision.html`](mpl_risk/Decision.html):

```html
<video id="webcam-video" autoplay playsinline muted></video>
<input type="hidden" name="eyetrack_sample_count"   id="eyetrack_sample_count"   value="0">
<input type="hidden" name="eyetrack_gaze_data"      id="eyetrack_gaze_data"      value="[]">
<input type="hidden" name="eyetrack_init_status"    id="eyetrack_init_status"    value="unknown">
<input type="hidden" name="eyetrack_runtime_error"  id="eyetrack_runtime_error"  value="">

<script type="module">
  import { loadWebEyeTrack } from '{{ static "webeyetrack-loader.js" }}';
  loadWebEyeTrack();
</script>
<script>{{ include_sibling 'gaze_tracker.js' }}</script>
<script>
  const tracker = new SimpleGazeTracker({ videoElementId: 'webcam-video' });
  document.addEventListener('DOMContentLoaded', async () => {
    if (await tracker.init()) tracker.startTracking();
    const form = document.querySelector('form');
    let submitting = false;
    form.addEventListener('submit', async function onSubmit(e) {
      if (submitting) return;
      e.preventDefault();
      submitting = true;
      await tracker.stopTracking();
      form.removeEventListener('submit', onSubmit);
      form.submit();
    });
  });
</script>
```

**6. List the new fields in `form_fields`** on the tracked `Page`:
`'eyetrack_sample_count', 'eyetrack_gaze_data', 'eyetrack_init_status', 'eyetrack_runtime_error'`.

## Data captured

### Per participant

Saved to oTree's database and the standard CSV export:

| Field | Meaning |
|-------|---------|
| `eyetrack_consent` | Whether camera permission was granted |
| `eyetrack_calibration_rmse` | Calibration error in pixels (lower is better) |
| `eyetrack_sample_count` | Total gaze samples collected |
| `eyetrack_gaze_data` | JSON array of all gaze samples |
| `eyetrack_init_status` | `ok` / `no_consent` / `init_failed` / `unknown` |
| `eyetrack_runtime_error` | First uncaught JS error on the tracked page (empty if none) |

### Per gaze sample

Available via the **Custom** export — one row per sample, joined with the
participant's `eyetrack_init_status` and an `is_mock` flag (`0`/`1`):

```json
{
  "x": 756.5, "y": 412.3,
  "norm_x": 0.10, "norm_y": -0.05,
  "gaze_state": "open", "confidence": 0.9,
  "t_perf": 12345.67, "timestamp": 1700000000000
}
```

`x`/`y` are screen-space pixels at the time of sampling; `norm_x`/`norm_y`
are WebEyeTrack's `[-0.5, 0.5]` normalized point of gaze.

## Testing

```bash
# Pure-Python unit test (no browser needed)
python tests/test_custom_export.py

# End-to-end smoke test in headless Chromium with a synthetic camera
pip install playwright && python -m playwright install chromium
uvicorn asgi:application --port 8000  # in one terminal
python tests/smoke_e2e.py             # in another
```

See [`tests/README.md`](tests/README.md) for what each layer asserts.

## Production deployment

<details>
<summary>Click to expand</summary>

`otree devserver` is fine for local testing. For a live study:

**Environment variables.** Copy [`.env.example`](.env.example) and set:

| Variable | Purpose |
|----------|---------|
| `OTREE_PRODUCTION` | Set to `1` to switch oTree out of debug mode |
| `OTREE_SECRET_KEY` | Cookie-signing secret. Without it [`settings.py`](settings.py) generates a per-process key, fine for `devserver` but invalidates sessions across restarts. |
| `OTREE_ADMIN_PASSWORD` | Password for the `/admin` interface |
| `DATABASE_URL` | A Postgres URL. SQLite is fine for `devserver` but does not handle concurrent writes well for live sessions. |
| `OTREE_AUTH_LEVEL` | Set to `STUDY` to require login on participant URLs |

**HTTPS is mandatory.** Browsers only expose `getUserMedia` on secure
contexts — localhost is exempt, any other host must serve over TLS or
camera permission will fail.

**Heroku-style hosts.** The included [Procfile](Procfile) starts
`uvicorn asgi:application --host 0.0.0.0 --port $PORT`. Run
`otree resetdb --noinput` once after deploy.

**oTree Hub.** The wrapper in [`asgi.py`](asgi.py) is **not** invoked on
oTree Hub — Hub runs `otree prodserver` directly, so requests to
`/web/model.json` 404 and WebEyeTrack falls back to its mock-data path.
Use a self-hosted deployment (Heroku, Render, fly.io, an oTree-installed
VM) if you need real gaze data.

**Data volume.** At ~30 Hz a 5-minute task produces ~9 000 samples per
participant, roughly 1.5 – 2 MB of JSON in `eyetrack_gaze_data`. Postgres
handles this fine; size your instance accordingly for large studies.

</details>

## Caveats

- **Webcam-grade accuracy.** WebEyeTrack is not a research-grade eye
  tracker. Calibration RMSE is reported in pixels — useful for
  per-participant quality screening, but expect substantial noise.
- **Mock-data fallback.** If WebEyeTrack fails to initialize,
  `SimpleGazeTracker` switches to mock samples around screen center so
  the rest of the task still completes. Filter on
  `eyetrack_init_status='init_failed'` (participant level) or `is_mock=1`
  (per sample) at analysis time.
- **Client-trusted fields.** All `eyetrack_*` fields are written by the
  participant's browser. A motivated participant could spoof them; for
  paid studies, treat them as quality hints and cross-check the
  `gaze_state` distribution and `eyetrack_runtime_error` field.

## Credits & license

- Eye-tracking model and library: [WebEyeTrack](https://github.com/RedForestAI/WebEyeTrack) by RedForestAI
- Experiment framework: [oTree](https://www.otree.org/)
- This integration: [MIT](LICENSE)

If you use this in published research, please cite both this repository
(see [`CITATION.cff`](CITATION.cff)) and the upstream WebEyeTrack project.

For other frameworks, see the parent
[Webcam Eye Tracking Guide](https://kiante-fernandez.github.io/webcam-eyetracking/).
