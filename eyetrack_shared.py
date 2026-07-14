"""
Shared pieces for adding webcam eye tracking to any oTree app in this project.

A task app needs four things, all small:

1. Fields on its Player model — copy the block below verbatim:

       eyetrack_sample_count = models.IntegerField(initial=0)
       eyetrack_gaze_data = models.LongStringField(blank=True)
       eyetrack_init_status = models.StringField(initial='unknown')
       eyetrack_calibration_restored = models.BooleanField(initial=False)
       eyetrack_viewport_width = models.IntegerField(initial=0)
       eyetrack_viewport_height = models.IntegerField(initial=0)
       eyetrack_viewport_changed = models.BooleanField(initial=False)
       eyetrack_rois = models.LongStringField(blank=True)
       eyetrack_runtime_error = models.LongStringField(blank=True)

2. Those fields appended to the tracked Page's `form_fields`:

       form_fields = ['your', 'task', 'fields'] + EYETRACK_FORM_FIELDS

3. The tracked Page's `js_vars` merged with `eyetrack_js_vars(player)`.

4. `{{ include 'eyetrack/tracked_page.html' }}` at the bottom of the tracked
   template, plus a `<video id="webcam-video">` element, `#tracking-status`,
   and `#gaze-dot` (see mpl_risk/Decision.html for the canonical example).

Mark any element whose location matters for analysis with
`data-eyetrack-roi="some-name"`; its on-screen rectangle is recorded alongside
the gaze samples so regions of interest can be mapped offline.

The session config must run the `eyetrack` app (consent + calibration) before
the task, and settings.py must declare the participant fields it writes:

       PARTICIPANT_FIELDS = [
           'eyetrack_consent',
           'eyetrack_calibration_rmse',
           'eyetrack_calibration_rmse_fraction',
       ]
"""

import json

# Appended to a tracked page's form_fields. The hidden inputs with these names
# live in eyetrack/tracked_page.html and are written by the tracker on submit.
EYETRACK_FORM_FIELDS = [
    'eyetrack_sample_count',
    'eyetrack_gaze_data',
    'eyetrack_init_status',
    'eyetrack_calibration_restored',
    'eyetrack_viewport_width',
    'eyetrack_viewport_height',
    'eyetrack_viewport_changed',
    'eyetrack_rois',
    'eyetrack_runtime_error',
]


def get_calibration_key(participant):
    """
    Where this participant's personalised gaze model is stored in the browser's
    IndexedDB. Keyed by participant so two people sharing a machine cannot
    inherit each other's calibration — and shared by every app in the session,
    which is what lets one calibration serve many tasks.
    """
    return f'webeyetrack-calib-{participant.code}'


def eyetrack_js_vars(player):
    """
    The js_vars every tracked page needs. Merge into the page's own dict.

    Consent is read via .get(): if the session config forgot to run the
    `eyetrack` app first, the participant never consented, and the tracker
    should report `no_consent` rather than the page crashing with a KeyError.
    """
    participant = player.participant
    return dict(
        calibration_key=get_calibration_key(participant),
        eyetrack_consent=bool(participant.vars.get('eyetrack_consent', False)),
    )


def gaze_rows(players, app_name, page_name):
    """
    Long-format gaze export: one row per sample, for one app's players.

    Each app's custom_export delegates here so every app exports the same
    columns and the `app`/`page` labels are always accurate:

        def custom_export(players):
            yield from gaze_rows(players, 'my_app', 'Decision')

    Columns:
      x, y            screen pixels, or empty when no face was detected
      norm_x, norm_y  the library's normalized point of gaze, in [-0.5, 0.5]
      gaze_state      'open' when a face was tracked; anything else means the
                      coordinates are empty rather than a real fixation
      clipped         1 when the estimate was saturated at a screen edge. The
                      tracker clips gaze to the screen, so such a sample is
                      censored: the participant was looking further out.
      t_perf          milliseconds since page load (monotonic; use this)
      frame_time      the camera's clock, in seconds since the stream started
    """
    yield [
        'session_code', 'participant_code', 'app', 'page',
        'eyetrack_init_status', 'sample_index',
        'x', 'y', 'norm_x', 'norm_y',
        'gaze_state', 'clipped', 't_perf', 'frame_time',
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
                app_name,
                page_name,
                player.eyetrack_init_status,
                i,
                s.get('x'), s.get('y'),
                s.get('norm_x'), s.get('norm_y'),
                s.get('gaze_state'),
                1 if s.get('clipped') else 0,
                s.get('t_perf'), s.get('frame_time'),
            ]
