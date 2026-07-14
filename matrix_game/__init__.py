"""
One-shot Prisoner's Dilemma with webcam eye tracking.

The task follows oTree's standard `prisoner` sample app, with one deliberate
change: it is single-player. An eye-tracking demo has to run solo — a real
two-player session would strand the participant on a wait page — so the other
player's decision is drawn at random when the participant submits, and the
Results page says so plainly. In a real study, replace the draw in
`draw_opponent` with decisions pre-recorded from earlier human participants.

Why a matrix game for eye tracking: which payoffs a player inspects before
choosing — their own versus the other player's, the cells for cooperation
versus defection — is itself a finding (see Polonio & Coricelli on information
search in one-shot games). Every payoff cell carries a `data-eyetrack-roi`
attribute, so the exported data includes each cell's on-screen rectangle and
gaze can be assigned to cells offline.

Run after the `eyetrack` app (consent + calibration):

    app_sequence = ['eyetrack', 'matrix_game']
"""

import random

from otree.api import (
    cu,
    models,
    widgets,
    BaseConstants,
    BaseSubsession,
    BaseGroup,
    BasePlayer,
    Page,
)

from eyetrack_shared import EYETRACK_FORM_FIELDS, eyetrack_js_vars, gaze_rows

doc = __doc__


class C(BaseConstants):
    NAME_IN_URL = 'matrix_game'
    PLAYERS_PER_GROUP = None
    NUM_ROUNDS = 1
    # The classic ordering: temptation > reward > punishment > sucker.
    PAYOFF_TEMPTATION = cu(3.00)  # you defect, other cooperates
    PAYOFF_REWARD = cu(2.00)      # both cooperate
    PAYOFF_PUNISHMENT = cu(1.00)  # both defect
    PAYOFF_SUCKER = cu(0)         # you cooperate, other defects


class Subsession(BaseSubsession):
    pass


class Group(BaseGroup):
    pass


class Player(BasePlayer):
    cooperate = models.BooleanField(
        choices=[[True, 'Cooperate'], [False, 'Defect']],
        label='Your decision',
        widget=widgets.RadioSelectHorizontal,
    )
    # The other player's decision, drawn at submission time (never shown while
    # the participant is deciding). In a real study, fill this from
    # pre-recorded human decisions instead.
    opponent_cooperate = models.BooleanField()

    # --- eye tracking (see eyetrack_shared.py for what each field means) ---
    eyetrack_sample_count = models.IntegerField(initial=0)
    eyetrack_gaze_data = models.LongStringField(blank=True)
    eyetrack_init_status = models.StringField(initial='unknown')
    eyetrack_calibration_restored = models.BooleanField(initial=False)
    eyetrack_viewport_width = models.IntegerField(initial=0)
    eyetrack_viewport_height = models.IntegerField(initial=0)
    eyetrack_viewport_changed = models.BooleanField(initial=False)
    eyetrack_rois = models.LongStringField(blank=True)
    eyetrack_runtime_error = models.LongStringField(blank=True)


def payoff_matrix():
    """(my_cooperate, other_cooperate) -> my payoff. The standard PD."""
    return {
        (True, True): C.PAYOFF_REWARD,
        (True, False): C.PAYOFF_SUCKER,
        (False, True): C.PAYOFF_TEMPTATION,
        (False, False): C.PAYOFF_PUNISHMENT,
    }


def draw_opponent():
    """
    The other player's decision for this one-shot demo.

    A fair coin, disclosed to the participant on the Results page. A real study
    should use decisions pre-recorded from human participants, so the game
    stays a game rather than a bet against a randomising machine.
    """
    return random.random() < 0.5


def set_payoff(player: Player):
    player.opponent_cooperate = draw_opponent()
    player.payoff = payoff_matrix()[(player.cooperate, player.opponent_cooperate)]


class Decision(Page):
    form_model = 'player'
    form_fields = ['cooperate'] + EYETRACK_FORM_FIELDS

    @staticmethod
    def js_vars(player: Player):
        return eyetrack_js_vars(player)

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        set_payoff(player)


class Results(Page):
    @staticmethod
    def vars_for_template(player: Player):
        return dict(
            my_decision='Cooperate' if player.cooperate else 'Defect',
            opponent_decision='Cooperate' if player.opponent_cooperate else 'Defect',
            same_choice=player.cooperate == player.opponent_cooperate,
        )


page_sequence = [Decision, Results]


def custom_export(players):
    """One row per gaze sample; see eyetrack_shared.gaze_rows for the columns."""
    yield from gaze_rows(players, 'matrix_game', 'Decision')
