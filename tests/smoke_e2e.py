"""
End-to-end smoke test: Consent → Calibration → Decision → Results.

Drives the four pages with a headless Chromium configured to auto-grant the
camera permission and feed a synthetic video stream (Chromium's
`--use-fake-device-for-media-stream`). WebEyeTrack still runs against the
fake stream — gaze samples will be near-deterministic but the *shape* of
the data flow is what we're verifying.

Setup (one-time):

    pip install playwright pytest
    python -m playwright install chromium

Run:

    # Start the dev server in another terminal (no resetdb -- devserver
    # manages its own database and rejects one that resetdb created):
    otree devserver

    # Then:
    python tests/smoke_e2e.py
    # or with pytest:
    python -m pytest tests/smoke_e2e.py -s

What this asserts:
  * Consent page accepts the fake camera and reveals the Next button.
  * Calibration page loads the vendored WebEyeTrack bundle and its gaze model
    from /static/ (no console errors about the model failing to load).
  * Decision page shows the expected currency formatting (no `€€` doubling).
  * Results page renders a single euro symbol per amount.

What this does NOT assert (see tests/README.md): Chromium's synthetic camera
has no face in it, so every gaze sample comes back `gaze_state: 'closed'` at
screen centre. Calibration accuracy and gaze quality cannot be checked here.
"""

from __future__ import annotations

import re
import sys
import time

BASE_URL = "http://localhost:8000"


