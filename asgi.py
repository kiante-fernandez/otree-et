"""
Custom ASGI application that wraps oTree to add custom routes.

oTree 5+ uses Starlette's ASGI routing which ignores Django's ROOT_URLCONF.
This wrapper intercepts specific paths before they reach oTree.

Usage:
    uvicorn asgi:application --reload --port 8000
"""

import json
import os
from datetime import datetime
from pathlib import Path

# Configure Django settings BEFORE importing oTree
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')

from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import JSONResponse

# Import oTree's ASGI application (after Django settings are configured)
from otree.asgi import app as otree_app

# Project paths
PROJECT_ROOT = Path(__file__).parent
STATIC_WEB_DIR = PROJECT_ROOT / '_static' / 'web'
GAZE_DATA_DIR = PROJECT_ROOT / 'gaze_data'


def get_gaze_file_path(participant_code: str, session_code: str) -> Path:
    """Get the path to the gaze data file for a participant."""
    gaze_dir = GAZE_DATA_DIR / participant_code
    gaze_dir.mkdir(parents=True, exist_ok=True)
    return gaze_dir / f'{session_code}.ndjson'


async def record_gaze(request: Request) -> JSONResponse:
    """
    POST endpoint at /record_gaze/
    Receives JSON with participant_code, session_code, samples array.
    Writes to gaze_data/{participant_code}/{session_code}.ndjson
    """
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({'ok': False, 'error': 'Invalid JSON'}, status_code=400)

    participant_code = data.get('participant_code')
    session_code = data.get('session_code')
    samples = data.get('samples', [])
    page = data.get('page', 'unknown')

    if not participant_code or not session_code:
        return JSONResponse(
            {'ok': False, 'error': 'Missing participant_code or session_code'},
            status_code=400
        )

    file_path = get_gaze_file_path(participant_code, session_code)
    t_received = datetime.utcnow().isoformat() + 'Z'

    with open(file_path, 'a') as f:
        # Write batch metadata
        batch_meta = {
            '_type': 'batch_meta',
            'page': page,
            'sample_count': len(samples),
            't_received': t_received
        }
        f.write(json.dumps(batch_meta) + '\n')

        # Write each sample
        for sample in samples:
            sample['_type'] = 'sample'
            sample['_t_received'] = t_received
            f.write(json.dumps(sample) + '\n')

    return JSONResponse({'ok': True, 'received': len(samples)})


async def record_event(request: Request) -> JSONResponse:
    """
    POST endpoint at /record_event/
    Receives JSON with participant_code, session_code, event_type.
    Appends event to the same NDJSON file.
    """
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({'ok': False, 'error': 'Invalid JSON'}, status_code=400)

    participant_code = data.get('participant_code')
    session_code = data.get('session_code')
    event_type = data.get('event_type')
    page = data.get('page', 'unknown')

    if not participant_code or not session_code or not event_type:
        return JSONResponse(
            {'ok': False, 'error': 'Missing required fields'},
            status_code=400
        )

    file_path = get_gaze_file_path(participant_code, session_code)
    t_received = datetime.utcnow().isoformat() + 'Z'

    event_record = {
        '_type': 'event',
        'event_type': event_type,
        'page': page,
        't_received': t_received
    }

    with open(file_path, 'a') as f:
        f.write(json.dumps(event_record) + '\n')

    return JSONResponse({'ok': True})


class CustomASGIWrapper:
    """
    ASGI wrapper that handles custom routes before delegating to oTree.

    Routes handled:
    - /web/* -> Serves files from _static/web/ (for WebEyeTrack model)
    - /record_gaze/ -> POST endpoint for gaze data
    - /record_event/ -> POST endpoint for events
    - Everything else -> oTree
    """

    def __init__(self):
        # Create a Starlette app for our custom routes
        self.custom_app = Starlette(
            routes=[
                Route('/record_gaze/', record_gaze, methods=['POST']),
                Route('/record_event/', record_event, methods=['POST']),
                Mount('/web', app=StaticFiles(directory=str(STATIC_WEB_DIR)), name='web'),
            ]
        )
        self.otree_app = otree_app

    async def __call__(self, scope, receive, send):
        path = scope.get('path', '')

        # Handle our custom routes
        if path.startswith('/web/') or path in ['/record_gaze/', '/record_event/']:
            await self.custom_app(scope, receive, send)
        else:
            # Delegate to oTree for everything else
            await self.otree_app(scope, receive, send)


# Create the application instance
application = CustomASGIWrapper()
