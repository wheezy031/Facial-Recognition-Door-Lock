# Troubleshooting

## Check Service Status

```bash
sudo /etc/init.d/doorlock status
tail -n 120 /var/log/doorlock.log
curl http://127.0.0.1:8080/status
```

The `/status` response should show:

```json
{
  "cameraThreadAlive": true,
  "cameraBackend": "rpicam"
}
```

## Vue Runtime 404 or `Vue is not defined`

Make sure this file exists on the Pi:

```text
src/index/vue.global.prod.js
```

Check from the Pi:

```bash
curl -I http://127.0.0.1:8080/vue.global.prod.js
```

It should return `200`, not `404`.

## Face Embedding Model Missing

Error:

```text
Face embedding model not found
```

Download the model:

```bash
mkdir -p src/models
curl -L -o src/models/face_embedder.tflite \
  https://raw.githubusercontent.com/hugocornellier/face_detection_tflite/main/assets/models/mobilefacenet.tflite
sudo /etc/init.d/doorlock restart
```

## `picamera2` Missing

Log:

```text
Picamera2 import failed, falling back to rpicam-vid
No module named 'picamera2'
```

This is acceptable if you are using `DOORLOCK_CAMERA_BACKEND="rpicam"`. The app will use the `rpicam-vid` command-line backend.

Install the command-line camera tools:

```bash
sudo apt-get install -y --no-install-recommends rpicam-apps
```

## Camera Worker Stopped

If the UI shows `Camera worker stopped`, check logs:

```bash
tail -n 120 /var/log/doorlock.log
```

Common causes:

- camera not connected
- wrong backend
- camera already in use
- missing `rpicam-vid`
- USB camera index is wrong

Restart:

```bash
sudo /etc/init.d/doorlock restart
```

## Black or Delayed Stream

Try lower latency settings:

```bash
sudo sed -i '/^DOORLOCK_CAMERA_WIDTH=/d;/^DOORLOCK_CAMERA_HEIGHT=/d;/^DOORLOCK_CAMERA_FPS=/d;/^DOORLOCK_RECOGNITION_FPS=/d;/^DOORLOCK_STREAM_FPS=/d' /etc/default/doorlock
printf 'DOORLOCK_CAMERA_WIDTH="640"\nDOORLOCK_CAMERA_HEIGHT="480"\nDOORLOCK_CAMERA_FPS="5"\nDOORLOCK_RECOGNITION_FPS="5"\nDOORLOCK_STREAM_FPS="5"\n' | sudo tee -a /etc/default/doorlock
sudo /etc/init.d/doorlock restart
```

## GPIO Busy

Error:

```text
lgpio.error: 'GPIO busy'
```

Check for duplicate processes:

```bash
pgrep -af doorlock.py
```

Stop the service and any stale process:

```bash
sudo /etc/init.d/doorlock stop
sudo pkill -f doorlock.py
sudo /etc/init.d/doorlock start
```

## Python Package Missing

Check which Python the service uses:

```bash
grep '^DOORLOCK_PYTHON_BIN=' /etc/default/doorlock
```

Install packages into that environment, not system Python.

Example:

```bash
/home/pi/conda-envs/fr-doorlock-py312/bin/python -m pip install sanic gpiozero lgpio opencv-python-headless mediapipe ai-edge-litert
```

## TensorFlow Lite CPU Warnings

Messages like these are usually informational:

```text
Error in cpuinfo: prctl(PR_SVE_GET_VL) failed
INFO: Created TensorFlow Lite XNNPACK delegate for CPU.
Feedback manager requires a model with a single signature inference.
```

If the model test shows an input tensor and output tensor, the embedding model is being used.
