"""
Minimal ASGI wrapper that mounts WebEyeTrack's TF.js model files at `/web/`.

Why this exists
---------------
WebEyeTrack 0.0.2 hardcodes its model URL as `${origin}/web/model.json` and
loads it inside a Web Worker (the model lives in TF.js, which TF.js spins up
in a worker). Workers have their own global scope, so a `window.fetch` shim
in the main thread cannot rewrite `/web/...` to `/static/web/...` for the
worker's requests — they have to be handled at the network layer.

This wrapper does exactly one thing: serve `_static/web/*` at `/web/*`.
Everything else falls through to oTree's normal ASGI app.

Usage
-----
    uvicorn asgi:application --reload --port 8000

For deployment, set the Procfile to start uvicorn instead of `otree
prodserver` so this wrapper is in the request path.
"""

import os
from pathlib import Path

# Configure Django settings BEFORE importing oTree.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')

from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

from otree.asgi import app as otree_app

PROJECT_ROOT = Path(__file__).parent
WEBEYETRACK_MODEL_DIR = PROJECT_ROOT / '_static' / 'web'


class CustomASGIWrapper:
    """Mounts /web/* to _static/web/, otherwise delegates to oTree."""

    def __init__(self):
        self.web_mount = Starlette(routes=[
            Mount('/web', app=StaticFiles(directory=str(WEBEYETRACK_MODEL_DIR)), name='web'),
        ])
        self.otree_app = otree_app

    async def __call__(self, scope, receive, send):
        if scope.get('path', '').startswith('/web/'):
            await self.web_mount(scope, receive, send)
        else:
            await self.otree_app(scope, receive, send)


application = CustomASGIWrapper()
