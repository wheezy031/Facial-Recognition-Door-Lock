#!/usr/bin/python3
'''
This script serves as the main to the doorlock project;

it will 
- serve a SANIC.py webserver, on port 80; serving static files from ./index
- start up the `identifier` object; which is our facial-recognition program in ./identifier.py
- connect the two together, so that the webserver is operating on the ./identifier.py

'''

import asyncio
import os
from pathlib import Path

from sanic import Sanic
import sanic.response as sanic_response
from functions import close_relay, doorState, lockDoor, unlockDoor, videoProcessing
from identifier import Identifier

APP_DIR = Path(__file__).resolve().parent

app = Sanic(__name__)


def truthy(value):
    return str(value).strip().lower() in ('1', 'true', 'yes', 'y', 'on')


def camera_backend():
    backend = os.environ.get('DOORLOCK_CAMERA_BACKEND', 'rpicam').strip().lower()
    if truthy(os.environ.get('DOORLOCK_DISABLE_CAMERA', '')):
        backend = 'mock'
    return backend


def stream_response(streaming_fn, content_type):
    if hasattr(sanic_response, 'stream'):
        return sanic_response.stream(streaming_fn, content_type=content_type)
    return sanic_response.ResponseStream(streaming_fn, content_type=content_type)


def unlock_duration(value):
    if value is None:
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        raise ValueError('duration must be a number')
    if seconds <= 0 or seconds > 60:
        raise ValueError('duration must be between 0 and 60 seconds')
    return seconds


@app.route('/')
async def index(request):
    return await sanic_response.file(str(APP_DIR / 'index' / 'index.html'))


@app.route('/vue.global.prod.js')
async def vue_runtime(request):
    return await sanic_response.file(str(APP_DIR / 'index' / 'vue.global.prod.js'))


@app.route('/status')
async def status(request):
    backend = camera_backend()
    return sanic_response.json({
        'cameraBackend': backend,
        'cameraDevice': os.environ.get('DOORLOCK_CAMERA_DEVICE', ''),
        'cameraFourcc': os.environ.get('DOORLOCK_CAMERA_FOURCC', 'MJPG'),
        'cameraIndex': int(os.environ.get('DOORLOCK_CAMERA_INDEX', '0')),
        'mockMode': backend in ('mock', 'none', 'disabled'),
        'port': int(os.environ.get('DOORLOCK_PORT', '80')),
        'processingScale': float(os.environ.get('DOORLOCK_PROCESSING_SCALE', '0.5')),
        'streamScale': float(os.environ.get('DOORLOCK_STREAM_SCALE', '1.0')),
        'door': doorState(),
    })


@app.route('/image/<uid>')
async def getImage(request, uid):
    img_loc = request.app.ctx.identifier.getImageLocation(uid)

    if not img_loc:
        return sanic_response.text('not valid')

    return await sanic_response.file(img_loc)


# manual door control
@app.route('/door', methods=['POST'])
async def door(request):
    data = request.json
    if data is None or type(data) is not dict:
        return sanic_response.json({'ok': False, 'error': 'wrong data'}, status=400)

    action = str(data.get('action', '')).strip().lower()

    try:
        if action == 'unlock':
            state = unlockDoor(unlock_duration(data.get('duration')))
            return sanic_response.json({'ok': True, 'action': 'unlock', 'door': state})
        if action == 'lock':
            state = lockDoor()
            return sanic_response.json({'ok': True, 'action': 'lock', 'door': state})
    except ValueError as e:
        return sanic_response.json({'ok': False, 'error': str(e)}, status=400)
    except Exception as e:
        return sanic_response.json({'ok': False, 'error': str(e)}, status=500)

    return sanic_response.json({'ok': False, 'error': 'action must be lock or unlock'}, status=400)


# manage allowed people
@app.route('/access', methods=['GET', 'POST'])
async def allowed(request):
    if request.method == 'POST':  # POSTING a list of new users to add
        data = request.json
        if data is None:
            return sanic_response.text('no data')

        uid = None
        try:
            uid = data['uid']
        except Exception:
            return sanic_response.text('wrong data')

        return sanic_response.text(request.app.ctx.identifier.toggleAccess(uid))

    return sanic_response.text('must use POST request')

# delete users
@app.route('/delete', methods=['GET', 'POST'])
async def delete(request):
    if request.method == 'POST':
        data = request.json
        if data is None or type(data) is not list:
            return

        for user in data:
            request.app.ctx.identifier.delete(user)
        return sanic_response.text('called delete')

    return sanic_response.text('must use POST request')


# merge duplicate detected people into a single identity
@app.route('/merge', methods=['POST'])
async def merge(request):
    data = request.json
    if data is None or type(data) is not dict:
        return sanic_response.json({'ok': False, 'error': 'wrong data'}, status=400)

    target = data.get('target')
    sources = data.get('sources')
    uids = data.get('uids')

    if sources is None and isinstance(uids, list):
        if target is None and uids:
            target = uids[0]
        sources = [uid for uid in uids if uid != target]

    if not isinstance(sources, list):
        return sanic_response.json({'ok': False, 'error': 'sources must be a list'}, status=400)
    if not isinstance(target, str):
        return sanic_response.json({'ok': False, 'error': 'target must be a person id'}, status=400)
    if any(not isinstance(uid, str) for uid in sources):
        return sanic_response.json({'ok': False, 'error': 'sources must contain person ids'}, status=400)

    result = request.app.ctx.identifier.merge(target, sources)
    return sanic_response.json(result, status=200 if result.get('ok') else 400)


# capture another live embedding sample for an existing person
@app.route('/sample', methods=['POST'])
async def sample(request):
    data = request.json
    if data is None or type(data) is not dict:
        return sanic_response.json({'ok': False, 'error': 'wrong data'}, status=400)

    uid = data.get('uid')
    if not isinstance(uid, str):
        return sanic_response.json({'ok': False, 'error': 'uid must be a person id'}, status=400)

    result = request.app.ctx.identifier.captureSample(uid)
    return sanic_response.json(result, status=200 if result.get('ok') else 400)


# provide JSON of names, and friendly names
@app.route('/names')
async def returnNames(request):
    return sanic_response.json(request.app.ctx.identifier.getNames())

# route for setting friendly names
@app.route('/set', methods=['POST'])
async def set(request):
    data = request.json
    if 'uid' not in data.keys():
        return sanic_response.text('need uid')
    if 'name' not in data.keys():
        return sanic_response.text('need name')

    request.app.ctx.identifier.setName(data['uid'], data['name'])

    return sanic_response.text('ok')

# mainview image stream
@app.route('/mainview')
async def view(request):
    return stream_response(
        request.app.ctx.identifier.stream,
        content_type='multipart/x-mixed-replace; boundary=frame',
    )


@app.listener('before_server_start')
async def server_prepare(app):
    app.ctx.identifier = Identifier()


@app.listener('after_server_start')
async def server_start(app):
    app.ctx.video_task = asyncio.create_task(videoProcessing(app.ctx.identifier, False))


@app.listener('before_server_stop')
async def server_stop(app):
    if hasattr(app.ctx, 'identifier'):
        app.ctx.identifier.quit()
    task = getattr(app.ctx, 'video_task', None)
    if task is not None and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    close_relay()


if __name__ == "__main__":

    app.static('/', str(APP_DIR / 'index'))
    app.run(host='0.0.0.0', port=int(os.environ.get('DOORLOCK_PORT', '80')))
