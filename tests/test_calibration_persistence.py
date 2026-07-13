"""
End-to-end check that a calibration performed on one page reaches the next.

This is the property the whole eye-tracking integration rests on. WebEyeTrack
personalises its gaze model in place, inside a Web Worker, and every oTree page
is a full document load — so the worker, and with it the calibration, is
destroyed on navigation. The vendored build persists the personalised model to
IndexedDB under a per-participant key and restores it on later pages.

Chromium's synthetic camera contains no face, so `calibrate()` cannot adapt the
model here; what this test pins down is the save/restore round trip across a
real page navigation, which is the part that used to be missing entirely.

Setup:
    pip install playwright && python -m playwright install chromium

Run:
    otree devserver            # in one terminal
    python tests/test_calibration_persistence.py
"""

from __future__ import annotations

import re
import sys

BASE_URL = "http://localhost:8000"

RESTORED = "restored a calibrated model"
FELL_BACK = "falling back to the base model"


def run() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed; skipping", file=sys.stderr)
        return 0

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
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
            ],
        )
        context = browser.new_context(permissions=["camera"])
        page = context.new_page()

        logs: list[str] = []
        page.on("console", lambda m: logs.append(m.text))

        # Consent
        page.goto(f"{BASE_URL}/demo/mpl_risk")
        page.wait_for_url(re.compile(r"/SessionStartLinks/"), timeout=15_000)
        match = re.search(r"/InitializeParticipant/[A-Za-z0-9_-]+", page.content())
        assert match, "no participant link"
        page.goto(BASE_URL + match.group(0))
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("#test-camera-btn", timeout=10_000)
        page.click("#test-camera-btn")
        page.wait_for_selector("#next-section:not(.hidden)", timeout=10_000)
        page.click("button[type='submit'], .otree-btn-next, button:has-text('Next')")
        page.wait_for_load_state("networkidle")

        # Calibration page: start the tracker, wait for the model, then persist it.
        print("\n[1/3] Calibration page — save the model")
        page.locator("#loading-overlay").wait_for(state="hidden", timeout=45_000)
        page.click("#start-calibration-btn")
        page.wait_for_selector(".calibration-point.active", timeout=30_000)

        # Nothing has been calibrated (no face), but the save/restore path is
        # independent of whether adapt() ran.
        key = page.evaluate("js_vars.calibration_key")
        assert_(bool(key), f"calibration key derived from the participant ({key!r})")

        page.evaluate("gazeTracker.saveCalibration(js_vars.calibration_key)")
        page.wait_for_function(
            "() => window.indexedDB.databases().then(dbs => dbs.some(d => d.name === 'tensorflowjs'))",
            timeout=15_000,
        )
        assert_(True, "model written to IndexedDB")

        # No face in the synthetic stream, so calibration cannot complete. Take
        # the escape route, which only appears after repeated failed attempts.
        for _ in range(3):
            page.click(".calibration-point.active", force=True)
            page.wait_for_timeout(400)
        page.wait_for_selector("#calibration-escape:not(.hidden)", timeout=10_000)
        page.click("#skip-calibration-btn")
        page.wait_for_selector("#proceed:not(.hidden)", timeout=10_000)

        print("\n[2/3] Navigate to the Decision page")
        logs.clear()
        page.click("button[type='submit'], .otree-btn-next, button:has-text('Next')")
        page.wait_for_load_state("networkidle")
        # Wait for the worker to finish loading whichever model it chose.
        page.wait_for_function("() => tracker.initStatus !== 'unknown'", timeout=45_000)
        page.wait_for_timeout(1000)

        print("\n[3/3] The Decision page restored the saved model")
        joined = "\n".join(logs)
        assert_(
            RESTORED in joined,
            "the worker restored the persisted model across the page navigation",
        )
        assert_(
            FELL_BACK not in joined,
            "it did not silently fall back to the uncalibrated base model",
        )
        assert_(
            key in joined,
            f"restored under this participant's key ({key!r})",
        )

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
