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


HEADER = [
    'session_code', 'participant_code', 'app', 'page',
    'eyetrack_init_status', 'sample_index',
    'x', 'y', 'norm_x', 'norm_y',
    'gaze_state', 'clipped', 't_perf', 'frame_time',
]


def test_header_and_columns():
    rows = list(custom_export([make_player([])]))
    assert rows == [HEADER], f"unexpected header: {rows}"


def test_yields_one_row_per_sample():
    samples = [
        {'x': 100, 'y': 200, 'norm_x': -0.4, 'norm_y': 0.0,
         'gaze_state': 'open', 't_perf': 1.5, 'frame_time': 4.85},
        {'x': 110, 'y': 210, 'norm_x': -0.3, 'norm_y': 0.05,
         'gaze_state': 'open', 't_perf': 1.6, 'frame_time': 4.90},
    ]
    player = make_player(samples, init_status='ok',
                         session='SESS', participant='PART')
    rows = list(custom_export([player]))
    # 1 header + 2 samples
    assert len(rows) == 3
    first = rows[1]
    assert first[0] == 'SESS'
    assert first[1] == 'PART'
    assert first[2] == 'mpl_risk'  # app
    assert first[3] == 'Decision'  # page
    assert first[4] == 'ok'
    assert first[5] == 0  # sample_index
    assert first[6] == 100  # x
    assert first[-1] == 4.85  # frame_time


def test_no_face_sample_exports_empty_coordinates_not_screen_centre():
    """
    A frame with no face is not a look at the middle of the screen. The tracker
    records null coordinates for it; the export must pass those through rather
    than substituting a number.
    """
    samples = [{'x': None, 'y': None, 'norm_x': None, 'norm_y': None,
                'gaze_state': 'closed', 'clipped': False,
                't_perf': 1.5, 'frame_time': 4.85}]
    rows = list(custom_export([make_player(samples)]))
    row = rows[1]
    assert row[6] is None and row[7] is None, f"x/y should be empty, got {row[6]!r},{row[7]!r}"
    assert row[10] == 'closed'
    assert row[11] == 0  # clipped


def test_clipped_is_exported_as_zero_or_one():
    """
    The tracker saturates gaze at the screen edge, so a clipped sample is
    censored rather than measured. Export it as a numeric flag so it loads
    cleanly into pandas or R.
    """
    samples = [
        {'x': 0, 'y': 10, 'gaze_state': 'open', 'clipped': True},
        {'x': 5, 'y': 10, 'gaze_state': 'open', 'clipped': False},
        {'x': 5, 'y': 10, 'gaze_state': 'open'},  # older data, no flag
    ]
    rows = list(custom_export([make_player(samples)]))
    assert [r[11] for r in rows[1:]] == [1, 0, 0]


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


def test_survives_valid_json_of_the_wrong_shape():
    """
    eyetrack_gaze_data is written by the participant's browser. These values all
    parse as JSON, so the json.loads guard lets them through; each one used to
    raise TypeError or AttributeError out of the generator and abort the whole
    export for every participant in the session.
    """
    for raw in ['123', 'null', 'true', '"abc"', '[1,2,3]', '{"x":1}', '[[1,2]]']:
        player = SimpleNamespace(
            eyetrack_gaze_data=raw,
            eyetrack_init_status='ok',
            session=SimpleNamespace(code='S'),
            participant=SimpleNamespace(code='P'),
        )
        rows = list(custom_export([player]))
        assert len(rows) == 1, f"{raw!r} should yield header only, got {len(rows)} rows"


def test_one_bad_player_does_not_abort_the_whole_export():
    """A single malformed row must not cost the researcher every other row."""
    good = make_player([{'x': 1, 'y': 2}], participant='GOOD')
    bad = SimpleNamespace(
        eyetrack_gaze_data='[1,2,3]',
        eyetrack_init_status='ok',
        session=SimpleNamespace(code='S'),
        participant=SimpleNamespace(code='BAD'),
    )
    rows = list(custom_export([bad, good]))
    assert len(rows) == 2, f"expected header + GOOD's one sample, got {len(rows)}"
    assert rows[1][1] == 'GOOD'


def test_skips_non_dict_samples_inside_a_valid_list():
    """A list that mixes real samples with junk keeps the real ones."""
    player = make_player([{'x': 1, 'y': 2}, 7, None, {'x': 3, 'y': 4}])
    rows = list(custom_export([player]))
    assert len(rows) == 3, f"expected header + 2 real samples, got {len(rows)}"
    assert [r[6] for r in rows[1:]] == [1, 3]


def test_init_status_propagates_per_row():
    samples = [{'x': 1, 'y': 2, 'gaze_state': 'open'}]
    player = make_player(samples, init_status='init_failed')
    rows = list(custom_export([player]))
    assert rows[1][4] == 'init_failed'


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
