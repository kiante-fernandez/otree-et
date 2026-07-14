# oTree — Webcam Eye Tracking Example

A working integration of in-browser webcam eye tracking
([WebEyeTrack](https://github.com/RedForestAI/WebEyeTrack)) for
[oTree](https://www.otree.org/) experiments.

The demos are standard behavioral-economics tasks — a multiple price list
for risk preferences, and a one-shot Prisoner's Dilemma played on a payoff
matrix — each with live eye tracking added. Run any of them as-is to see the
tracking working, then follow the same recipe to add it to your own task.

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

otree devserver
```

Do not run `otree resetdb` first. `devserver` keeps its database in memory and
writes it out when you stop it; a database created by `resetdb` is missing a
version marker that `devserver` then rejects.

Open <http://localhost:8000> in your browser, click **Demo**, and pick a
task. Grant the camera permission when your browser asks. Each demo takes a
minute or two to walk through; the calibration step is the same in all of
them, so the "Both tasks" session shows the point best — calibrate once,
then two tracked tasks.

Everything the tracker needs — the library, the gaze model, and MediaPipe's
face detector — ships with this repository and is served from `/static/`. No
participant's browser contacts a third-party host while a study is running, so
any standard oTree command works and nothing depends on a CDN being up.

## What you will see

| Page | What happens |
|------|-------------|
| Consent | Asks for camera permission. The Next button only appears once you grant access. |
| Calibration | Click each red dot as it appears. The completion screen shows the calibration error measured on held-out points. |
| The task | The 10-row price list, or the 2×2 payoff matrix, depending on the demo. A small webcam preview sits in the corner and a faint red dot follows your gaze. |
| Results | The payoff, and how it was determined. |

To see the data, open <http://localhost:8000/admin>. Each participant has
their task choices plus the eye-tracking fields listed below. Each task app's
Custom export gives one row per gaze sample, labeled with the app and page it
came from.

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| Status badge says "unavailable" | The tracker could not start. `eyetrack_runtime_error` says why. If it mentions the library, re-run `tools/build_webeyetrack.sh`. |
| "Face not detected" on every calibration dot | The webcam cannot see a face. Improve lighting, sit closer, remove glare. The dot deliberately will not advance without a gaze reading. |
| Camera permission prompt never appears | The browser remembers a previous "deny". Clear site permissions for `localhost` and refresh. |
| `getUserMedia` not supported | Camera APIs only work on `localhost` or HTTPS. Tunneling through ngrok? Use the HTTPS URL. |
| "oTree has been updated. Please delete your database" | Your `db.sqlite3` predates the installed oTree, or was created by `otree resetdb`. Run `rm db.sqlite3` and start `otree devserver` again. |
| `eyetrack_calibration_rmse` is empty | The participant skipped calibration. Their gaze comes from an uncalibrated model; exclude or flag them. |

## The example tasks

Three demo sessions, each a task researchers already know, with live eye
tracking added:

| Session config | Task | Why gaze is interesting here |
|---|---|---|
| `mpl_risk` | Multiple price list (risk preferences) | Attention to the safe amounts versus the lottery down the list |
| `matrix_game` | One-shot Prisoner's Dilemma, 2×2 payoff matrix | Which payoffs a player inspects — own versus other, cooperation versus defection cells — before choosing |
| `task_battery` | Both tasks in one session | Calibrate once at the start; the calibration follows the participant into every task |

Each config runs the shared [`eyetrack`](eyetrack/) app first (camera consent,
then calibration). The calibrated gaze model is stored in the participant's
browser under a key derived from their participant code, and every tracked page
afterwards — in any app — restores it.

The matrix game is single-player so the demo can run solo: the other player's
decision is drawn at random at submission and the Results page says so. In a
real study, replace `draw_opponent()` in
[`matrix_game/__init__.py`](matrix_game/__init__.py) with decisions
pre-recorded from human participants.

## Add eye tracking to your own oTree task

The tasks above are worked examples of a four-step recipe. `matrix_game` is the
cleaner one to copy from — it was written against this recipe from the start.

**1. Put the shared `eyetrack` app first** in your session config:

```python
dict(name='my_study', app_sequence=['eyetrack', 'my_task'], num_demo_participants=1)
```

and declare the participant fields it writes (in `settings.py`):

```python
PARTICIPANT_FIELDS = [
    'eyetrack_consent',
    'eyetrack_calibration_rmse',
    'eyetrack_calibration_rmse_fraction',
]
```

**2. Add the field block to your task's `Player` model** (copy it verbatim from
[`matrix_game/__init__.py`](matrix_game/__init__.py) — nine `eyetrack_*`
fields), and wire the tracked Page with the two helpers from
[`eyetrack_shared.py`](eyetrack_shared.py):

```python
from eyetrack_shared import EYETRACK_FORM_FIELDS, eyetrack_js_vars, gaze_rows

class Decision(Page):
    form_model = 'player'
    form_fields = ['your_task_field'] + EYETRACK_FORM_FIELDS

    @staticmethod
    def js_vars(player):
        return eyetrack_js_vars(player)


def custom_export(players):
    yield from gaze_rows(players, 'my_task', 'Decision')
```

**3. Add three elements and one include to the tracked template:**

```html
<div id="tracking-status" class="status-inactive">Eye tracking: initializing...</div>
<div id="gaze-dot"></div>
<video id="webcam-video" autoplay playsinline muted></video>

...your task's content...

{{ include 'eyetrack/tracked_page.html' }}
```

**4. Mark the regions your analysis cares about.** Any element with a
`data-eyetrack-roi="name"` attribute has its on-screen rectangle recorded
alongside the gaze samples (again at every resize or scroll), so fixations can
be assigned to payoff cells, table rows, or options offline:

```html
<td data-eyetrack-roi="cell-cooperate-cooperate">{{ C.PAYOFF_REWARD }}</td>
```

That is the whole integration. Consent, calibration, honest failure reporting,
and the data path are all inherited from the shared app; your task stays a
plain oTree app.

Calibration lives in the gaze model's weights, inside a Web Worker that every
oTree page load recreates. The participant-keyed storage is what lets a
calibration performed once apply to every page — and every app — that follows.

## Data captured

### Per participant

On the `eyetrack` app (once per participant, also copied to the participant):

| Field | Meaning |
|-------|---------|
| `eyetrack_consent` | Whether camera permission was granted |
| `eyetrack_calibration_rmse` | Error in pixels on the four held-out validation points (lower is better). **Empty means calibration was skipped** — all gaze from this participant comes from an uncalibrated model. |
| `eyetrack_calibration_rmse_fraction` | The same error as a fraction of the screen diagonal. **Compare participants on this, not on pixels.** |

On every tracked task page:

| Field | Meaning |
|-------|---------|
| `eyetrack_sample_count` | Total gaze samples collected on this page |
| `eyetrack_gaze_data` | JSON array of all gaze samples |
| `eyetrack_rois` | Snapshots of every `data-eyetrack-roi` element's on-screen rectangle (re-captured after each resize or scroll), for mapping gaze to regions offline |
| `eyetrack_viewport_width`, `eyetrack_viewport_height` | The screen the gaze was measured on. Sample `x`/`y` are pixels and mean nothing without it. |
| `eyetrack_viewport_changed` | `True` if the window was resized mid-task, so samples before and after are scaled to different viewports |
| `eyetrack_init_status` | `ok`, `no_consent`, `init_failed`, `init_pending` (the page was submitted while the model was still loading), or `unknown` (the page never ran the tracker at all) |
| `eyetrack_calibration_restored` | Whether this page used the model **this participant** calibrated. `False` means their gaze came from the uncalibrated base model, whatever the RMSE says. |
| `eyetrack_runtime_error` | First uncaught browser error on the tracked page (empty if none) |

The MPL task also records `num_switches` and `switch_row` (a coherent
respondent switches option exactly once; multiple switchers have not revealed
a risk preference and are normally excluded).

`eyetrack_calibration_rmse` is measured on points the model was *not* fitted to.
Error on the points used for calibration would be optimistic by construction.

A pixel error is not comparable across participants: 265 px is 16% of a
1512-wide laptop window and 7% of a 3440-wide monitor. Use
`eyetrack_calibration_rmse_fraction`. As a rough guide, under 6% of the screen
diagonal is good, under 12% is usable, beyond that is poor.

For a participant whose gaze you intend to analyse, you want
`eyetrack_init_status = 'ok'`, `eyetrack_calibration_restored = True`,
`eyetrack_viewport_changed = False`, and an error you are happy with.

Expect around 20–30 samples per second. Vertical gaze is markedly less accurate
than horizontal — a webcam sees far less vertical eye movement — so most of the
error is usually in `y`. A measured session on a 1512 × 781 window scored 79 px
(4.7% of the diagonal) with horizontal spread of 389 px against only 125 px
vertically.

**This matters for regions of interest.** With a held-out error of that size,
gaze reliably distinguishes the *columns* of the price list (Option A vs Option
B) but not necessarily individual *rows*, which are only a few tens of pixels
tall. Design your regions of interest around what the tracker can actually
resolve, and check `eyetrack_calibration_rmse_fraction` before assuming
row-level attribution.

### Per gaze sample

The Custom export gives one row per sample, joined with the participant's
`eyetrack_init_status`:

```json
{
  "x": 756.5, "y": 412.3,
  "norm_x": 0.10, "norm_y": -0.05,
  "gaze_state": "open", "clipped": false,
  "t_perf": 12345.67, "frame_time": 4.85
}
```

| Column | Meaning |
|--------|---------|
| `x`, `y` | Screen pixels. **Empty when no face was detected** — never a guessed location. |
| `norm_x`, `norm_y` | The library's normalized point of gaze, in `[-0.5, 0.5]`. Empty when no face was detected. |
| `gaze_state` | `open` when a face was tracked. Any other value means the coordinates are empty rather than a real fixation. |
| `clipped` | `1` when the estimate was saturated at a screen edge. The tracker clips gaze to the screen, so such a sample is **censored, not measured**: the participant was looking further out. |
| `t_perf` | Milliseconds since page load. Monotonic — **use this for timing**. |
| `frame_time` | The camera's own clock, in *seconds* since the video stream started. A different clock from `t_perf`. |

One sample per unique camera frame. The library reports gaze on every animation
frame (~60 Hz) while the camera runs at ~30 fps, so roughly a third of its
reports re-process the previous frame; those are collapsed rather than stored
twice.

Samples are **not independent**: the library runs a Kalman filter over its
estimates, so consecutive samples are smoothed and autocorrelated. Treat them as
a filtered time series, not as repeated independent measurements.

## Testing

```bash
# Fast checks, no browser (about a second)
python -m pytest tests/
node --test tests/js/*.test.mjs

# Browser tests with a synthetic camera
pip install playwright
python -m playwright install chromium
otree devserver                              # in one terminal
python tests/smoke_e2e.py                    # in another
python tests/test_calibration_persistence.py # calibration survives the page change
python tests/test_offline.py                 # works with every CDN blocked
python tests/test_matrix_e2e.py              # second task on the shared eyetrack app
python tests/test_battery_e2e.py             # calibrate once, both tasks restore it
```

See [`tests/README.md`](tests/README.md) for what each test checks.

### Checking a real session

The automated tests use a synthetic camera with no face in it. They prove the
data path works, that failures are reported rather than hidden, and that
calibration persists across pages — but they cannot tell you whether the tracker
is *accurate*. For that, run the demo yourself with a real webcam, calibrate
properly, then stop the server and run:

```bash
python tools/check_live_session.py
```

It grades the most recent participant and names anything that looks wrong: the
tracker not starting, the task page falling back to an uncalibrated model,
calibration skipped, too few samples, a webcam that rarely saw a face, gaze that
never moved, duplicate frames, or coordinates on a no-face sample.

### Watching the scan path

[`tools/gaze_visualizer.html`](tools/gaze_visualizer.html) replays recorded
sessions. Open the file in a browser (no server needed), drop in the
`all_apps_wide-...csv` downloaded from oTree's Data page, and pick a
participant and task. It plays the scan path in real time — scrub, change
speed, watch the gaze land in the recorded regions of interest. No-face
stretches play as honest gaps, samples clipped at the screen edge draw as
rings, and everything stays on your machine: the file is read locally by the
page.

`python tests/test_visualizer.py` drives it headlessly against a real export.

## Production deployment

<details>
<summary>Click to expand</summary>

`otree devserver` is fine for local testing. For a live study:

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

**No third-party requests.** The library, the gaze model, and MediaPipe's
face detector are all served from `/static/`. A participant's browser never
contacts an external host, which matters both for reliability and because
contacting one would disclose participants' IP addresses to it. Verify with
`python tests/test_offline.py`, which blocks every external host and asserts
the tracker still works. Refresh the vendored assets with
[`tools/fetch_mediapipe_assets.sh`](tools/fetch_mediapipe_assets.sh)
(and `--check` to verify their checksums).

**Heroku-style hosts.** The included [Procfile](Procfile) starts
`otree prodserver $PORT`. Run `otree resetdb --noinput` once after deploy.
Do not launch `otree.asgi:app` with uvicorn directly: oTree's own commands run
a setup step (participant fields, currency, database checks) that a bare ASGI
import skips, and what breaks first is silent — participant fields stop
persisting.

**oTree Hub.** Supported. The gaze model is served from `/static/`, which
oTree serves everywhere, so no custom server is needed.

**Data volume.** At about 30 samples per second a 5-minute task produces
roughly 9,000 samples per participant, around 1.5–2 MB of JSON per row.
Postgres handles this easily; size the instance accordingly for studies
with many participants.

</details>

## Caveats

- **Webcam-grade accuracy.** This is not a research-grade eye tracker.
  Calibration error is reported in pixels and is useful for screening,
  but expect substantial noise.
- **No fabricated data.** If the tracker cannot start, it says so
  (`eyetrack_init_status` is `init_failed` or `no_consent`) and records
  nothing. A frame in which no face was seen is stored with empty
  coordinates, not as a fixation at the centre of the screen. Nothing in
  the exported data is synthetic.
- **Participants can skip calibration.** Someone the webcam cannot see is
  offered a way past the calibration page rather than being stranded on it.
  Those rows have an empty `eyetrack_calibration_rmse` and gaze from an
  uncalibrated model. Decide up front whether to exclude them.
- **Client-trusted fields.** All `eyetrack_*` fields are written by the
  participant's browser. A determined participant could spoof them.
  Treat them as quality hints rather than ground truth.

## How it works

The library used here, [WebEyeTrack](https://github.com/RedForestAI/WebEyeTrack),
runs entirely in the browser and only sends the gaze coordinates back to
the server, not the video. Gaze samples are collected in the browser and
posted to the server with the rest of the form data — no streaming server
required.

### The eye-tracking library is a patched build

This project does not use WebEyeTrack off the shelf. It builds the library
from a **pinned upstream commit plus a small patch series**, because the
stock library cannot do what a research instrument needs:

- Its personalisation step (`adapt()`) lives in a Web Worker and is not
  exposed, so a calibration cannot be applied deliberately or carried from
  the calibration page to the task page. The patches expose it and persist
  the calibrated model across pages.
- Its model and asset URLs are hardcoded to a path oTree does not serve and
  to two third-party CDNs. The patches make them configurable, so everything
  is served from `/static/` and no participant's browser contacts an external
  host.
- Its build does not compile on a clean checkout. One patch fixes that.

The source is pinned in
[`vendor/webeyetrack/UPSTREAM`](vendor/webeyetrack/UPSTREAM), the exact
changes are in [`vendor/webeyetrack/patches/`](vendor/webeyetrack/patches/),
and the whole thing is reproducible:

```bash
tools/build_webeyetrack.sh          # fetch pinned source, apply patches, build
tools/build_webeyetrack.sh --check  # assert the committed bundle matches, byte for byte
```

An unpatched build of the pinned commit is byte-identical to the published
`webeyetrack@0.0.2` on npm, so `--check` is a genuine supply-chain assertion:
the bundle this repository serves is exactly that source plus those patches and
nothing else. See
[`_static/webeyetrack/VENDOR.md`](_static/webeyetrack/VENDOR.md) for details.

The patches are written to be submittable upstream, but the project does not
depend on them being accepted — the pin and the patch series stand on their own.

## Credits

- Eye-tracking library:
  [WebEyeTrack](https://github.com/RedForestAI/WebEyeTrack) by Davalos et al.
  (Vanderbilt University, Trinity University, and St. Mary's University),
  [arXiv:2508.19544](https://arxiv.org/abs/2508.19544)
- Experiment framework: [oTree](https://www.otree.org/)

If you use this in published research, please cite both this repository
(see [`CITATION.cff`](CITATION.cff)) and the upstream WebEyeTrack project. For
reproducibility, report the pinned WebEyeTrack commit
(`vendor/webeyetrack/UPSTREAM`) so others can rebuild the exact library you ran.

## License

TDG-Attribution-NonCommercial-ShareAlike (UCLA Academic Software License).
Free for academic and non-profit research use with attribution; redistribution
must keep this license. **Commercial use is not permitted** — contact
software@tdg.ucla.edu for commercial licensing. See [LICENSE](LICENSE) for full
terms.
