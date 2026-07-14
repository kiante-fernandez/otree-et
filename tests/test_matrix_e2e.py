"""
End-to-end walk of the matrix game demo: consent, calibration page, the 2x2
decision matrix, results.

What this pins down beyond the mpl_risk smoke test:

  * A second task app runs on the same shared eyetrack app, with no
    eye-tracking code of its own beyond the include and the field block.
  * The payoff cells' on-screen rectangles (data-eyetrack-roi) are captured
    AND actually persisted: after submit, the test reads the stored player row
    from the database and checks the samples, the sample count, and the cell
    rectangles — in-page state alone cannot catch broken hidden-field wiring.
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
import sqlite3
import sys

BASE_URL = "http://localhost:8000"
DB_PATH = "db.sqlite3"

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

        print("\n[1/5] Consent and calibration (skipped: no face in the fake camera)")
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

        print("\n[2/5] The matrix page tracks and records the payoff-cell regions")
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

        print("\n[3/5] Decide (Defect) and submit")
        page.click("input[name='cooperate'][value='False']")
        # Samples must actually flow before we submit, or the persistence
        # assertions below would be vacuous.
        page.wait_for_function("() => tracker.allSamples.length > 0", timeout=30_000)
        participant_code = page.evaluate("js_vars.calibration_key").replace(
            "webeyetrack-calib-", ""
        )
        page.click("button[type='submit'], .otree-btn-next, button:has-text('Next')")
        page.wait_for_load_state("networkidle")

        print("\n[4/5] Results are consistent with the matrix")
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

        print("\n[5/5] The gaze data and ROI rectangles were actually persisted")
        # In-page assertions cannot catch a break in the hidden-field wiring:
        # the tracker's setter is null-tolerant and the model fields accept
        # blank, so a renamed input id posts placeholders while every suite
        # stays green. Read the row oTree stored (prodserver keeps the
        # database on disk, so this works while the server runs).
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "select m.* from matrix_game_player m join otree_participant p"
            " on m.participant_id = p.id where p.code = ?",
            (participant_code,),
        ).fetchone()
        assert_(row is not None, f"a matrix_game row was persisted for {participant_code}")
        if row is not None:
            assert_(row["eyetrack_init_status"] == "ok",
                    f"persisted init_status (got {row['eyetrack_init_status']!r})")
            samples = json.loads(row["eyetrack_gaze_data"] or "[]")
            assert_(len(samples) > 0 and row["eyetrack_sample_count"] == len(samples),
                    f"gaze samples persisted ({row['eyetrack_sample_count']} counted, {len(samples)} stored)")
            rois = json.loads(row["eyetrack_rois"] or "[]")
            persisted_names = {i["name"] for snap in rois for i in snap.get("items", [])}
            assert_({"cell-cc", "cell-cd", "cell-dc", "cell-dd"} <= persisted_names,
                    f"payoff-cell rectangles persisted (got {sorted(persisted_names)[:6]})")
            assert_(bool(row["cooperate"]) is False and row["no_choice"] == 0,
                    "the real Defect choice was recorded as a choice, not flagged no_choice")
        conn.close()

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
