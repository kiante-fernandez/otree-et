#!/usr/bin/env python3
"""
Grade a real-webcam session.

The automated suite runs against Chromium's synthetic camera, which contains no
face. It can prove the data path is wired up, that failures are reported, and
that calibration persists across pages — but it cannot say whether the tracker
is *accurate*. That needs a human sitting in front of a real webcam.

Run the demo yourself, complete calibration properly, then:

    python tools/check_live_session.py

It reads the most recent participant from db.sqlite3 and reports whether the
data looks like a usable eye-tracking record, naming anything that does not.

  python tools/check_live_session.py --all      grade every participant
  python tools/check_live_session.py --db PATH  use a different database
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys

# Heuristic thresholds. Calibration error is judged as a fraction of the screen
# diagonal, because a pixel threshold means something different on every monitor.
RMSE_GOOD_FRACTION = 0.06
RMSE_OK_FRACTION = 0.12
MIN_OPEN_FRACTION = 0.60
MIN_SAMPLES = 30


class Grade:
    def __init__(self) -> None:
        self.problems: list[str] = []
        self.warnings: list[str] = []

    def fail(self, msg: str) -> None:
        self.problems.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def grade_player(row: sqlite3.Row, calib: dict | None) -> Grade:
    """Grade one task app's row. `calib` is the eyetrack app's record for the
    same participant (consent + calibration quality), or None if that app
    never ran."""
    g = Grade()

    # Databases created before a field was added simply lack the column.
    cols = set(row.keys())
    def get(name, default=None):
        return row[name] if name in cols else default

    status = row["eyetrack_init_status"]
    print(f"  init_status                : {status}")
    if status == "init_pending":
        g.fail("the page was submitted while the eye-tracking model was still "
               "loading; no samples could have been collected")
    elif status != "ok":
        g.fail(f"the tracker did not start (init_status={status!r})")

    if row["eyetrack_runtime_error"]:
        g.fail(f"a JavaScript error occurred: {row['eyetrack_runtime_error'][:90]}")

    # Price-list consistency. Not an eye-tracking property, but it decides
    # whether this participant's risk preference is usable at all.
    switches = get("num_switches")
    if switches is not None:
        label = f"row {get('switch_row')}" if get("switch_row") else "none"
        print(f"  price-list switches        : {switches} (switch point: {label})")
        if switches > 1:
            g.warn(
                f"multiple switching ({switches} transitions); no single switch point, "
                "so this participant's risk preference is not identified"
            )

    restored = bool(get("eyetrack_calibration_restored"))
    print(f"  calibration restored       : {restored}")
    if not restored:
        g.fail("the task page used the UNCALIBRATED base model")

    vw = get("eyetrack_viewport_width") or 0
    vh = get("eyetrack_viewport_height") or 0
    if vw and vh:
        print(f"  viewport                   : {vw} x {vh} px")
    else:
        g.warn("no viewport recorded; gaze pixel coordinates cannot be interpreted")
    if get("eyetrack_viewport_changed"):
        g.warn("the window was resized during the task; samples before and after "
               "the resize are scaled to different viewports")

    rmse = calib.get("rmse") if calib else None
    fraction = calib.get("fraction") if calib else None
    if rmse is None:
        print("  calibration RMSE           : (not measured — calibration skipped)")
        g.fail("calibration was skipped; this participant's gaze is uncalibrated")
    else:
        if not fraction and vw and vh:
            fraction = rmse / (vw ** 2 + vh ** 2) ** 0.5
        pct = f"{fraction:.1%} of the screen diagonal" if fraction else "screen size unknown"
        band = (
            "good" if fraction and fraction <= RMSE_GOOD_FRACTION
            else "ok" if fraction and fraction <= RMSE_OK_FRACTION
            else "poor"
        )
        print(f"  calibration RMSE           : {rmse:.0f} px = {pct} ({band})")
        if rmse <= 0:
            g.fail("RMSE is zero, which means no validation point was ever measured")
        elif fraction and fraction > RMSE_OK_FRACTION:
            g.warn(
                f"calibration is poor ({fraction:.1%} of the screen); consider "
                "recalibrating with a steadier head position, or excluding"
            )

    raw = row["eyetrack_gaze_data"] or ""
    try:
        samples = json.loads(raw) if raw else []
    except ValueError:
        g.fail("eyetrack_gaze_data is not valid JSON")
        samples = []
    if not isinstance(samples, list):
        g.fail("eyetrack_gaze_data is not a list")
        samples = []

    n = len(samples)
    print(f"  samples                    : {n}")
    if n < MIN_SAMPLES:
        g.fail(f"only {n} samples; expected at least {MIN_SAMPLES}")
    if n != row["eyetrack_sample_count"]:
        g.warn(f"sample_count ({row['eyetrack_sample_count']}) disagrees with the data ({n})")
    if not samples:
        return g

    seen = [s for s in samples if s.get("gaze_state") == "open"]
    open_frac = len(seen) / n
    print(f"  frames with a face         : {len(seen)}/{n} ({open_frac:.0%})")
    if open_frac < MIN_OPEN_FRACTION:
        g.fail(
            f"only {open_frac:.0%} of frames saw a face; the webcam mostly could not "
            "find the participant"
        )

    # A frame with no face must never carry coordinates.
    fabricated = [s for s in samples if s.get("gaze_state") != "open" and s.get("x") is not None]
    if fabricated:
        g.fail(f"{len(fabricated)} no-face samples carry coordinates (should be empty)")

    # Gaze is clipped to the screen, so an estimate on the boundary is censored.
    # Samples recorded before the flag existed are re-derived from norm_x/norm_y,
    # so this number never silently under-reports on older data.
    def is_clipped(s):
        if "clipped" in s:
            return bool(s["clipped"])
        nx, ny = s.get("norm_x"), s.get("norm_y")
        if nx is None or ny is None:
            return False
        return max(abs(nx), abs(ny)) >= 0.5 - 1e-9

    clipped = [s for s in samples if is_clipped(s)]
    if seen:
        clipped_frac = len(clipped) / len(seen)
        print(f"  clipped at screen edge     : {len(clipped)}/{len(seen)} ({clipped_frac:.1%})")
        if clipped_frac > 0.10:
            g.warn(
                f"{clipped_frac:.0%} of gaze estimates were saturated at a screen edge; "
                "those are censored, not measured"
            )

    # One sample per unique camera frame.
    frame_times = [s.get("frame_time") for s in samples]
    dupes = len(frame_times) - len(set(frame_times))
    if dupes:
        g.fail(f"{dupes} duplicate camera frames were stored")

    # t_perf must be the monotonic clock.
    t = [s.get("t_perf") for s in samples if isinstance(s.get("t_perf"), (int, float))]
    if len(t) == len(samples) and any(b < a for a, b in zip(t, t[1:])):
        g.warn("t_perf is not monotonically increasing")
    if len(t) > 1:
        span_s = (t[-1] - t[0]) / 1000.0
        if span_s > 0:
            print(f"  sampling rate              : {n / span_s:.1f} Hz over {span_s:.1f} s")

    if len(seen) > 2:
        xs = [s["x"] for s in seen]
        ys = [s["y"] for s in seen]
        sx, sy = statistics.pstdev(xs), statistics.pstdev(ys)
        print(f"  gaze spread (sd)           : x {sx:.0f} px, y {sy:.0f} px")
        if sx < 1 and sy < 1:
            g.fail("gaze never moved; the model is almost certainly not tracking")

        # A pile-up on the exact centre is the signature of the old bug where a
        # no-face frame was recorded as a fixation.
        centre = sum(1 for s in seen if abs(s["norm_x"]) < 1e-9 and abs(s["norm_y"]) < 1e-9)
        if centre:
            g.fail(f"{centre} samples sit at exactly (0,0) normalized — suspicious")

    return g


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="db.sqlite3")
    ap.add_argument("--all", action="store_true", help="grade every participant, not just the latest")
    args = ap.parse_args()

    try:
        conn = sqlite3.connect(args.db)
    except sqlite3.Error as exc:
        print(f"cannot open {args.db}: {exc}", file=sys.stderr)
        return 2
    conn.row_factory = sqlite3.Row

    # Task apps are any *_player table that records gaze; the shared eyetrack
    # app's own table holds consent and calibration quality instead.
    def table_columns(name):
        try:
            return {r[1] for r in conn.execute(f"pragma table_info({name})")}
        except sqlite3.Error:
            return set()

    try:
        all_tables = [
            r[0] for r in conn.execute(
                "select name from sqlite_master where type='table' and name like '%_player'"
            )
        ]
    except sqlite3.Error as exc:
        print(f"cannot read {args.db}: {exc}", file=sys.stderr)
        return 2

    task_tables = [
        name for name in all_tables
        if name != 'eyetrack_player' and 'eyetrack_gaze_data' in table_columns(name)
    ]
    if not task_tables:
        print("No task app tables with gaze data found. Run a demo session first.")
        return 1

    def calibration_for(participant_id):
        if 'eyetrack_player' not in all_tables:
            return None
        row = conn.execute(
            "select * from eyetrack_player where participant_id = ?", (participant_id,)
        ).fetchone()
        if row is None:
            return None
        cols = set(row.keys())
        return dict(
            consent=bool(row['eyetrack_consent']) if 'eyetrack_consent' in cols else None,
            rmse=row['eyetrack_calibration_rmse'] if 'eyetrack_calibration_rmse' in cols else None,
            fraction=row['eyetrack_calibration_rmse_fraction']
            if 'eyetrack_calibration_rmse_fraction' in cols else None,
        )

    order = "id" if args.all else "id desc"
    limit = "" if args.all else "limit 1"
    participants = conn.execute(
        f"select id, code from otree_participant order by {order} {limit}"
    ).fetchall()
    if not participants:
        print("No participants in the database yet. Run the demo first.")
        return 1

    total_problems = 0
    graded_any = False
    for participant in participants:
        calib = calibration_for(participant['id'])
        header_printed = False
        for table in task_tables:
            row = conn.execute(
                f"select * from {table} where participant_id = ?", (participant['id'],)
            ).fetchone()
            if row is None:
                continue
            if not header_printed:
                print(f"\nparticipant {participant['code']}")
                if calib is None:
                    print("  (the eyetrack app never ran for this participant)")
                header_printed = True
            graded_any = True
            app = table[: -len('_player')]
            print(f"\n  [{app}]")
            print("  " + "-" * 44)
            g = grade_player(row, calib)
            total_problems += len(g.problems)
            if g.problems:
                print("\n  PROBLEMS")
                for p in g.problems:
                    print(f"    - {p}")
            if g.warnings:
                print("\n  WARNINGS")
                for w in g.warnings:
                    print(f"    - {w}")
            if not g.problems and not g.warnings:
                print("\n  This looks like a usable eye-tracking record.")

    if not graded_any:
        print("No completed task rows for these participants yet.")
        return 1

    print()
    if total_problems:
        print(f"{total_problems} problem(s) found.")
        return 1
    print("No problems found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
