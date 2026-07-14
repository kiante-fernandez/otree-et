"""
Multiple Price List risk-elicitation task with webcam eye tracking.

Run after the `eyetrack` app (consent + calibration):

    app_sequence = ['eyetrack', 'mpl_risk']

The eye-tracking pieces on the Decision page come from eyetrack_shared and
eyetrack/tracked_page.html; this file contains only the task.
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
    NAME_IN_URL = 'mpl_risk'
    PLAYERS_PER_GROUP = None
    NUM_ROUNDS = 1
    NUM_CHOICES = 10
    SAFE_MIN = cu(2.0)
    SAFE_MAX = cu(3.85)
    LOTTERY_LOW = cu(1.0)
    LOTTERY_HIGH = cu(4.0)
    LOTTERY_PROB = 0.5
    PERCENT_MULTIPLIER = 100

    # choice_N values
    OPTION_A = 1  # the safe amount for that row
    OPTION_B = 2  # the lottery

    # lottery_outcome encoding
    NO_CHOICE = -1  # the drawn row was never answered (see calculate_payoff)
    OUTCOME_SAFE = 0
    OUTCOME_LOTTERY_HIGH = 1
    OUTCOME_LOTTERY_LOW = 2


class Subsession(BaseSubsession):
    pass


class Group(BaseGroup):
    pass


def make_choice_field(row):
    """One row of the price list. oTree needs each field declared on the class,
    but the options only have to be written once."""
    return models.IntegerField(
        choices=[[C.OPTION_A, 'Option A'], [C.OPTION_B, 'Option B']],
        label=f'Row {row}',
        widget=widgets.RadioSelectHorizontal,
    )


class Player(BasePlayer):
    choice_1 = make_choice_field(1)
    choice_2 = make_choice_field(2)
    choice_3 = make_choice_field(3)
    choice_4 = make_choice_field(4)
    choice_5 = make_choice_field(5)
    choice_6 = make_choice_field(6)
    choice_7 = make_choice_field(7)
    choice_8 = make_choice_field(8)
    choice_9 = make_choice_field(9)
    choice_10 = make_choice_field(10)

    selected_row = models.IntegerField()
    lottery_outcome = models.IntegerField()  # see C.NO_CHOICE / C.OUTCOME_*
    # Number of times the participant changed option as they moved down the list.
    # A coherent respondent switches exactly once. See summarize_switching().
    num_switches = models.IntegerField(initial=0)
    # The row on which they first take the lottery. Empty unless num_switches
    # is 1 and they began on the safe option.
    switch_row = models.IntegerField(blank=True)

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


def get_safe_amount(row):
    """
    Safe amount offered on `row`, interpolated between SAFE_MIN and SAFE_MAX.

    Scale before dividing. Currency quantizes to whole cents, so computing the
    per-row increment first rounds 0.2055... up to 0.21 and walks the top row
    past SAFE_MAX (row 10 paid 3.89 against a declared maximum of 3.85).
    """
    span = C.SAFE_MAX - C.SAFE_MIN
    return C.SAFE_MIN + span * (row - 1) / (C.NUM_CHOICES - 1)


def summarize_switching(player: Player):
    """
    Record how consistent the participant's price list is.

    A coherent respondent takes the safe option on low rows and switches once to
    the lottery as the safe amount rises. Someone who switches back and forth has
    not given a usable risk preference, and the standard remedy is to exclude
    them — so the data has to say who they are. `switch_row` is only meaningful
    when `num_switches` is 1.
    """
    choices = [getattr(player, f'choice_{row}') for row in range(1, C.NUM_CHOICES + 1)]

    transitions = [
        row for row in range(1, C.NUM_CHOICES)
        if choices[row - 1] is not None
        and choices[row] is not None
        and choices[row - 1] != choices[row]
    ]
    player.num_switches = len(transitions)

    if len(transitions) == 1 and choices[0] == C.OPTION_A:
        # The row on which they first take the lottery.
        player.switch_row = transitions[0] + 1
    else:
        player.switch_row = None


def calculate_payoff(player: Player):
    player.selected_row = random.randint(1, C.NUM_CHOICES)
    choice = getattr(player, f'choice_{player.selected_row}')

    if choice == C.OPTION_A:
        player.payoff = get_safe_amount(player.selected_row)
        player.lottery_outcome = C.OUTCOME_SAFE
    elif choice == C.OPTION_B:
        if random.random() < C.LOTTERY_PROB:
            player.payoff = C.LOTTERY_HIGH
            player.lottery_outcome = C.OUTCOME_LOTTERY_HIGH
        else:
            player.payoff = C.LOTTERY_LOW
            player.lottery_outcome = C.OUTCOME_LOTTERY_LOW
    else:
        # The drawn row holds no valid choice. oTree's admin "Advance
        # participants" auto-submits a missing IntegerField as 0, which an
        # `if choice == 1 ... else` would resolve as the lottery — paying out
        # a gamble the participant never accepted. Record it instead.
        player.payoff = cu(0)
        player.lottery_outcome = C.NO_CHOICE


class Decision(Page):
    form_model = 'player'
    form_fields = (
        [f'choice_{row}' for row in range(1, C.NUM_CHOICES + 1)] + EYETRACK_FORM_FIELDS
    )

    @staticmethod
    def vars_for_template(player: Player):
        rows = [
            {
                'row': row,
                'safe_amount': get_safe_amount(row),
                'field_name': f'choice_{row}',
            }
            for row in range(1, C.NUM_CHOICES + 1)
        ]
        prob_high_percent = int(C.LOTTERY_PROB * C.PERCENT_MULTIPLIER)
        prob_low_percent = C.PERCENT_MULTIPLIER - prob_high_percent
        return dict(
            rows=rows,
            prob_high_percent=prob_high_percent,
            prob_low_percent=prob_low_percent,
        )

    @staticmethod
    def js_vars(player: Player):
        return eyetrack_js_vars(player)

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        summarize_switching(player)
        calculate_payoff(player)


class Results(Page):

    @staticmethod
    def vars_for_template(player: Player):
        safe_amount = get_safe_amount(player.selected_row)
        choice_field = f'choice_{player.selected_row}'
        selected_choice = getattr(player, choice_field)
        return dict(safe_amount=safe_amount, selected_choice=selected_choice)


page_sequence = [Decision, Results]


def custom_export(players):
    """One row per gaze sample; see eyetrack_shared.gaze_rows for the columns."""
    yield from gaze_rows(players, 'mpl_risk', 'Decision')
