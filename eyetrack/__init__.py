"""
Webcam eye-tracking setup: camera consent, then calibration.

Run this app once at the start of any session, before the task apps:

    app_sequence = ['eyetrack', 'your_task']

The participant calibrates here; the personalised gaze model is saved in the
browser under a key derived from the participant code, and every later tracked
page — in any app — restores it. The outcome is copied onto the participant
(`eyetrack_consent`, `eyetrack_calibration_rmse`, and the screen-relative
`eyetrack_calibration_rmse_fraction`) so task apps can read it without
depending on this app's models.
"""

from otree.api import (
    models,
    BaseConstants,
    BaseSubsession,
    BaseGroup,
    BasePlayer,
    Page,
)

from eyetrack_shared import get_calibration_key

doc = __doc__


class C(BaseConstants):
    NAME_IN_URL = 'eyetrack'
    PLAYERS_PER_GROUP = None
    NUM_ROUNDS = 1
    CALIBRATION_DELAY_MS = 500
    # The tracker keeps a support set of this size. Passed through to the
    # library so it matches the number of points we actually present.
    MAX_CALIBRATION_POINTS = 5


class Subsession(BaseSubsession):
    pass


class Group(BaseGroup):
    pass


class Player(BasePlayer):
    eyetrack_consent = models.BooleanField(initial=False)
    # Error in pixels on the held-out validation points. Empty means the
    # participant skipped calibration: their gaze is from an uncalibrated model.
    eyetrack_calibration_rmse = models.FloatField(blank=True)
    # The same error as a fraction of the screen diagonal. Pixels are not
    # comparable across participants' monitors; this is.
    eyetrack_calibration_rmse_fraction = models.FloatField(blank=True)


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


class Consent(Page):
    form_model = 'player'
    form_fields = ['eyetrack_consent']

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        # Task apps read consent from the participant, not from this app's
        # Player model — that is what makes them independent of this app.
        player.participant.eyetrack_consent = bool(player.eyetrack_consent)


class Calibration(Page):
    form_model = 'player'
    form_fields = ['eyetrack_calibration_rmse', 'eyetrack_calibration_rmse_fraction']

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
            calibration_key=get_calibration_key(player.participant),
            # The server-side record of consent. Relying on sessionStorage alone
            # silently disables tracking for a participant who consented but
            # resumed in a new tab.
            eyetrack_consent=bool(player.participant.eyetrack_consent),
        )

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        player.participant.eyetrack_calibration_rmse = player.field_maybe_none(
            'eyetrack_calibration_rmse'
        )
        player.participant.eyetrack_calibration_rmse_fraction = player.field_maybe_none(
            'eyetrack_calibration_rmse_fraction'
        )


page_sequence = [Consent, Calibration]
