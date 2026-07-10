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
    # The tracker keeps a support set of this size. Passed through to the
    # library so it matches the number of points we actually present.
    MAX_CALIBRATION_POINTS = 5

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

    eyetrack_consent = models.BooleanField(initial=False)
    # Error in pixels on the held-out validation points. Empty means the
    # participant skipped calibration: their gaze is from an uncalibrated model.
    eyetrack_calibration_rmse = models.FloatField(blank=True)
    eyetrack_sample_count = models.IntegerField(initial=0)
    eyetrack_gaze_data = models.LongStringField(blank=True)  # JSON array of samples
    # Outcome of eye-tracker initialization. One of:
    #   ok           — the gaze model loaded and samples were collected
    #   no_consent   — participant did not grant camera access
    #   init_failed  — the tracker could not start; no samples were recorded
    #   unknown      — the page never reported a status (e.g. crash before init)
    eyetrack_init_status = models.StringField(initial='unknown')
    # Whether the tracked page measured gaze with the model this participant
    # calibrated, or with the uncalibrated base model. False means the gaze
    # below is not calibrated to them, whatever eyetrack_calibration_rmse says.
    eyetrack_calibration_restored = models.BooleanField(initial=False)
    # First uncaught JS error during the tracked page (empty if no crash).
    # A non-empty value means sample collection may have stopped early.
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


def get_calibration_points():
    """
    Points the model is adapted to, as percentages of the viewport.

    Exactly C.MAX_CALIBRATION_POINTS of them: the tracker keeps a support set of
    that size and evicts the oldest, so a longer list would silently discard the
    points clicked first.
    """
    return [
        {'x': 10, 'y': 10}, {'x': 90, 'y': 10},
        {'x': 50, 'y': 50},
        {'x': 10, 'y': 90}, {'x': 90, 'y': 90},
    ]


def get_validation_points():
    """
    Points used only to measure error, never to adapt the model.

    Calibration error measured on the same points the model was fit to is
    optimistic by construction. These are held out, so `eyetrack_calibration_rmse`
    is an honest estimate of accuracy on unseen screen locations.
    """
    return [
        {'x': 50, 'y': 10},
        {'x': 10, 'y': 50}, {'x': 90, 'y': 50},
        {'x': 50, 'y': 90},
    ]


def get_calibration_key(player: Player):
    """
    Where this participant's personalised model is stored in the browser's
    IndexedDB. Keyed by participant so two people sharing a machine cannot
    inherit each other's calibration.
    """
    return f'webeyetrack-calib-{player.participant.code}'


class Consent(Page):
    form_model = 'player'
    form_fields = ['eyetrack_consent']


class Calibration(Page):
    form_model = 'player'
    form_fields = ['eyetrack_calibration_rmse']

    @staticmethod
    def vars_for_template(player: Player):
        return dict(
            num_points=len(get_calibration_points()) + len(get_validation_points()),
        )

    @staticmethod
    def js_vars(player: Player):
        return dict(
            calibration_points=get_calibration_points(),
            validation_points=get_validation_points(),
            delay_ms=C.CALIBRATION_DELAY_MS,
            max_calibration_points=C.MAX_CALIBRATION_POINTS,
            calibration_key=get_calibration_key(player),
            # The server-side record of consent. Relying on sessionStorage alone
            # silently disables tracking for a participant who consented but
            # resumed in a new tab.
            eyetrack_consent=bool(player.eyetrack_consent),
        )


class Decision(Page):
    form_model = 'player'
    form_fields = [f'choice_{row}' for row in range(1, C.NUM_CHOICES + 1)] + [
        'eyetrack_sample_count', 'eyetrack_gaze_data',
        'eyetrack_init_status', 'eyetrack_calibration_restored',
        'eyetrack_runtime_error',
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
    def js_vars(player: Player):
        return dict(
            calibration_key=get_calibration_key(player),
            eyetrack_consent=bool(player.eyetrack_consent),
        )

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        calculate_payoff(player)


class Results(Page):

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

    Columns:
      x, y            screen pixels, or empty when no face was detected
      norm_x, norm_y  the library's normalized point of gaze, in [-0.5, 0.5]
      gaze_state      'open' when a face was tracked; anything else means the
                      coordinates are empty rather than a real fixation
      t_perf          milliseconds since page load (monotonic; use this)
      frame_time      the camera's clock, in seconds since the stream started
    """
    yield [
        'session_code', 'participant_code', 'page',
        'eyetrack_init_status', 'sample_index',
        'x', 'y', 'norm_x', 'norm_y',
        'gaze_state', 't_perf', 'frame_time',
    ]

    for player in players:
        raw = player.eyetrack_gaze_data
        if not raw:
            continue
        try:
            samples = json.loads(raw)
        except (ValueError, TypeError):
            continue
        # eyetrack_gaze_data is written by the participant's browser. Anything
        # that parses as JSON reaches here, so check the shape too: a bare
        # number, string, or object would otherwise raise out of this generator
        # and abort the export for every participant in the session.
        if not isinstance(samples, list):
            continue
        for i, s in enumerate(samples):
            if not isinstance(s, dict):
                continue
            yield [
                player.session.code,
                player.participant.code,
                'Decision',
                player.eyetrack_init_status,
                i,
                s.get('x'), s.get('y'),
                s.get('norm_x'), s.get('norm_y'),
                s.get('gaze_state'),
                s.get('t_perf'), s.get('frame_time'),
            ]
