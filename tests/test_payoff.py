"""
Unit tests for the MPL price ladder and the payoff rule in mpl_risk/__init__.py.

Pure Python: no database, no browser, no oTree runtime beyond the Currency type.

    python -m pytest tests/test_payoff.py

or, for a one-off check without pytest:

    python tests/test_payoff.py
"""

import os
import sys
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')

try:
    from otree.api import cu

    from mpl_risk import C, calculate_payoff, get_safe_amount, summarize_switching
except Exception as exc:  # pragma: no cover
    print(f"SKIP: could not import mpl_risk ({exc!r})")
    sys.exit(0)


def make_player(**choices):
    """Stub Player carrying only what calculate_payoff reads and writes."""
    player = SimpleNamespace(payoff=None, selected_row=None, lottery_outcome=None,
                             num_switches=None, switch_row=None)
    for row in range(1, C.NUM_CHOICES + 1):
        setattr(player, f'choice_{row}', choices.get(f'choice_{row}'))
    return player


def player_with(pattern):
    """`pattern` is a list of 10 choice values (1 = safe, 2 = lottery)."""
    return make_player(**{f'choice_{i}': v for i, v in enumerate(pattern, 1)})


# --- the price ladder -------------------------------------------------------

def test_row_1_equals_safe_min():
    assert get_safe_amount(1) == C.SAFE_MIN, get_safe_amount(1)


def test_top_row_equals_safe_max():
    """Currency division used to round the increment to 0.21, so row 10 paid 3.89."""
    top = get_safe_amount(C.NUM_CHOICES)
    assert top == C.SAFE_MAX, f"row {C.NUM_CHOICES} should equal SAFE_MAX {C.SAFE_MAX}, got {top}"


def test_ladder_is_strictly_increasing():
    amounts = [get_safe_amount(r) for r in range(1, C.NUM_CHOICES + 1)]
    for a, b in zip(amounts, amounts[1:]):
        assert b > a, f"ladder not strictly increasing: {amounts}"


def test_ladder_stays_within_declared_bounds():
    for row in range(1, C.NUM_CHOICES + 1):
        amount = get_safe_amount(row)
        assert C.SAFE_MIN <= amount <= C.SAFE_MAX, f"row {row} = {amount} outside bounds"


def test_risk_neutral_switch_point_is_interior():
    """A risk-neutral agent must have a switch row strictly inside 1..NUM_CHOICES."""
    ev = C.LOTTERY_PROB * C.LOTTERY_HIGH + (1 - C.LOTTERY_PROB) * C.LOTTERY_LOW
    switch = next(r for r in range(1, C.NUM_CHOICES + 1) if get_safe_amount(r) > ev)
    assert 1 < switch < C.NUM_CHOICES, f"switch row {switch} is degenerate (EV={ev})"


# --- the payoff rule --------------------------------------------------------

def test_choosing_option_a_pays_that_rows_safe_amount():
    player = make_player(**{f'choice_{r}': 1 for r in range(1, 11)})
    calculate_payoff(player)
    assert player.lottery_outcome == C.OUTCOME_SAFE
    assert player.payoff == get_safe_amount(player.selected_row)


def test_choosing_option_b_pays_a_lottery_prize():
    player = make_player(**{f'choice_{r}': 2 for r in range(1, 11)})
    calculate_payoff(player)
    assert player.lottery_outcome in (1, 2)
    assert player.payoff in (C.LOTTERY_HIGH, C.LOTTERY_LOW)


def test_unanswered_choice_is_not_silently_paid_the_lottery():
    """
    oTree's admin 'Advance participants' auto-submits a missing IntegerField as 0.
    `if choice == 1` sends 0 down the else branch, so the participant used to be
    paid the lottery for a row they never answered.
    """
    player = make_player()  # every choice_N is None
    for row in range(1, C.NUM_CHOICES + 1):
        setattr(player, f'choice_{row}', 0)  # what oTree actually writes
    calculate_payoff(player)
    assert player.lottery_outcome == C.NO_CHOICE, (
        f"unanswered row was resolved as lottery_outcome={player.lottery_outcome}"
    )
    assert player.payoff == cu(0), f"unanswered row paid {player.payoff}"


def test_unanswered_choice_none_is_also_handled():
    player = make_player()  # every choice_N is None
    calculate_payoff(player)
    assert player.lottery_outcome == C.NO_CHOICE
    assert player.payoff == cu(0)


# --- price-list consistency -------------------------------------------------

A, B = 1, 2


def test_single_switch_records_the_row_where_the_lottery_is_first_taken():
    player = player_with([A, A, A, B, B, B, B, B, B, B])
    summarize_switching(player)
    assert player.num_switches == 1
    assert player.switch_row == 4


def test_switching_on_the_last_row_is_still_a_single_switch():
    player = player_with([A] * 9 + [B])
    summarize_switching(player)
    assert player.num_switches == 1
    assert player.switch_row == 10


def test_multiple_switching_is_recorded_and_has_no_switch_row():
    """
    A real session produced [1,1,2,1,1,1,1,1,2,2]: three transitions. Such a
    participant has not revealed a risk preference and is normally excluded.
    """
    player = player_with([A, A, B, A, A, A, A, A, B, B])
    summarize_switching(player)
    assert player.num_switches == 3
    assert player.switch_row is None


def test_never_switching_has_no_switch_row():
    for pattern in ([A] * 10, [B] * 10):
        player = player_with(pattern)
        summarize_switching(player)
        assert player.num_switches == 0
        assert player.switch_row is None


def test_starting_on_the_lottery_and_switching_to_safe_has_no_switch_row():
    """One transition, but the wrong way round: not an interpretable switch point."""
    player = player_with([B, B, B, A, A, A, A, A, A, A])
    summarize_switching(player)
    assert player.num_switches == 1
    assert player.switch_row is None


def test_unanswered_rows_do_not_invent_transitions():
    player = make_player()  # all None
    summarize_switching(player)
    assert player.num_switches == 0
    assert player.switch_row is None


def test_selected_row_is_always_in_range():
    for _ in range(50):
        player = make_player(**{f'choice_{r}': 1 for r in range(1, 11)})
        calculate_payoff(player)
        assert 1 <= player.selected_row <= C.NUM_CHOICES


if __name__ == '__main__':
    failures = []
    for name, fn in list(globals().items()):
        if name.startswith('test_') and callable(fn):
            try:
                fn()
                print(f"  ok  {name}")
            except AssertionError as exc:
                failures.append((name, exc))
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:
                failures.append((name, exc))
                print(f"  ERROR {name}: {exc!r}")
    sys.exit(1 if failures else 0)
