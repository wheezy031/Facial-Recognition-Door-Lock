# Facial Recognition Door Lock

This project uses a Raspberry Pi camera, MediaPipe face detection, a TensorFlow Lite face embedding model, and a relay-controlled door strike to provide a small web-managed access control system.

![hero](hero.jpg)

The web UI shows the live camera feed, detected people, identity samples, allow/deny controls, merge tools, manual lock controls, and camera/worker health.

## What It Does

- Detects faces from a Pi camera or USB webcam.
- Creates a saved identity for new faces.
- Lets you allow or deny each identity from the browser.
- Unlocks the door relay when an allowed identity is recognised.
- Stores multiple face embeddings per person for more reliable matching.
- Runs camera and recognition work in a background worker so the web UI remains responsive.

## Quick Start

On Raspberry Pi 64-bit systems, first create the Python 3.12 conda environment described in [Raspberry Pi setup](docs/pi-setup.md). MediaPipe wheels are not available for every system Python version.

```bash
git clone https://github.com/Jaycar-Electronics/Facial-Recognition-Door-Lock
cd Facial-Recognition-Door-Lock
DOORLOCK_PYTHON_BIN="$HOME/conda-envs/fr-doorlock-py312/bin/python" ./setup.sh
```

Download the face embedding model:

```bash
mkdir -p src/models
curl -L -o src/models/face_embedder.tflite \
  https://raw.githubusercontent.com/hugocornellier/face_detection_tflite/main/assets/models/mobilefacenet.tflite
```

Start or restart the service:

```bash
sudo /etc/init.d/doorlock restart
```

Open the web UI:

```text
http://<raspberry-pi-ip>:8080/
```

## Documentation

- [Hardware and assembly](docs/hardware.md)
- [Raspberry Pi setup](docs/pi-setup.md)
- [Camera backends and tuning](docs/camera-backends.md)
- [Identity model and samples](docs/identity-model.md)
- [Using the web UI](docs/operation.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Development notes](docs/development.md)

## Project Layout

```text
src/doorlock.py          Sanic web server and API routes
src/functions.py         camera, relay, and video processing logic
src/identifier.py        identity storage, matching, merge, and samples
src/recognizer.py        MediaPipe detection and TFLite embeddings
src/index/              Vue 3 no-build web UI
src/models/             local model files
src/people/             local identity data
```

## Status

This fork has been updated from the original `face_recognition`/`dlib` approach to MediaPipe plus TensorFlow Lite, with a buildless Vue 3 UI and a threaded camera/recognition backend.
