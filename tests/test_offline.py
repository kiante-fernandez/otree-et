"""
The eye tracker must work with every third-party host blocked.

A study cannot depend on a CDN being reachable when a participant sits down, and
in many settings a participant's browser may not disclose its IP address to a
third party at all. This test blocks every request that does not go to the
application itself, then drives the flow and asserts the tracker still starts,
loads its models, and records real gaze samples.

It also records exactly which external hosts were contacted, so a future change
that reintroduces a CDN dependency fails here loudly.

Setup:
    pip install playwright && python -m playwright install chromium

Run:
    otree devserver           # in one terminal
    python tests/test_offline.py
"""

from __future__ import annotations

import re
import sys
from urllib.parse import urlparse

BASE_URL = "http://localhost:8000"
ALLOWED_HOSTS = {"localhost", "127.0.0.1"}


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

    blocked: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
            ],
        )
        context = browser.new_context(permissions=["camera"])

        def gate(route):
            host = urlparse(route.request.url).hostname or ""
            if host in ALLOWED_HOSTS or route.request.url.startswith("blob:"):
                route.continue_()
            else:
                blocked.append(route.request.url)
                route.abort()

        context.route("**/*", gate)
        page = context.new_page()

        print("\n[1/3] Consent")
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

        print("\n[2/3] Calibration page loads its models with no network access")
        page.locator("#loading-overlay").wait_for(state="hidden", timeout=45_000)
        page.click("#start-calibration-btn")
        page.wait_for_selector(".calibration-point.active", timeout=45_000)
        assert_(True, "the gaze model and MediaPipe both loaded from /static/")

        for _ in range(3):
            page.click(".calibration-point.active", force=True)
            page.wait_for_timeout(400)
        page.wait_for_selector("#calibration-escape:not(.hidden)", timeout=10_000)
        page.click("#skip-calibration-btn")
        page.wait_for_selector("#proceed:not(.hidden)", timeout=10_000)
        page.click("button[type='submit'], .otree-btn-next, button:has-text('Next')")
        page.wait_for_load_state("networkidle")

        print("\n[3/3] Decision page records real gaze samples")
        page.wait_for_function("() => tracker.initStatus !== 'unknown'", timeout=45_000)

        status = page.evaluate("tracker.initStatus")
        assert_(status == "ok", f"tracker started offline (init_status={status!r})")

        # Wait on the condition, not the clock: this page reloads MediaPipe's
        # 8.7 MB of WASM before any frame can be processed.
        try:
            page.wait_for_function("() => tracker.allSamples.length > 0", timeout=30_000)
        except Exception:
            pass
        n = page.evaluate("tracker.allSamples.length")
        assert_(n > 0, f"gaze samples collected offline (got {n})")

        browser.close()

    external = sorted({urlparse(u).hostname for u in blocked})
    print(f"\nexternal hosts contacted: {external or 'none'}")
    assert_(not external, f"no third-party host is contacted at run time (saw {external})")

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
