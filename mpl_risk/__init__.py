"""Multiple Price List risk-elicitation task with webcam eye tracking."""

import json
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
    CALIBRATION_DELAY_MS = 500


class Subsession(BaseSubsession):
    pass


class Group(BaseGroup):
    pass


class Player(BasePlayer):
    choice_1 = models.IntegerField(choices=[[1, 'Option A'], [2, 'Option B']], label='Row 1', widget=widgets.RadioSelectHorizontal)
    choice_2 = models.IntegerField(choices=[[1, 'Option A'], [2, 'Option B']], label='Row 2', widget=widgets.RadioSelectHorizontal)
    choice_3 = models.IntegerField(choices=[[1, 'Option A'], [2, 'Option B']], label='Row 3', widget=widgets.RadioSelectHorizontal)
    choice_4 = models.IntegerField(choices=[[1, 'Option A'], [2, 'Option B']], label='Row 4', widget=widgets.RadioSelectHorizontal)
    choice_5 = models.IntegerField(choices=[[1, 'Option A'], [2, 'Option B']], label='Row 5', widget=widgets.RadioSelectHorizontal)
    choice_6 = models.IntegerField(choices=[[1, 'Option A'], [2, 'Option B']], label='Row 6', widget=widgets.RadioSelectHorizontal)
    choice_7 = models.IntegerField(choices=[[1, 'Option A'], [2, 'Option B']], label='Row 7', widget=widgets.RadioSelectHorizontal)
    choice_8 = models.IntegerField(choices=[[1, 'Option A'], [2, 'Option B']], label='Row 8', widget=widgets.RadioSelectHorizontal)
    choice_9 = models.IntegerField(choices=[[1, 'Option A'], [2, 'Option B']], label='Row 9', widget=widgets.RadioSelectHorizontal)
    choice_10 = models.IntegerField(choices=[[1, 'Option A'], [2, 'Option B']], label='Row 10', widget=widgets.RadioSelectHorizontal)
    selected_row = models.IntegerField()
    lottery_outcome = models.IntegerField()
    final_payoff = models.CurrencyField()

    eyetrack_consent = models.BooleanField(initial=False)
    eyetrack_calibration_rmse = models.FloatField(blank=True)
    eyetrack_sample_count = models.IntegerField(initial=0)
    eyetrack_gaze_data = models.LongStringField(blank=True)  # JSON array of {x, y, t, ...}
    # Outcome of WebEyeTrack initialization. One of:
    #   ok              — model loaded, real gaze samples
    #   no_consent      — participant did not grant camera access
    #   init_failed     — model failed to load; samples are mocked
    #   unknown         — page never reported a status (e.g. crash before init)
    eyetrack_init_status = models.StringField(initial='unknown')
    # First uncaught JS error during the tracked page (empty if no crash).
    # A non-empty value means sample collection may have stopped early.
    eyetrack_runtime_error = models.LongStringField(blank=True)


def get_safe_amount(row):
    increment = (C.SAFE_MAX - C.SAFE_MIN) / (C.NUM_CHOICES - 1)
    return C.SAFE_MIN + increment * (row - 1)


def calculate_payoff(player: Player):
    player.selected_row = random.randint(1, C.NUM_CHOICES)
    choice_field = f'choice_{player.selected_row}'
    choice = getattr(player, choice_field)
    if choice == 1:
        player.final_payoff = get_safe_amount(player.selected_row)
        player.lottery_outcome = 0
    else:
        if random.random() < C.LOTTERY_PROB:
            player.final_payoff = C.LOTTERY_HIGH
            player.lottery_outcome = 1
        else:
            player.final_payoff = C.LOTTERY_LOW
            player.lottery_outcome = 2
    player.payoff = player.final_payoff


def get_calibration_points():
    return [
        {'x': 10, 'y': 10}, {'x': 50, 'y': 10}, {'x': 90, 'y': 10},
        {'x': 10, 'y': 50}, {'x': 50, 'y': 50}, {'x': 90, 'y': 50},
        {'x': 10, 'y': 90}, {'x': 50, 'y': 90}, {'x': 90, 'y': 90},
    ]


class Consent(Page):
    form_model = 'player'
    form_fields = ['eyetrack_consent']


class Calibration(Page):
    form_model = 'player'
    form_fields = ['eyetrack_calibration_rmse']

    @staticmethod
    def vars_for_template(player: Player):
        return dict(num_points=len(get_calibration_points()))

    @staticmethod
    def js_vars(player: Player):
        return dict(
            calibration_points=get_calibration_points(),
            delay_ms=C.CALIBRATION_DELAY_MS,
        )


class Decision(Page):
    form_model = 'player'
    form_fields = [
        'choice_1', 'choice_2', 'choice_3', 'choice_4', 'choice_5',
        'choice_6', 'choice_7', 'choice_8', 'choice_9', 'choice_10',
        'eyetrack_sample_count', 'eyetrack_gaze_data',
        'eyetrack_init_status', 'eyetrack_runtime_error',
    ]

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
    def before_next_page(player: Player, timeout_happened):
        calculate_payoff(player)


class Results(Page):
    form_model = 'player'

    @staticmethod
    def vars_for_template(player: Player):
        safe_amount = get_safe_amount(player.selected_row)
        choice_field = f'choice_{player.selected_row}'
        selected_choice = getattr(player, choice_field)
        return dict(safe_amount=safe_amount, selected_choice=selected_choice)


page_sequence = [Consent, Calibration, Decision, Results]


def custom_export(players):
    """
    Long-format export of every gaze sample, one row per sample.
    Available in oTree's Data tab as the "custom" export.

    `is_mock` is rendered as 0/1 (rather than False/True) so it loads
    cleanly into pandas/R as a numeric column.
    """
    yield [
        'session_code', 'participant_code', 'page',
        'eyetrack_init_status', 'sample_index',
        'x', 'y', 'norm_x', 'norm_y',
        'gaze_state', 'confidence', 't_perf', 'timestamp', 'is_mock',
    ]

    for player in players:
        raw = player.eyetrack_gaze_data
        if not raw:
            continue
        try:
            samples = json.loads(raw)
        except (ValueError, TypeError):
            continue
        for i, s in enumerate(samples):
            yield [
                player.session.code,
                player.participant.code,
                'Decision',
                player.eyetrack_init_status,
                i,
                s.get('x'), s.get('y'),
                s.get('norm_x'), s.get('norm_y'),
                s.get('gaze_state'), s.get('confidence'),
                s.get('t_perf'), s.get('timestamp'),
                1 if s.get('is_mock') else 0,
            ]
