"""
End-to-end walk of the matrix game demo: consent, calibration page, the 2x2
decision matrix, results.

What this pins down beyond the mpl_risk smoke test:

  * A second task app runs on the same shared eyetrack app, with no
    eye-tracking code of its own beyond the include and the field block.
  * The payoff cells' on-screen rectangles (data-eyetrack-roi) are captured
    and posted with the data, so gaze can be assigned to cells offline.
  * The payoff shown on Results matches the recorded choices and the matrix.

Chromium's synthetic camera has no face, so calibration is skipped through the
escape hatch; the tracked page still runs with the base model.

Run:
    otree prodserver 8000         # in one terminal (or otree devserver)
    python tests/test_matrix_e2e.py
"""

from __future__ import annotations

import json
import re
import sys

BASE_URL = "http://localhost:8000"

PAYOFFS = {
    # (my_cooperate, other_cooperate) -> my payoff, mirroring matrix_game.C
    (True, True): 2.00,
    (True, False): 0.00,
    (False, True): 3.00,
    (False, False): 1.00,
}


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

        print("\n[1/4] Consent and calibration (skipped: no face in the fake camera)")
        page.goto(f"{BASE_URL}/demo/matrix_game")
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

        page.locator("#loading-overlay").wait_for(state="hidden", timeout=45_000)
        page.click("#start-calibration-btn")
        page.wait_for_selector(".calibration-point.active", timeout=45_000)
        for _ in range(3):
            page.click(".calibration-point.active", force=True)
            page.wait_for_timeout(400)
        page.wait_for_selector("#calibration-escape:not(.hidden)", timeout=10_000)
        page.click("#skip-calibration-btn")
        page.wait_for_selector("#proceed:not(.hidden)", timeout=10_000)
        page.click("button[type='submit'], .otree-btn-next, button:has-text('Next')")
        page.wait_for_load_state("networkidle")

        print("\n[2/4] The matrix page tracks and records the payoff-cell regions")
        page.wait_for_selector("table.payoff-matrix", timeout=15_000)
        page.wait_for_function("() => tracker.initStatus !== 'unknown'", timeout=45_000)

        status = page.evaluate("tracker.initStatus")
        assert_(status == "ok", f"tracker started on the second app's page (got {status!r})")

        page.wait_for_function("() => tracker.roiSnapshots.length > 0", timeout=10_000)
        names = set(page.evaluate(
            "tracker.roiSnapshots[0].items.map(i => i.name)"
        ))
        for cell in ("cell-cc", "cell-cd", "cell-dc", "cell-dd"):
            assert_(cell in names, f"payoff cell {cell} has a recorded rectangle")
        assert_("choice-controls" in names, "the choice controls have a recorded rectangle")

        sane = page.evaluate(
            "tracker.roiSnapshots[0].items.every(i => i.w > 0 && i.h > 0)"
        )
        assert_(sane, "every recorded rectangle has positive size")

        print("\n[3/4] Decide (Defect) and submit")
        page.click("input[name='cooperate'][value='False']")
        page.wait_for_timeout(800)
        page.click("button[type='submit'], .otree-btn-next, button:has-text('Next')")
        page.wait_for_load_state("networkidle")

        print("\n[4/4] Results are consistent with the matrix")
        body = page.inner_text("body")
        assert_("You chose to Defect" in body or "Both of you chose to" in body,
                "Results names the decisions")

        drew_cooperate = "chose to Cooperate" in body and "You chose to Defect" in body
        both_defect = "Both of you chose to Defect" in body
        assert_(drew_cooperate or both_defect, f"opponent decision disclosed (body: {body[:120]!r})")

        expected = PAYOFFS[(False, True)] if drew_cooperate else PAYOFFS[(False, False)]
        amount = re.search(r"you earned\s+€?(\d+(?:\.\d+)?)", body)
        assert_(amount is not None and float(amount.group(1)) == expected,
                f"payoff matches the matrix (expected {expected}, body says {amount and amount.group(1)})")

        assert_("drawn at random" in body, "the random opponent draw is disclosed to the participant")

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
