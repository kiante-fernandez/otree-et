# Adding WebEyeTrack Eye Tracking to oTree 5+

This project demonstrates webcam-based eye tracking in an oTree experiment using the WebEyeTrack library.

## Table of Contents

1. [Installation](#installation)
2. [Why Not `otree devserver`?](#why-not-otree-devserver)
3. [oTree Hub Compatibility](#otree-hub-compatibility)
4. [Architecture](#architecture)
5. [Project Structure](#project-structure)
6. [Running the Server](#running-the-server)
7. [Data Storage](#data-storage)
8. [Common Issues](#common-issues)
9. [Step-by-Step Guide: Adding to Any oTree Project](#step-by-step-guide-adding-to-any-otree-project)

---

## Installation

### Prerequisites

- Python 3.8+
- pip or conda

### Install Dependencies

**Option 1: Using conda (recommended)**

```bash
# Create environment from environment.yml
conda env create -f environment.yml

# Activate
conda activate otree-env
```

**Option 2: Using pip**

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install requirements
pip install -r requirements.txt
```

### Required Packages

The `requirements.txt` includes:

| Package | Purpose |
|---------|---------|
| `otree>=5.0` | oTree framework |
| `uvicorn[standard]` | ASGI server for custom routing |
| `starlette` | Custom route handling in asgi.py |

### Initialize Database

```bash
otree resetdb --noinput
```

---

## Why Not `otree devserver`?

**The Problem:** oTree 5+ completely ignores Django's URL routing system.

When you run `otree devserver`, it starts oTree's internal Starlette ASGI server. This server:
- Only knows about oTree's built-in routes (pages, admin, static files)
- Does NOT read `ROOT_URLCONF` or any `urls.py` file
- Provides NO mechanism to register custom endpoints

**What we needed:**
- Custom endpoints (`/record_gaze/`, `/record_event/`) to receive gaze data in real-time
- A way to serve WebEyeTrack model files from `/web/`

**The Solution:**
We created a custom ASGI wrapper (`asgi.py`) that:
1. Intercepts incoming requests
2. Routes custom paths to our Starlette handlers
3. Passes everything else to oTree's ASGI app

This requires running `uvicorn asgi:application` instead of `otree devserver`.

### Key Discovery

oTree 5+ uses **Starlette ASGI routing**, NOT Django URL routing. The `ROOT_URLCONF` setting is completely ignored. This means:
- Adding URLs to `urls.py` does NOT work
- Custom endpoints return 404
- You must use a custom ASGI wrapper

---

## oTree Hub Compatibility

### What Works on oTree Hub

| Feature | Works? | Why |
|---------|--------|-----|
| Eye tracking in browser | Yes | WebEyeTrack runs client-side via CDN |
| Gaze data in oTree CSV | Yes | Uses standard form submission |
| Calibration page | Yes | Standard oTree page |
| Real-time NDJSON backup | No | Custom endpoints don't exist |

### What Happens on oTree Hub

When deployed to oTree Hub:
1. The custom ASGI wrapper is NOT used (oTree Hub runs standard oTree)
2. `/record_gaze/` and `/record_event/` endpoints return 404
3. Browser console shows errors for failed POST requests
4. **BUT gaze data is still saved** via form submission to `eyetrack_gaze_data`

### The Data is Safe

We implemented **dual storage** intentionally:

| Storage | Location | Works on oTree Hub? |
|---------|----------|---------------------|
| Primary | `eyetrack_gaze_data` field (form submission) | Yes |
| Backup | NDJSON files via `/record_gaze/` | No |

On oTree Hub, you lose the real-time backup but **keep all the data** in the oTree database.

### Recommendation

- **Self-hosted:** Use `uvicorn asgi:application` for real-time backup
- **oTree Hub:** Works fine, just ignore console errors for `/record_gaze/`

---

## Architecture

```
Browser                         Server
   |                               |
   |  POST /record_gaze/          |
   | ---------------------------->| Custom ASGI Wrapper (asgi.py)
   |                               |   |-- /web/* -> StaticFiles
   |  GET /web/model.json         |   |-- /record_gaze/ -> Starlette endpoint
   | ---------------------------->|   |-- /record_event/ -> Starlette endpoint
   |                               |   +-- /* -> oTree app
```

**Page Flow:** Consent -> Calibration -> Decision (tracked) -> Results

---

## Project Structure

```
mpl_risk/
├── asgi.py                        # ASGI wrapper - routes gaze endpoints
├── settings.py                    # oTree settings
├── requirements.txt               # pip dependencies
├── environment.yml                # conda environment
├── Procfile                       # Heroku deployment (uses uvicorn)
├── _templates/
│   └── global/
│       └── Page.html              # Base template (includes otai-utils.js)
├── _static/
│   ├── otai-utils.js              # DOM utilities (docQuerySelectorStrict)
│   ├── styles.css                 # CSS styles
│   ├── webeyetrack-loader.js      # WebEyeTrack ES module loader
│   └── web/
│       ├── model.json             # TensorFlow.js model
│       └── group1-shard1of1.bin   # Model weights
├── mpl_risk/
│   ├── __init__.py                # oTree app (Player model, Pages)
│   ├── Consent.html               # Camera consent page
│   ├── consent.js                 # Camera permission logic
│   ├── Calibration.html           # 9-point calibration page
│   ├── calibration.js             # Calibration logic
│   ├── Decision.html              # MPL task with eye tracking
│   ├── gaze_tracker.js            # SimpleGazeTracker class
│   └── Results.html               # Results page
└── gaze_data/                     # NDJSON backup files (created at runtime)
```

---

## Running the Server

### Self-Hosted (Recommended)

```bash
# Activate environment
source venv/bin/activate  # or: conda activate otree-env

# Install dependencies (first time only)
pip install -r requirements.txt

# Reset database (required after model changes)
otree resetdb --noinput

# Start server with custom ASGI wrapper
uvicorn asgi:application --reload --port 8000
```

### oTree Hub

Upload normally. The eye tracking will work, but you'll see console errors for `/record_gaze/` (which can be ignored).

### Why NOT `otree devserver`?

`otree devserver` starts oTree's built-in server which doesn't know about our custom routes. The custom ASGI wrapper in `asgi.py` intercepts requests and routes them appropriately.

---

## Data Storage

Gaze data is stored in two places:

1. **oTree Database** - `eyetrack_gaze_data` field (JSON array) exported with CSV
2. **NDJSON Files** - `gaze_data/{participant}/{session}.ndjson` backup (self-hosted only)

### Sample Format

```json
{
  "x": 756.5,
  "y": 412.3,
  "norm_x": 0.1,
  "norm_y": -0.05,
  "gaze_state": "open",
  "confidence": 0.9,
  "t_perf": 12345.67
}
```

---

## Common Issues

| Issue | Solution |
|-------|----------|
| 404 for /record_gaze/ | Use `uvicorn asgi:application`, not `otree devserver` |
| Database readonly error | `pkill -f uvicorn && rm db.sqlite3 && otree resetdb` |
| Gaze data not in CSV | Add field to `form_fields` in Page class |
| BooleanField not saving | Use "1"/"0" not "true"/"false" in hidden inputs |

---

## Step-by-Step Guide: Adding to Any oTree Project

### Prerequisites

- oTree 5+ project
- Webcam access (HTTPS required in production)

### Step 1: Download Required Files

**WebEyeTrack Model Files** - Download from https://github.com/RedForestAI/WebEyeTrack/tree/main/js/web:

```
_static/web/
├── model.json
└── group1-shard1of1.bin
```

**Create WebEyeTrack Loader** - `_static/webeyetrack-loader.js`:

```javascript
let WebEyeTrackModule = null;
let loadingPromise = null;

export async function loadWebEyeTrack() {
  if (WebEyeTrackModule) return WebEyeTrackModule;
  if (loadingPromise) return loadingPromise;

  loadingPromise = (async () => {
    const module = await import('https://esm.sh/webeyetrack');
    let WebcamClient = module.WebcamClient;
    let WebEyeTrackProxy = module.WebEyeTrackProxy;

    if (!WebcamClient && module.default) {
      WebcamClient = module.default.WebcamClient;
      WebEyeTrackProxy = module.default.WebEyeTrackProxy;
    }

    WebEyeTrackModule = { WebcamClient, WebEyeTrackProxy };
    window.WebEyeTrack = WebEyeTrackModule;
    return WebEyeTrackModule;
  })();

  return loadingPromise;
}
```

### Step 2: Add Player Model Fields

In your app's `__init__.py`:

```python
class Player(BasePlayer):
    # Your existing fields...

    # Eye tracking fields
    eyetrack_consent = models.BooleanField(initial=False)
    eyetrack_calibration_rmse = models.FloatField(blank=True)
    eyetrack_sample_count = models.IntegerField(initial=0)
    eyetrack_gaze_data = models.LongStringField(blank=True)  # JSON array
```

### Step 3: Create Consent Page

Add to your Page class:

```python
class Consent(Page):
    form_model = 'player'
    form_fields = ['eyetrack_consent']
```

In template, add camera test button and hidden input:

```html
<input type="hidden" name="eyetrack_consent" id="eyetrack_consent" value="0">
```

Set value to "1" when camera access is granted.

### Step 4: Add Tracking to Your Task Page

Template requirements:
```html
<!-- Hidden inputs for data -->
<input type="hidden" name="eyetrack_sample_count" id="eyetrack_sample_count" value="0">
<input type="hidden" name="eyetrack_gaze_data" id="eyetrack_gaze_data" value="[]">

<!-- Video element -->
<video id="webcam-video" autoplay playsinline muted></video>

<!-- Gaze visualization (optional) -->
<div id="gaze-dot"></div>

<!-- Load WebEyeTrack -->
<script type="module">
import { loadWebEyeTrack } from '{{ static "webeyetrack-loader.js" }}';
loadWebEyeTrack();
</script>

<!-- Include tracker and initialize -->
<script>{{ include_sibling 'gaze_tracker.js' }}</script>
<script>
const tracker = new SimpleGazeTracker({
    participantCode: '{{ participant.code }}',
    sessionCode: '{{ session.code }}',
    pageName: 'YourPageName',
    flushIntervalMs: 1000
});

document.addEventListener('DOMContentLoaded', async () => {
    const initialized = await tracker.init();
    if (initialized) tracker.startTracking();

    // Intercept form submission to save data
    const form = document.querySelector('form');
    if (form) {
        form.addEventListener('submit', async function(e) {
            e.preventDefault();
            await tracker.stopTracking();
            form.removeEventListener('submit', arguments.callee);
            form.submit();
        });
    }
});
</script>
```

Page class:
```python
class YourTaskPage(Page):
    form_model = 'player'
    form_fields = ['your_field_1', 'eyetrack_sample_count', 'eyetrack_gaze_data']
```

### Step 5: Create ASGI Wrapper (Self-Hosted Only)

Copy `asgi.py` from this project to your project root. Key parts:

```python
from otree.asgi import app as otree_app

class CustomASGIWrapper:
    def __init__(self):
        self.custom_app = Starlette(routes=[
            Route('/record_gaze/', record_gaze, methods=['POST']),
            Route('/record_event/', record_event, methods=['POST']),
            Mount('/web', app=StaticFiles(directory=str(STATIC_WEB_DIR)), name='web'),
        ])
        self.otree_app = otree_app

    async def __call__(self, scope, receive, send):
        path = scope.get('path', '')
        if path.startswith('/web/') or path in ['/record_gaze/', '/record_event/']:
            await self.custom_app(scope, receive, send)
        else:
            await self.otree_app(scope, receive, send)

application = CustomASGIWrapper()
```

### Step 6: Run with uvicorn

```bash
otree resetdb --noinput
uvicorn asgi:application --reload --port 8000
```

### Checklist

- [ ] Downloaded WebEyeTrack model files to `_static/web/`
- [ ] Created `_static/webeyetrack-loader.js`
- [ ] Added Player fields for eye tracking
- [ ] Created Consent page with camera test
- [ ] Added gaze_tracker.js to your app
- [ ] Added hidden inputs to tracked pages
- [ ] Added fields to `form_fields` in Page classes
- [ ] Created `asgi.py` (self-hosted only)
- [ ] Reset database after schema changes
