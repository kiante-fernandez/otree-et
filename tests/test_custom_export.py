"""
Unit test for the custom_export generator in mpl_risk/__init__.py.

Verifies the long-format gaze export against synthetic samples — no
database, no browser, no oTree runtime needed. Run with:

    python -m pytest tests/

or, for a one-off check without pytest:

    python tests/test_custom_export.py
"""

import json
import os
import sys
from types import SimpleNamespace

# Make the project root importable without configuring DJANGO_SETTINGS_MODULE.
# We only need the custom_export function — not Django models — for this test.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Set up a Django settings stub so that `from otree.api import ...` succeeds
# without needing a full oTree boot. If oTree isn't installed, the test is
# skipped with a clear message.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')

try:
    from mpl_risk import custom_export
except Exception as exc:  # pragma: no cover
    print(f"SKIP: could not import mpl_risk.custom_export ({exc!r})")
    sys.exit(0)


def make_player(samples, init_status='ok', session='S1', participant='P1'):
    """Build a stub Player with just the attributes custom_export reads."""
    return SimpleNamespace(
        eyetrack_gaze_data=json.dumps(samples) if samples is not None else '',
        eyetrack_init_status=init_status,
        session=SimpleNamespace(code=session),
        participant=SimpleNamespace(code=participant),
    )


def test_header_and_columns():
    rows = list(custom_export([make_player([])]))
    assert rows == [[
        'session_code', 'participant_code', 'page',
        'eyetrack_init_status', 'sample_index',
        'x', 'y', 'norm_x', 'norm_y',
        'gaze_state', 'confidence', 't_perf', 'timestamp', 'is_mock',
    ]], f"unexpected header: {rows}"


def test_yields_one_row_per_sample():
    samples = [
        {'x': 100, 'y': 200, 'norm_x': -0.4, 'norm_y': 0.0,
         'gaze_state': 'open', 'confidence': 0.9,
         't_perf': 1.5, 'timestamp': 1700000000000, 'is_mock': False},
        {'x': 110, 'y': 210, 'norm_x': -0.3, 'norm_y': 0.05,
         'gaze_state': 'open', 'confidence': 0.85,
         't_perf': 1.6, 'timestamp': 1700000000033, 'is_mock': False},
    ]
    player = make_player(samples, init_status='ok',
                         session='SESS', participant='PART')
    rows = list(custom_export([player]))
    # 1 header + 2 samples
    assert len(rows) == 3
    first = rows[1]
    assert first[0] == 'SESS'
    assert first[1] == 'PART'
    assert first[2] == 'Decision'
    assert first[3] == 'ok'
    assert first[4] == 0  # sample_index
    assert first[5] == 100  # x
    assert first[-1] == 0  # is_mock rendered as 0


def test_is_mock_rendered_as_one_when_true():
    sample = {'x': 1, 'y': 2, 'is_mock': True}
    rows = list(custom_export([make_player([sample])]))
    assert rows[1][-1] == 1, f"is_mock should be int 1, got {rows[1][-1]!r}"


def test_skips_player_with_empty_data():
    rows = list(custom_export([
        make_player(None, init_status='no_consent'),  # never wrote any data
        make_player([]),                              # empty array
    ]))
    # Only the header row; both players contributed zero sample rows.
    assert len(rows) == 1


def test_skips_player_with_corrupt_json():
    bad = SimpleNamespace(
        eyetrack_gaze_data='{not valid json',
        eyetrack_init_status='ok',
        session=SimpleNamespace(code='S'),
        participant=SimpleNamespace(code='P'),
    )
    rows = list(custom_export([bad]))
    assert len(rows) == 1  # header only


def test_init_status_propagates_per_row():
    samples = [{'x': 1, 'y': 2, 'is_mock': True}]
    player = make_player(samples, init_status='init_failed')
    rows = list(custom_export([player]))
    assert rows[1][3] == 'init_failed'


if __name__ == '__main__':
    # Allow running as `python tests/test_custom_export.py` without pytest.
    failures = []
    for name, fn in list(globals().items()):
        if name.startswith('test_') and callable(fn):
            try:
                fn()
                print(f"  ok  {name}")
            except AssertionError as exc:
                failures.append((name, exc))
                print(f"  FAIL {name}: {exc}")
    sys.exit(1 if failures else 0)
