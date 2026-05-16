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
from functions import close_relay, videoProcessing
from identifier import Identifier

APP_DIR = Path(__file__).resolve().parent

app = Sanic(__name__)


def truthy(value):
    return str(value).strip().lower() in ('1', 'true', 'yes', 'y', 'on')


def camera_backend():
    backend = os.environ.get('DOORLOCK_CAMERA_BACKEND', 'auto').strip().lower()
    if truthy(os.environ.get('DOORLOCK_DISABLE_CAMERA', '')):
        backend = 'mock'
    return backend


def stream_response(streaming_fn, content_type):
    if hasattr(sanic_response, 'stream'):
        return sanic_response.stream(streaming_fn, content_type=content_type)
    return sanic_response.ResponseStream(streaming_fn, content_type=content_type)


@app.route('/')
async def index(request):
    return await sanic_response.file(str(APP_DIR / 'index' / 'index.html'))


@app.route('/status')
async def status(request):
    backend = camera_backend()
    return sanic_response.json({
        'cameraBackend': backend,
        'mockMode': backend in ('mock', 'none', 'disabled'),
        'port': int(os.environ.get('DOORLOCK_PORT', '80')),
    })


@app.route('/image/<uid>')
async def getImage(request, uid):
    img_loc = request.app.ctx.identifier.getImageLocation(uid)

    if not img_loc:
        return sanic_response.text('not valid')

    return await sanic_response.file(img_loc)


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
    asyncio.create_task(videoProcessing(app.ctx.identifier, False))


@app.listener('before_server_stop')
async def server_stop(app):
    if hasattr(app.ctx, 'identifier'):
        app.ctx.identifier.quit()
    close_relay()


if __name__ == "__main__":

    app.static('/', str(APP_DIR / 'index'))
    app.run(host='0.0.0.0', port=int(os.environ.get('DOORLOCK_PORT', '80')))
