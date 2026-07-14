# Webcam eye tracking in oTree — a walkthrough

A guided tour, written to be followed live: run the demos, be a participant,
inspect the data, then add tracking to your own task. Every command you need
is included, in order.

## What this is

Eye tracking usually means a lab, a chin rest, and hardware. This runs in the
participant's own browser using their webcam. The video never leaves their
machine — a neural network in the browser estimates where on the screen they
are looking, and only those gaze coordinates are posted back with the rest of
the oTree form data.

No third-party servers are contacted at any point: the tracking library, its
models, everything ships with this project and is served by your own oTree
server. That matters for reliability, and it matters for your ethics protocol —
no participant's IP address is disclosed to Google or a CDN. You can prove it:
`python tests/test_offline.py` blocks every outside host and shows the tracker
still works.

It is webcam-grade, not lab-grade: roughly 20–30 gaze samples per second, and
accuracy of a few percent of the screen with a careful calibration. That is
enough to tell which *region* of the screen someone is looking at — which
column of a price list, which cell of a payoff matrix — not which word.

## Step 1 — Get it running

```bash
# get the project
git clone https://github.com/kiante-fernandez/otree-et
cd otree-et

# a clean Python environment (either one)
python -m venv venv && source venv/bin/activate
# or: conda env create -f environment.yml && conda activate otree-env

# install oTree
pip install -r requirements.txt

# start the development server  (do NOT run "otree resetdb" first --
# devserver manages its own database and rejects one made by resetdb)
otree devserver
```

Open the demo page:

```bash
open http://localhost:8000/demo        # macOS; elsewhere just open the URL
```

Three sessions are listed: a multiple price list, a Prisoner's Dilemma on a
payoff matrix, and both tasks in one session. They are ordinary oTree apps —
tasks you already know — with tracking added.

## Step 2 — Be a participant

Pick **"Both tasks in one session"** and go through it yourself. Three stages:

**Consent.** The participant is told what happens — camera images processed
only in the browser, only screen coordinates recorded — and tests their
camera. No consent, no tracking; the task still runs and the data records
`no_consent` honestly.

**Calibration.** Nine red dots, one at a time: look at the dot, click it. The
first five teach the model your eyes; the last four are held out to *measure*
the error. That distinction is why the number on the completion screen means
something — it is accuracy on points the model never saw, reported in pixels
and as a fraction of your screen. Under 6% of the screen diagonal is good;
under 12% usable. If the camera cannot see your face, the dot refuses to
advance and says why; if it is hopeless there is an escape hatch, and the skip
is recorded in the data.

**The tasks.** A faint red dot follows your gaze while you make ordinary oTree
decisions. The part that is easy to miss: calibration happened on a different
page, in a different app — and it followed you. The calibrated model is stored
in the participant's browser under their participant code, and every tracked
page restores it. Calibrate once, track everywhere — across every task in the
session.

## Step 3 — Look at the data

If you are running `otree devserver`, **stop it first** (`Ctrl+C`) — devserver
holds the database in memory and writes it to disk on exit. (`otree
prodserver` keeps it on disk, so with prodserver you can skip the stop.) Then:

```bash
# a referee report on the session you just ran: tracker started? calibration
# restored? error acceptable? enough samples? face visible most of the time?
python tools/check_live_session.py

# grade every participant, not just the most recent
python tools/check_live_session.py --all
```

For the raw files, restart the server and open the Data page at
<http://localhost:8000/export>, or pull the wide file directly:

```bash
curl -s "http://localhost:8000/ExportWide" -o all_apps_wide.csv
```

Two exports matter:

- **The wide CSV** (`all_apps_wide-...csv`): one row per participant. Each
  tracked task carries the gaze samples as JSON plus the honesty fields — did
  the tracker start (`eyetrack_init_status`), was this participant's
  calibration actually restored on this page
  (`eyetrack_calibration_restored`), how big was their screen
  (`eyetrack_viewport_*`), and the held-out calibration error.
- **Each task's custom export** (linked next to the app on the Data page):
  one row per gaze sample — coordinates, whether a face was visible, whether
  the estimate was clipped at the screen edge, two clocks — labeled with the
  app and page it came from. This is the file you analyze.

Now watch a session:

```bash
open tools/gaze_visualizer.html        # or double-click the file
```

Drop the wide CSV onto the page, pick a participant and task, press play. The
scan path replays in real time on the participant's actual screen dimensions,
with the recorded regions of interest overlaid exactly where they sat.
Stretches where the webcam lost the face play as gaps, not invented lines;
estimates pinned to the screen edge draw as rings. Space plays and pauses,
arrows switch task, shift+arrows switch participant, and the timeline scrubs.
The file is read locally by the page; nothing is uploaded anywhere.

For the skeptics, the test suite:

