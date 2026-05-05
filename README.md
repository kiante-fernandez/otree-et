# oTree — Webcam Eye Tracking Example

A working integration of in-browser webcam eye tracking
([WebEyeTrack](https://github.com/RedForestAI/WebEyeTrack)) for
[oTree](https://www.otree.org/) experiments.

The demo task is a Multiple Price List (MPL) for measuring risk
preferences — a common task in behavioral economics. You can run it as-is
to see eye tracking working, then copy the eye-tracking pieces into your
own oTree app.

---

## Try the demo

You will need:

- Python 3.11 or newer
- A working webcam
- Chrome, Edge, or Firefox (Safari has not been tested)

Open a terminal and run:

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

Open <http://localhost:8000> in your browser, click **Demo**, then
**mpl_risk**, and grant the camera permission when your browser asks.
The demo takes one or two minutes to walk through.

The first time you load the calibration page the browser downloads the
eye-tracking model from a CDN, which can take a few seconds.

**Note:** start the server with `uvicorn asgi:application`, not
`otree devserver`. The `otree devserver` command runs but the
eye-tracking model fails to load and the tracker quietly switches to fake
data. The line above is the right command.

## What you will see

| Page | What happens |
|------|-------------|
| Consent | Asks for camera permission. The Next button only appears once you grant access. |
| Calibration | Click each red dot as it appears. The completion screen shows a calibration error in pixels (lower is better). |
| Decision | The 10-row MPL task. A small webcam preview is in the corner, and a faint red dot follows your gaze. |
| Results | Picks one row at random and shows the payoff. |

To see the data, open <http://localhost:8000/admin>. Each participant has
their MPL choices plus the eye-tracking fields listed below. The Custom
export gives one row per gaze sample for analysis.

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| Status badge says "mock mode" | The eye-tracking model failed to load. Most often: you ran `otree devserver` instead of `uvicorn asgi:application`. |
| Camera permission prompt never appears | The browser remembers a previous "deny". Clear site permissions for `localhost` and refresh. |
| `getUserMedia` not supported | Camera APIs only work on `localhost` or HTTPS. Tunneling through ngrok? Use the HTTPS URL. |
| `otree resetdb` complains about a stale schema | Run `rm db.sqlite3 && otree resetdb --noinput`. |
| Calibration error reads "n/a" | The webcam couldn't see a face. Improve lighting, sit closer, and recalibrate. |

## Add eye tracking to your own oTree app

Three files to copy, six fields to add, one block of HTML.

**1. Copy these into your project:**

- [`asgi.py`](asgi.py) — small Python file that serves the model files at `/web/`
- [`_static/web/`](_static/web/) — the model files themselves (about 700 KB)
- [`_static/webeyetrack-loader.js`](_static/webeyetrack-loader.js) — loads the eye-tracking library
- [`mpl_risk/gaze_tracker.js`](mpl_risk/gaze_tracker.js) — the `SimpleGazeTracker` class that records samples

**2. Add six fields to your `Player` model:**

```python
eyetrack_consent           = models.BooleanField(initial=False)
eyetrack_calibration_rmse  = models.FloatField(blank=True)
eyetrack_sample_count      = models.IntegerField(initial=0)
eyetrack_gaze_data         = models.LongStringField(blank=True)
eyetrack_init_status       = models.StringField(initial='unknown')
eyetrack_runtime_error     = models.LongStringField(blank=True)
```

**3. Use the bundled consent and calibration pages.** Drop in
[`Consent.html`](mpl_risk/Consent.html) +
[`consent.js`](mpl_risk/consent.js) and
[`Calibration.html`](mpl_risk/Calibration.html) +
[`calibration.js`](mpl_risk/calibration.js) as-is, or merge them into
your existing intro flow.

**4. Track on the page(s) you care about.** Mirror
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

**5. Add the new fields to `form_fields`** on the tracked Page:
`'eyetrack_sample_count', 'eyetrack_gaze_data', 'eyetrack_init_status', 'eyetrack_runtime_error'`.

## Data captured

### Per participant

| Field | Meaning |
|-------|---------|
| `eyetrack_consent` | Whether camera permission was granted |
| `eyetrack_calibration_rmse` | Calibration error in pixels (lower is better) |
| `eyetrack_sample_count` | Total gaze samples collected |
| `eyetrack_gaze_data` | JSON array of all gaze samples |
| `eyetrack_init_status` | `ok`, `no_consent`, `init_failed`, or `unknown` |
| `eyetrack_runtime_error` | First uncaught browser error on the tracked page (empty if none) |

### Per gaze sample

The Custom export gives one row per sample, joined with the participant's
`eyetrack_init_status` and an `is_mock` flag (`0` or `1`):

```json
{
  "x": 756.5, "y": 412.3,
  "norm_x": 0.10, "norm_y": -0.05,
  "gaze_state": "open", "confidence": 0.9,
  "t_perf": 12345.67, "timestamp": 1700000000000
}
```

`x` and `y` are screen-space pixels at the time of sampling. `norm_x` and
`norm_y` are the library's normalized point of gaze in the range
`[-0.5, 0.5]`.

## Testing

```bash
# Quick check (no browser needed)
python tests/test_custom_export.py

# Full end-to-end test in a headless browser with a synthetic camera
pip install playwright
python -m playwright install chromium
uvicorn asgi:application --port 8000  # in one terminal
python tests/smoke_e2e.py             # in another
```

See [`tests/README.md`](tests/README.md) for what each test checks.

## Production deployment

<details>
<summary>Click to expand</summary>

`uvicorn asgi:application --port 8000` is fine for local testing. For a
live study:

**Environment variables.** Copy [`.env.example`](.env.example) and set:

| Variable | Purpose |
|----------|---------|
| `OTREE_PRODUCTION` | Set to `1` to switch oTree out of debug mode |
| `OTREE_SECRET_KEY` | Cookie-signing secret. Without it [`settings.py`](settings.py) generates a per-process key, which means participants get logged out on every restart. |
| `OTREE_ADMIN_PASSWORD` | Password for the `/admin` interface |
| `DATABASE_URL` | Postgres URL (`postgres://...`). SQLite is fine for `devserver` but does not handle concurrent writes well. |
| `OTREE_AUTH_LEVEL` | Set to `STUDY` to require login on participant URLs |

**HTTPS is required.** Browsers only allow camera access on `localhost`
or HTTPS. If you deploy behind a proxy, make sure it terminates TLS and
forwards `X-Forwarded-Proto`.

**Heroku-style hosts.** The included [Procfile](Procfile) starts
`uvicorn asgi:application --host 0.0.0.0 --port $PORT`. Run
`otree resetdb --noinput` once after deploy.

**oTree Hub.** The wrapper in [`asgi.py`](asgi.py) is not invoked on
oTree Hub, so the model 404s and the tracker silently records mock data.
Use a self-hosted deployment (Heroku, Render, fly.io, an oTree-installed
VM) if you need real gaze data.

**Data volume.** At about 30 samples per second a 5-minute task produces
roughly 9,000 samples per participant, around 1.5–2 MB of JSON per row.
Postgres handles this easily; size the instance accordingly for studies
with many participants.

</details>

## Caveats

- **Webcam-grade accuracy.** This is not a research-grade eye tracker.
  Calibration error is reported in pixels and is useful for screening,
  but expect substantial noise.
- **Mock data fallback.** If the eye-tracking library fails to start,
  the tracker keeps the experiment running with fake samples around the
  screen center. Filter on `eyetrack_init_status='init_failed'` or
  `is_mock=1` when analyzing.
- **Client-trusted fields.** All `eyetrack_*` fields are written by the
  participant's browser. A determined participant could spoof them.
  Treat them as quality hints rather than ground truth.

## How it works

The library used here, [WebEyeTrack](https://github.com/RedForestAI/WebEyeTrack),
runs entirely in the browser and only sends the gaze coordinates back to
the server, not the video. It loads its model from a hardcoded URL
(`/web/model.json`), which doesn't match where oTree puts static files.
The 25-line [`asgi.py`](asgi.py) is a thin wrapper that serves that one
URL prefix and passes everything else to oTree. Gaze samples are
collected in the browser and posted to the server with the rest of the
form data — no streaming server required.

## Credits and license

- Eye-tracking library:
  [WebEyeTrack](https://github.com/RedForestAI/WebEyeTrack) by RedForestAI
- Experiment framework: [oTree](https://www.otree.org/)
- This integration: [MIT](LICENSE)

If you use this in published research, please cite both this repository
(see [`CITATION.cff`](CITATION.cff)) and the upstream WebEyeTrack project.
