import secrets
from os import environ

SESSION_CONFIG_DEFAULTS = dict(real_world_currency_per_point=1.0, participation_fee=0.0)
SESSION_CONFIGS = [dict(name='mpl_risk', num_demo_participants=1, app_sequence=['mpl_risk'])]
LANGUAGE_CODE = 'en'
REAL_WORLD_CURRENCY_CODE = 'EUR'
USE_POINTS = False
DEMO_PAGE_INTRO_HTML = ''
PARTICIPANT_FIELDS = []
SESSION_FIELDS = []
THOUSAND_SEPARATOR = ''
ROOMS = []

ADMIN_USERNAME = 'admin'
# Set OTREE_ADMIN_PASSWORD in your environment for any non-local deployment.
ADMIN_PASSWORD = environ.get('OTREE_ADMIN_PASSWORD')

# Cookie-signing secret.
#
# A per-process fallback is fine for `otree devserver`, but in production it is
# a trap: every uvicorn worker would generate a different key, so a cookie
# signed by one worker is rejected by the next, logging participants out at
# random mid-study. Refuse to start rather than fail that way.
_secret_key = environ.get('OTREE_SECRET_KEY')
if not _secret_key:
    if environ.get('OTREE_PRODUCTION'):
        raise RuntimeError(
            'OTREE_SECRET_KEY must be set when OTREE_PRODUCTION is on. '
            'Generate one with:  python -c "import secrets; print(secrets.token_urlsafe(50))"'
        )
    # Local development. Restarting invalidates signed cookies, which is fine.
    _secret_key = secrets.token_urlsafe(50)
SECRET_KEY = _secret_key

# if an app is included in SESSION_CONFIGS, you don't need to list it here
INSTALLED_APPS = ['otree']
