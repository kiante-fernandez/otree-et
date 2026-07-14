"""
Drive tools/gaze_visualizer.html against a real all_apps_wide export.

The visualizer is a standalone page opened from disk; no server is involved.
This test loads it in headless Chromium, feeds it a CSV, and asserts the whole
pipeline: participants and tasks discovered, the scanpath drawn to canvas, the
ROI dwell table populated from the recorded rectangles, and time-true playback
actually advancing.

Usage:
    python tests/test_visualizer.py [path/to/all_apps_wide.csv]

Without an argument it exports a fresh CSV from a running server
(http://localhost:8000/ExportWide) into the system temp directory.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
VISUALIZER = ROOT / "tools" / "gaze_visualizer.html"


def fetch_export() -> pathlib.Path:
    out = pathlib.Path(tempfile.gettempdir()) / "visualizer_test_wide.csv"
    with urllib.request.urlopen("http://localhost:8000/ExportWide", timeout=30) as r:
        out.write_bytes(r.read())
    return out


def run(csv_path: pathlib.Path) -> int:
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
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        print("\n[1/4] Load the page and feed it the CSV")
        page.goto(VISUALIZER.as_uri())
        page.set_input_files("#csvFile", str(csv_path))
        page.wait_for_selector("#viewer:not(.hidden)", timeout=10_000)

        n_participants = page.locator("#participantSelect option").count()
        n_apps = page.locator("#appSelect option").count()
        assert_(n_participants >= 1, f"participants discovered ({n_participants})")
        assert_(n_apps >= 1, f"tasks discovered ({n_apps})")

        print("\n[2/4] A scanpath is actually drawn")

        def canvas_ink() -> int:
            # Count non-white pixels; a blank canvas has none.
            return page.evaluate(
                """() => {
                  const c = document.getElementById('gazeCanvas');
                  const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
                  let n = 0;
                  for (let i = 0; i < d.length; i += 4) {
                    if (d[i] < 245 || d[i+1] < 245 || d[i+2] < 245) n++;
                  }
                  return n;
                }"""
            )

        # Find a participant/task combination that has samples.
        found = None
        for pi in range(n_participants):
            for ai in range(n_apps):
                page.select_option("#participantSelect", str(pi))
                page.select_option("#appSelect", str(ai))
                page.wait_for_timeout(150)
                if "no gaze data" not in (page.text_content("#infoBar") or ""):
                    found = (pi, ai)
                    break
            if found:
                break
        assert_(found is not None, "at least one participant/task pair has samples")
        assert_(canvas_ink() > 500, f"the canvas has a drawn scanpath ({canvas_ink()} inked pixels)")

        stats = page.text_content("#statsPanel") or ""
        assert_("Samples" in stats and "Hz" in stats, "the recording panel is populated")

        print("\n[3/4] ROI overlay (when the export carries rectangles)")
        has_rois = page.evaluate("current && current.rois.length > 0")
        if has_rois:
            # The overlay must be real drawn ink: toggling it off changes the canvas.
            with_rois = canvas_ink()
            page.uncheck("#showRois")
            page.wait_for_timeout(150)
            without_rois = canvas_ink()
            page.check("#showRois")
            page.wait_for_timeout(150)
            assert_(with_rois > without_rois,
                    f"the recorded regions are drawn ({with_rois} vs {without_rois} inked pixels)")
        else:
            print("  (this export has no ROI rectangles; skipped)")

        print("\n[4/4] Time-true playback advances")
        t_before = page.text_content("#timeDisplay")
        page.click("#playBtn")           # restarts from 0 when at the end
        page.wait_for_timeout(700)
        t_during = page.text_content("#timeDisplay")
        assert_(t_before != t_during, f"the playhead moved ({t_before!r} -> {t_during!r})")
        page.click("#playBtn")

        # Scrubbing to the start empties the visible path.
        page.eval_on_selector("#timeline", "el => { el.value = 0; el.dispatchEvent(new Event('input')); }")
        page.wait_for_timeout(150)
        start_ink = canvas_ink()
        page.eval_on_selector("#timeline", "el => { el.value = 1000; el.dispatchEvent(new Event('input')); }")
        page.wait_for_timeout(150)
        assert_(canvas_ink() > start_ink, "scrubbing the timeline changes what is drawn")

        assert_(not errors, f"no uncaught page errors (got {errors[:2]})")
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
    if len(sys.argv) > 1:
        csv_file = pathlib.Path(sys.argv[1])
    else:
        try:
            csv_file = fetch_export()
        except Exception as exc:
            print(f"could not fetch an export from a running server ({exc}); "
                  "pass a CSV path instead", file=sys.stderr)
            sys.exit(2)
    print(f"CSV: {csv_file}")
    sys.exit(run(csv_file))
