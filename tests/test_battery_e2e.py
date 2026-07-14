"""
The task battery, end to end: calibrate once, then two tracked tasks.

This is the claim the whole architecture makes — a calibration performed in
the shared `eyetrack` app follows the participant into every task app that
comes after it. The persistence mechanism is exercised for real: the model is
saved under the participant's key on the calibration page, and BOTH task pages
must report that they restored it, across two full app boundaries.

Chromium's synthetic camera has no face, so the model is saved unadapted and
calibration is skipped through the escape hatch; what is being verified is the
save/restore path and the two tasks running back to back on one calibration,
not gaze accuracy.

Run:
    otree prodserver 8000        # in one terminal (or otree devserver)
    python tests/test_battery_e2e.py
"""

from __future__ import annotations

import re
import sys

BASE_URL = "http://localhost:8000"

NEXT = "button[type='submit'], .otree-btn-next, button:has-text('Next')"


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
            args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"],
        )
        context = browser.new_context(permissions=["camera"])
        page = context.new_page()

        logs: list[str] = []
        page.on("console", lambda m: logs.append(m.text))

        print("\n[1/5] Consent")
        page.goto(f"{BASE_URL}/demo/task_battery")
        page.wait_for_url(re.compile(r"/SessionStartLinks/"), timeout=15_000)
        match = re.search(r"/InitializeParticipant/[A-Za-z0-9_-]+", page.content())
        assert_(match is not None, "participant link found")
        page.goto(BASE_URL + match.group(0))
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("#test-camera-btn", timeout=10_000)
        page.click("#test-camera-btn")
        page.wait_for_selector("#next-section:not(.hidden)", timeout=10_000)
        page.click(NEXT)
        page.wait_for_load_state("networkidle")

        print("\n[2/5] Calibration page: save the model under the participant's key")
        page.locator("#loading-overlay").wait_for(state="hidden", timeout=45_000)
        page.click("#start-calibration-btn")
        page.wait_for_selector(".calibration-point.active", timeout=45_000)

        key = page.evaluate("js_vars.calibration_key")
        assert_(bool(key), f"calibration key derived from the participant ({key!r})")

        page.evaluate("gazeTracker.saveCalibration(js_vars.calibration_key)")
        page.wait_for_function(
            "() => window.indexedDB.databases().then(dbs => dbs.some(d => d.name === 'tensorflowjs'))",
            timeout=15_000,
        )
        assert_(True, "model written to IndexedDB")

        # No face in the synthetic stream, so leave through the escape hatch.
        for _ in range(3):
            page.click(".calibration-point.active", force=True)
            page.wait_for_timeout(400)
        page.wait_for_selector("#calibration-escape:not(.hidden)", timeout=10_000)
        page.click("#skip-calibration-btn")
        page.wait_for_selector("#proceed:not(.hidden)", timeout=10_000)
        logs.clear()
        page.click(NEXT)
        page.wait_for_load_state("networkidle")

        print("\n[3/5] Task 1 (mpl_risk) restores the calibration")
        page.wait_for_selector("input[name='choice_1'][value='1']", timeout=30_000)
        page.wait_for_function("() => tracker.initStatus !== 'unknown'", timeout=45_000)

        assert_(page.evaluate("tracker.initStatus") == "ok", "task 1 tracker started")
        assert_(
            page.evaluate("tracker.calibrationRestored") is True,
            "task 1 restored the participant's calibration",
        )
        assert_(
            page.evaluate("js_vars.calibration_key") == key,
            "task 1 uses the same participant key",
        )
        rois1 = page.evaluate("tracker.roiSnapshots.length")
        assert_(rois1 > 0, f"task 1 recorded its table regions (got {rois1} snapshots)")

        for i in range(1, 11):
            page.click(f"input[name='choice_{i}'][value='1']")
        page.click(NEXT)
        page.wait_for_load_state("networkidle")

        # mpl_risk Results
        assert_("payoff" in page.inner_text("body").lower(), "task 1 results shown")
        page.click(NEXT)
        page.wait_for_load_state("networkidle")

        print("\n[4/5] Task 2 (matrix_game) restores the same calibration")
        page.wait_for_selector("table.payoff-matrix", timeout=30_000)
        page.wait_for_function("() => tracker.initStatus !== 'unknown'", timeout=45_000)

        assert_(page.evaluate("tracker.initStatus") == "ok", "task 2 tracker started")
        assert_(
            page.evaluate("tracker.calibrationRestored") is True,
            "task 2 restored the participant's calibration across the app boundary",
        )
        assert_(
            page.evaluate("js_vars.calibration_key") == key,
            "task 2 uses the same participant key",
        )
        names = set(page.evaluate("tracker.roiSnapshots[0].items.map(i => i.name)"))
        assert_(
            {"cell-cc", "cell-cd", "cell-dc", "cell-dd"} <= names,
            "task 2 recorded all four payoff cells",
        )

        page.click("input[name='cooperate'][value='True']")
        page.wait_for_timeout(500)
        page.click(NEXT)
        page.wait_for_load_state("networkidle")

        print("\n[5/5] The battery completes")
        body = page.inner_text("body")
        assert_("you earned" in body.lower(), "task 2 results shown")

        restored_lines = [l for l in logs if "restored a calibrated model" in l]
        assert_(
            len(restored_lines) >= 2,
            f"both task pages logged a real restore (saw {len(restored_lines)})",
        )
        fell_back = [l for l in logs if "falling back to the base model" in l]
        assert_(not fell_back, "neither task silently fell back to the base model")

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
