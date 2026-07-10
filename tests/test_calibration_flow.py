"""
Drive the whole nine-point calibration sequence to completion.

Chromium's synthetic camera has no face, so `getCurrentGaze()` returns null and
the real calibration flow stops at the first dot — which means the code path
*after* the `await gazeTracker.calibrate(...)` is never executed by any other
browser test. That is exactly where a bug lived: `event.currentTarget` is only
valid while an event is being dispatched, and the await hands control back to
the browser, which resets it to null. The dot was never marked, the sequence
never advanced, and a real participant was stuck on the first dot.

So: stub the gaze reading and the adapt call, keeping the async boundary intact,
and walk all nine dots.

Setup:
    pip install playwright && python -m playwright install chromium

Run:
    otree devserver               # in one terminal
    python tests/test_calibration_flow.py
"""

from __future__ import annotations

import re
import sys

BASE_URL = "http://localhost:8000"

# Report gaze at the centre of the screen. Held-out points are away from the
# centre, so the RMSE comes out positive and we can tell it was really computed.
STUB_GAZE = """
() => {
  gazeTracker.getCurrentGaze = () => ({
    x: window.innerWidth / 2,
    y: window.innerHeight / 2,
    normX: 0, normY: 0, gazeState: 'open',
  });
  // Keep this async: the bug it guards against only appears after an await.
  gazeTracker.calibrate = () => Promise.resolve(true);
}
"""


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

        page_errors: list[str] = []
        page.on("pageerror", lambda e: page_errors.append(str(e)))

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

        print("\n[1/3] Walk all nine dots")
        page.locator("#loading-overlay").wait_for(state="hidden", timeout=45_000)
        page.click("#start-calibration-btn")
        page.wait_for_selector(".calibration-point.active", timeout=45_000)
        page.evaluate(STUB_GAZE)

        total = page.evaluate("document.querySelectorAll('.calibration-point').length")
        assert_(total == 9, f"nine dots are presented (got {total})")

        active_index = (
            "Array.from(document.querySelectorAll('.calibration-point'))"
            ".findIndex(d => d.classList.contains('active'))"
        )
        for i in range(total):
            # Wait for the sequence to reach dot i before clicking it. Clicking
            # whichever dot happens to be active would re-click the previous one
            # during the inter-dot delay.
            page.wait_for_function(f"() => {active_index} === {i}", timeout=10_000)
            page.click(".calibration-point.active", force=True)
            # Each click must mark its own dot and advance the sequence.
            page.wait_for_function(
                f"() => document.querySelectorAll('.calibration-point.clicked').length === {i + 1}",
                timeout=10_000,
            )
        assert_(True, "every dot recorded and advanced the sequence")

        print("\n[2/3] Completion screen")
        page.wait_for_selector("#calibration-complete:not(.hidden)", timeout=10_000)

        rmse_text = (page.text_content("#calibration-rmse-value") or "").strip()
        assert_(
            re.fullmatch(r"\d+", rmse_text) is not None,
            f"a numeric RMSE is displayed (got {rmse_text!r})",
        )

        field = page.evaluate("document.getElementById('eyetrack_calibration_rmse').value")
        assert_(
            field not in ("", "0") and float(field) > 0,
            f"eyetrack_calibration_rmse is positive (got {field!r})",
        )

        print("\n[3/3] The personalised model was saved")
        page.wait_for_function(
            "() => (document.getElementById('calibration-save-status')?.textContent || '').length > 0",
            timeout=15_000,
        )
        save_status = page.text_content("#calibration-save-status") or ""
        assert_("saved" in save_status.lower(), f"calibration saved (got {save_status!r})")

        page.wait_for_selector("#proceed:not(.hidden)", timeout=10_000)
        assert_(True, "participant can proceed to the task")

        assert_(not page_errors, f"no uncaught page errors (got {page_errors})")

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