def run() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "playwright not installed. Install with:\n"
            "    pip install playwright\n"
            "    python -m playwright install chromium",
            file=sys.stderr,
        )
        return 2

    failures: list[str] = []

    def assert_(cond: bool, msg: str) -> None:
        if not cond:
            failures.append(msg)
            print(f"  FAIL {msg}")
        else:
            print(f"  ok   {msg}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--use-fake-ui-for-media-stream",  # auto-grants camera permission
                "--use-fake-device-for-media-stream",  # synthetic video source
            ],
        )
        context = browser.new_context(
            permissions=["camera"],
            ignore_https_errors=True,
        )
        page = context.new_page()

        console_errors: list[str] = []
        page.on("pageerror", lambda exc: console_errors.append(str(exc)))
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text)
            if msg.type == "error"
            else None,
        )

        # 1. Create a demo session. /demo/mpl_risk redirects to the admin
        # SessionStartLinks page; we scrape a participant init URL from
        # there and follow it.
        print("\n[1/5] Open demo session")
        page.goto(f"{BASE_URL}/demo/mpl_risk")
        page.wait_for_url(re.compile(r"/SessionStartLinks/"), timeout=15_000)
        body = page.content()
        match = re.search(r"/InitializeParticipant/[A-Za-z0-9_-]+", body)
        if not match:
            failures.append("could not find a participant link on SessionStartLinks page")
            print("  FAIL: no participant link found")
            return 1
        page.goto(BASE_URL + match.group(0))
        page.wait_for_load_state("networkidle")

        # 2. Consent page.
        print("\n[2/5] Consent page")
        page.wait_for_selector("#test-camera-btn", timeout=10_000)
        page.click("#test-camera-btn")
        page.wait_for_selector("#next-section:not(.hidden)", timeout=10_000)
        consent_value = page.evaluate(
            "document.getElementById('eyetrack_consent').value"
        )
        assert_(consent_value == "1", f"eyetrack_consent input set to '1' (got {consent_value!r})")

        # Continue to calibration.
        page.click("button[type='submit'], .otree-btn-next, button:has-text('Next')")
        page.wait_for_load_state("networkidle")

        # 3. Calibration page.
        print("\n[3/5] Calibration page")
        # Loading overlay should clear once WebEyeTrack is ready (it gets the
        # `.hidden` class -> display:none).
        try:
            page.locator("#loading-overlay").wait_for(state="hidden", timeout=45_000)
        except Exception:
            overlay_text = page.evaluate(
                "document.getElementById('loading-overlay')?.innerText"
            )
            print(f"  Loading overlay never hid; current content: {overlay_text!r}")
            console_dump = "\n    ".join(console_errors[-10:])
            print(f"  Recent console errors:\n    {console_dump}")
            raise
        page.click("#start-calibration-btn")

        # Chromium's synthetic camera shows a test pattern with no face in it, so
        # the tracker has no gaze reading to pair with the dot. Calibration MUST
        # refuse rather than adapt the model to a fabricated centre-screen gaze.
        # Clicking the dot repeatedly must not advance the sequence.
        #
        # The dot has a CSS pulse animation, so Playwright's "element stable"
        # check never settles; force=True bypasses it.
        page.wait_for_selector(".calibration-point.active", timeout=10_000)

        # Which dot is active, by position in the sequence. Do not compare
        # bounding boxes: the active dot has a CSS pulse animation, so its box
        # legitimately changes between reads.
        active_index = (
            "Array.from(document.querySelectorAll('.calibration-point'))"
            ".findIndex(d => d.classList.contains('active'))"
        )
        assert_(page.evaluate(active_index) == 0, "calibration starts on the first dot")

        for _ in range(3):
            page.click(".calibration-point.active", force=True)
            time.sleep(0.4)

        hint = (page.text_content("#calibration-live-hint") or "").strip()
        assert_("Face not detected" in hint, f"no-face hint shown (got {hint!r})")

        assert_(
            page.evaluate(active_index) == 0,
            "the dot must not advance when no face was seen",
        )
        assert_(
            page.locator(".calibration-point.clicked").count() == 0,
            "no point may be recorded without a gaze reading",
        )

        # With no face there is no way to finish, so the page must offer a way
        # out. Nothing else on this page can move the participant forward.
        page.wait_for_selector("#calibration-escape:not(.hidden)", timeout=10_000)
        assert_(True, "escape route offered after repeated no-face attempts")
        page.click("#skip-calibration-btn")

        page.wait_for_selector("#proceed:not(.hidden)", timeout=10_000)
        assert_(True, "participant can proceed after skipping calibration")

        page.click("button[type='submit'], .otree-btn-next, button:has-text('Next')")
        page.wait_for_load_state("networkidle")

        # 4. Decision page — check no currency doubling, then fill form.
        print("\n[4/5] Decision page")
        body = page.content()
        assert_("€€" not in body, "no '€€' double-print in Decision body")

        # Pick option A (radio value 1) for every row.
        for i in range(1, 11):
            page.click(f"input[name='choice_{i}'][value='1']")
        page.wait_for_timeout(1500)

        # The gaze data path must actually carry data. The model loaded (the
        # console check above would have caught a 404), so samples must flow.
        status = page.evaluate("tracker.initStatus")
        assert_(status == "ok", f"tracker reports init_status 'ok' (got {status!r})")

        n_samples = page.evaluate("tracker.allSamples.length")
        assert_(n_samples > 0, f"gaze samples were collected (got {n_samples})")

        # No face in the synthetic stream, so every sample must carry null
        # coordinates rather than a fabricated fixation at the screen centre.
        centre_fixations = page.evaluate(
            "tracker.allSamples.filter(s => s.gaze_state !== 'open' && s.x !== null).length"
        )
        assert_(
            centre_fixations == 0,
            f"no-face samples must have null coordinates (got {centre_fixations} with coordinates)",
        )

        # Duplicate camera frames must be collapsed.
        distinct_frames = page.evaluate(
            "new Set(tracker.allSamples.map(s => s.frame_time)).size"
        )
        assert_(
            distinct_frames == n_samples,
            f"one sample per camera frame ({n_samples} samples, {distinct_frames} frames)",
        )

        # Submit.
        page.click("button[type='submit'], .otree-btn-next, button:has-text('Next')")
        page.wait_for_load_state("networkidle")

        # 5. Results page — currency rendering check.
        print("\n[5/5] Results page")
        body = page.content()
        euro_count = body.count("€€")
        assert_(euro_count == 0, f"no '€€' double-print on Results (saw {euro_count})")
        assert_(re.search(r"€\d", body) is not None, "Results page contains a Euro amount")

        # Console-error sanity. Only MediaPipe's own INFO/WARN chatter, which it
        # routes through console.error during XNNPACK / GL initialization, is
        # benign. Do NOT whitelist "WebEyeTrack", "404", or "init_failed": those
        # are exactly the strings a broken model mount emits, and filtering them
        # is how this test used to pass while the tracker recorded nothing.
        benign_substrings = (
            "TensorFlow Lite",
            "XNNPACK",
            "gl_context",
            "face_landmarker_graph",
        )
        unexpected = [
            e for e in console_errors
            if not any(s in e for s in benign_substrings)
        ]
        assert_(len(unexpected) == 0, f"no unexpected console errors (got {unexpected})")

        browser.close()

    print()
    if failures:
        print(f"FAILED ({len(failures)})")
        for f in failures:
            print("  -", f)
        return 1
    print("ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(run())
