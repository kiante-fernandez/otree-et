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

# In production, set OTREE_SECRET_KEY in the environment. The fallback below
# generates a random key for local development only — restarts will invalidate
# any signed cookies, which is fine for `otree devserver`.
SECRET_KEY = environ.get('OTREE_SECRET_KEY') or secrets.token_urlsafe(50)

# if an app is included in SESSION_CONFIGS, you don't need to list it here
INSTALLED_APPS = ['otree']
