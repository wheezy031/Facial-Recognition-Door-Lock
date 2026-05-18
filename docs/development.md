# Development Notes

This fork replaces the original `face_recognition`/`dlib` stack with MediaPipe face detection and a TensorFlow Lite embedding model.

## Main Components

```text
src/doorlock.py
```

Sanic web server, static UI serving, API routes, status endpoint, and worker thread lifecycle.

```text
src/functions.py
```

Camera backends, relay control, door state, and video processing loop.

```text
src/identifier.py
```

Identity storage, matching, samples, allow/deny state, merge/delete, and stream image state.

```text
src/recognizer.py
```

MediaPipe face detection and TensorFlow Lite embedding inference.

```text
src/index/
```

Buildless Vue 3 web UI. Vue is vendored as `vue.global.prod.js` so the Pi does not need internet access to render the UI.

## Threading Model

Sanic runs the web API and UI.

Camera and recognition work runs in a background thread:

```text
Sanic web server
  - /status
  - /names
  - /merge
  - /sample
  - /door
  - /mainview

Camera/recognition worker
  - camera capture
  - frame scaling
  - MediaPipe detection
  - TFLite embedding
  - identity matching
  - JPEG stream frame updates
```

The app intentionally avoids multiple Sanic workers because each worker could try to open the camera, GPIO relay, and model state.

`Identifier` uses an `RLock` around shared state so API calls can safely merge/delete/update identities while the recognition thread is running.

## API Routes

| Route | Method | Purpose |
| --- | --- | --- |
| `/` | GET | Web UI |
| `/status` | GET | Service, camera, stream, and door state |
| `/mainview` | GET | MJPEG camera stream |
| `/names` | GET | Known people |
| `/image/<uid>` | GET | Profile image |
| `/access` | POST | Toggle allowed/denied |
| `/set` | POST | Set friendly name |
| `/delete` | POST | Delete people |
| `/merge` | POST | Merge identities |
| `/sample` | POST | Add a live face sample |
| `/door` | POST | Manual lock/unlock |

## Frontend

The UI uses Vue 3 without a build step:

```html
<script src="/vue.global.prod.js"></script>
```

The backend explicitly serves the Vue runtime at:

```text
/vue.global.prod.js
```

This avoids depending on a CDN at runtime.

## Local Checks

Python syntax:

```bash
PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile src/doorlock.py src/functions.py src/identifier.py src/recognizer.py
```

Shell syntax:

```bash
sh -n setup.sh
sh -n src/doorlock.init.sh
```

JavaScript syntax:

```bash
node -e "const fs=require('fs'); const html=fs.readFileSync('src/index/index.html','utf8'); const scripts=[...html.matchAll(/<script(?: [^>]*)?>([\\s\\S]*?)<\\/script>/g)].map(m=>m[1]).filter(Boolean); for (const script of scripts) new Function(script); console.log('inline js ok');"
```

Whitespace:

```bash
git diff --check
```

## Future Improvements

- Add a sample-management modal for reviewing, promoting, and removing visual samples.
- Add an optional physical lock position sensor.
- Add richer health checks for camera and model inference.
- Add systemd service support alongside the init script.
- Add automated tests for identity merge/sample behavior.
