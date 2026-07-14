"""
Unit tests for the matrix game's payoff rule.

Pure Python: no database, no browser.

    python -m pytest tests/test_matrix_game.py

or, for a one-off check without pytest:

    python tests/test_matrix_game.py
"""

import os
import sys
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')

try:
    from otree.api import cu

    from matrix_game import C, draw_opponent, payoff_matrix, set_payoff
except Exception as exc:  # pragma: no cover
    print(f"SKIP: could not import matrix_game ({exc!r})")
    sys.exit(0)


def make_player(cooperate):
    return SimpleNamespace(cooperate=cooperate, opponent_cooperate=None, payoff=None,
                           no_choice=False)


def test_payoffs_have_the_prisoners_dilemma_ordering():
    """Temptation > reward > punishment > sucker is what makes it a dilemma."""
    assert (
        C.PAYOFF_TEMPTATION > C.PAYOFF_REWARD > C.PAYOFF_PUNISHMENT > C.PAYOFF_SUCKER
    )
    # And cooperation must be jointly efficient: 2R > T + S.
    assert C.PAYOFF_REWARD * 2 > C.PAYOFF_TEMPTATION + C.PAYOFF_SUCKER


def test_matrix_covers_all_four_outcomes():
    matrix = payoff_matrix()
    assert set(matrix) == {(True, True), (True, False), (False, True), (False, False)}
    assert matrix[(True, True)] == C.PAYOFF_REWARD
    assert matrix[(True, False)] == C.PAYOFF_SUCKER
    assert matrix[(False, True)] == C.PAYOFF_TEMPTATION
    assert matrix[(False, False)] == C.PAYOFF_PUNISHMENT


def test_set_payoff_records_the_drawn_opponent_and_pays_from_the_matrix():
    for my_choice in (True, False):
        for _ in range(20):
            player = make_player(my_choice)
            set_payoff(player)
            assert player.opponent_cooperate in (True, False), (
                "the opponent draw must be recorded, or the outcome cannot be audited"
            )
            assert player.payoff == payoff_matrix()[(my_choice, player.opponent_cooperate)]


def test_auto_submitted_page_is_not_paid_as_a_defection():
    """
    oTree's admin force-advance auto-submits an unanswered BooleanField as
    False -- here a valid choice, Defect. Without the timeout guard the
    participant would be paid for a gamble they never took, and the exported
    row would be indistinguishable from a genuine defection.
    """
    player = make_player(cooperate=False)  # what oTree's auto-submit writes
    set_payoff(player, timeout_happened=True)
    assert player.no_choice is True
    assert player.payoff == cu(0), f"a never-made choice paid {player.payoff}"
    assert player.opponent_cooperate is None, "no opponent should be drawn for a non-choice"


def test_a_real_choice_is_not_flagged_as_no_choice():
    player = make_player(cooperate=True)
    set_payoff(player, timeout_happened=False)
    assert player.no_choice is False
    assert player.opponent_cooperate in (True, False)


def test_opponent_draw_produces_both_outcomes():
    draws = {draw_opponent() for _ in range(200)}
    assert draws == {True, False}, f"a fair draw should produce both outcomes (got {draws})"


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
