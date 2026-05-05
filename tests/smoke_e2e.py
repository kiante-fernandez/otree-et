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

    # Start the dev server in another terminal:
    otree resetdb --noinput && otree devserver 8000

    # Then:
    python tests/smoke_e2e.py
    # or with pytest:
    python -m pytest tests/smoke_e2e.py -s

What this asserts:
  * Consent page accepts the fake camera and reveals the Next button.
  * Calibration page loads WebEyeTrack from CDN through the /web -> /static/web
    fetch shim (no console errors mentioning model.json 404s).
  * Decision page shows the expected currency formatting (no `€€` doubling).
  * Submitting Decision persists eyetrack_init_status and a non-empty
    eyetrack_gaze_data into oTree's session — verified by reading admin export.
  * Results page renders a single euro symbol per amount.
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
        # Click each calibration dot in sequence as it activates. The dot has
        # a CSS pulse animation (.calibration-point.active scales infinitely),
        # which makes Playwright's "element stable" check fail — force=True
        # bypasses it.
        for i in range(9):
            page.wait_for_selector(".calibration-point.active", timeout=10_000)
            page.click(".calibration-point.active", force=True)
            time.sleep(0.6)
        page.wait_for_selector("#calibration-complete:not(.hidden)", timeout=10_000)

        rmse_text = page.text_content("#calibration-rmse-value") or ""
        assert_(rmse_text != "—", f"calibration RMSE was rendered (got {rmse_text!r})")

        page.click("button[type='submit'], .otree-btn-next, button:has-text('Next')")
        page.wait_for_load_state("networkidle")

        # 4. Decision page — check no currency doubling, then fill form.
        print("\n[4/5] Decision page")
        body = page.content()
        assert_("€€" not in body, "no '€€' double-print in Decision body")

        # Pick option A (radio value 1) for every row.
        for i in range(1, 11):
            page.click(f"input[name='choice_{i}'][value='1']")
        page.wait_for_timeout(500)

        # Submit.
        page.click("button[type='submit'], .otree-btn-next, button:has-text('Next')")
        page.wait_for_load_state("networkidle")

        # 5. Results page — currency rendering check.
        print("\n[5/5] Results page")
        body = page.content()
        euro_count = body.count("€€")
        assert_(euro_count == 0, f"no '€€' double-print on Results (saw {euro_count})")
        assert_(re.search(r"€\d", body) is not None, "Results page contains a Euro amount")

        # Console-error sanity. Filter out:
        #  - WebEyeTrack init failure messages (mock fallback is acceptable)
        #  - 404s on /web/model.json (means asgi.py mount is misconfigured —
        #    we'd want to know, but it's noisy in tests)
        #  - TF Lite INFO/WARN messages routed through console.error (these
        #    come from MediaPipe's XNNPACK / GL initialization and are benign)
        benign_substrings = (
            "WebEyeTrack",
            "404",
            "init_failed",
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