```bash
# fast checks, about a second total
python -m pytest tests/
node --test tests/js/*.test.mjs

# prove the committed tracking library is exactly its pinned source + patches
tools/build_webeyetrack.sh --check
tools/fetch_mediapipe_assets.sh --check

# browser tests (one-time setup, then run with a server up in another terminal)
pip install playwright && python -m playwright install chromium
otree devserver                                   # terminal 1
python tests/smoke_e2e.py                         # terminal 2, then:
python tests/test_calibration_flow.py             # all nine dots to completion
python tests/test_calibration_persistence.py      # calibration survives the page change
python tests/test_offline.py                      # works with every outside host blocked
python tests/test_matrix_e2e.py                   # second task; data really persisted
python tests/test_battery_e2e.py                  # one calibration, both tasks restore it
python tests/test_visualizer.py                   # the replay tool, headless
```

## Step 4 — Add it to your own task

Your task stays a plain oTree app. Four additions; `matrix_game/` is the
worked example to copy from.

**4a. `settings.py`** — run the shared consent+calibration app first, and
declare the participant fields it writes:

```python
SESSION_CONFIGS = [
    dict(name='my_study', num_demo_participants=1,
         app_sequence=['eyetrack', 'my_task']),
]

PARTICIPANT_FIELDS = [
    'eyetrack_consent',
    'eyetrack_calibration_rmse',
    'eyetrack_calibration_rmse_fraction',
]
```

**4b. Your task's `__init__.py`** — paste the field block onto `Player`, wire
the tracked Page, delegate the export:

```python
from eyetrack_shared import EYETRACK_FORM_FIELDS, eyetrack_js_vars, gaze_rows

class Player(BasePlayer):
    # ... your task's own fields ...

    eyetrack_sample_count = models.IntegerField(initial=0)
    eyetrack_gaze_data = models.LongStringField(blank=True)
    eyetrack_init_status = models.StringField(initial='unknown')
    eyetrack_calibration_restored = models.BooleanField(initial=False)
    eyetrack_viewport_width = models.IntegerField(initial=0)
    eyetrack_viewport_height = models.IntegerField(initial=0)
    eyetrack_viewport_changed = models.BooleanField(initial=False)
    eyetrack_rois = models.LongStringField(blank=True)
    eyetrack_runtime_error = models.LongStringField(blank=True)


class Decision(Page):
    form_model = 'player'
    form_fields = ['your_task_field'] + EYETRACK_FORM_FIELDS

    @staticmethod
    def js_vars(player):
        return eyetrack_js_vars(player)


def custom_export(players):
    yield from gaze_rows(players, 'my_task', 'Decision')
```

**4c. The tracked page's template** — three elements, one include, and ROI
tags on whatever your analysis cares about:

```html
{{ block content }}

<div id="tracking-status" class="status-inactive">Eye tracking: initializing...</div>
<div id="gaze-dot"></div>
<video id="webcam-video" autoplay playsinline muted></video>

<!-- your task's content; tag the regions that matter: -->
<td data-eyetrack-roi="option-a">{{ C.SAFE_AMOUNT }}</td>
<td data-eyetrack-roi="option-b">{{ C.LOTTERY }}</td>

{{ next_button }}

{{ include 'eyetrack/tracked_page.html' }}

{{ endblock }}
```

Anything carrying `data-eyetrack-roi="name"` has its on-screen rectangle
recorded alongside the gaze samples — re-captured if the participant scrolls
or resizes — so fixations can be assigned to cells, rows, or options offline.

**4d. Run it** exactly like the demos:

```bash
otree devserver
open http://localhost:8000/demo
```

## Step 5 — What the pipeline promises about the data

This is what separates usable data from plausible-looking garbage, and it is
worth a slide of its own. The pipeline never fabricates:

- If the tracker fails, the data says so instead of inventing samples.
- A frame where no face was visible has *empty* coordinates — never a fake
  fixation at the centre of the screen.
- An estimate pinned to the screen edge is flagged `clipped`: the person was
  looking further out, and the value is censored, not measured.
- Every tracked page records whether it used *this participant's* calibration
  or silently fell back to an uncalibrated model.

So every analysis starts with the same filter — keep only rows where:

```
eyetrack_init_status == 'ok'
eyetrack_calibration_restored == True
eyetrack_calibration_rmse_fraction <= 0.12    # your threshold; lower is stricter
```

Compare calibration error across participants **as a fraction of the screen**,
never in raw pixels: 265 px is a fifth of a laptop window and a twelfth of a
large monitor.

Two properties to respect in analysis: vertical accuracy is much worse than
horizontal (a webcam sees little vertical eye movement), so design regions of
interest as columns and cells, not thin rows; and samples pass through a
smoothing filter, so they are autocorrelated — a time series, not independent
draws.

## Step 6 — Going live

```bash
# environment: copy the template and fill it in
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(50))"   # -> OTREE_SECRET_KEY

# production server (what the Procfile runs). Never launch otree.asgi with
# uvicorn directly: oTree's own commands run a setup step that a bare ASGI
# import skips, and participant fields silently stop persisting.
otree resetdb --noinput        # once, on the production machine
otree prodserver 8000
```

HTTPS is required in front of the server — browsers only allow camera access
on secure origins. oTree Hub works. Expect roughly 1–2 MB of gaze data per
participant per five minutes of tracking.

Before a real study, run one careful session yourself and hold it to the
standard you will hold participants to:

```bash
python tools/check_live_session.py
```
