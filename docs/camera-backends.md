# Camera Backends and Tuning

The app supports Raspberry Pi cameras, USB webcams, and mock mode.

## Defaults

The default backend is the Raspberry Pi command-line camera backend:

```bash
DOORLOCK_CAMERA_BACKEND="rpicam"
DOORLOCK_CAMERA_FPS="10"
DOORLOCK_RECOGNITION_FPS="3"
DOORLOCK_STREAM_FPS="10"
```

The web server runs separately from the camera/recognition worker thread, so API calls and the UI remain responsive while frames are processed.

## Raspberry Pi Camera

For the Raspberry Pi Camera Module, leave `DOORLOCK_CAMERA_BACKEND` as `rpicam`. The app uses `rpicam-vid` or `libcamera-vid`.

When running from a conda Python environment, the command-line camera backend is usually the most reliable option because it avoids importing Picamera2 into the conda Python process:

```bash
sudo apt-get install -y --no-install-recommends rpicam-apps
```

Set the Pi camera backend:

```bash
sudo sed -i '/^DOORLOCK_CAMERA_BACKEND=/d' /etc/default/doorlock
printf 'DOORLOCK_CAMERA_BACKEND="rpicam"\n' | sudo tee -a /etc/default/doorlock
sudo /etc/init.d/doorlock restart
```

## USB Webcam

For a USB webcam, use the OpenCV backend and set the camera index:

```bash
sudo sed -i '/^DOORLOCK_CAMERA_BACKEND=/d;/^DOORLOCK_CAMERA_INDEX=/d;/^DOORLOCK_CAMERA_DEVICE=/d;/^DOORLOCK_CAMERA_FOURCC=/d' /etc/default/doorlock
printf 'DOORLOCK_CAMERA_BACKEND="opencv"\nDOORLOCK_CAMERA_INDEX="0"\nDOORLOCK_CAMERA_FOURCC="MJPG"\n' | sudo tee -a /etc/default/doorlock
sudo /etc/init.d/doorlock restart
```

If index `0` is not the USB camera, test indexes:

```bash
DOORLOCK_PYTHON="$HOME/conda-envs/fr-doorlock-py312/bin/python"

"$DOORLOCK_PYTHON" - <<'PY'
import cv2

for index in range(5):
    cap = cv2.VideoCapture(index)
    ok, frame = cap.read()
    print(index, 'opened', cap.isOpened(), 'frame', ok, None if frame is None else frame.shape)
    cap.release()
PY
```

Some USB cameras expose multiple `/dev/video*` nodes. To target one directly:

```bash
printf 'DOORLOCK_CAMERA_BACKEND="opencv"\nDOORLOCK_CAMERA_DEVICE="/dev/video0"\nDOORLOCK_CAMERA_FOURCC="MJPG"\n' | sudo tee -a /etc/default/doorlock
sudo /etc/init.d/doorlock restart
```

## Mock Camera

Mock mode lets you run the web interface without a camera:

```bash
sudo sed -i 's/^DOORLOCK_CAMERA_BACKEND=.*/DOORLOCK_CAMERA_BACKEND="mock"/' /etc/default/doorlock
sudo /etc/init.d/doorlock restart
```

Switch back to the Pi camera:

```bash
sudo sed -i 's/^DOORLOCK_CAMERA_BACKEND=.*/DOORLOCK_CAMERA_BACKEND="rpicam"/' /etc/default/doorlock
sudo /etc/init.d/doorlock restart
```

## Stream and Recognition Tuning

The recognition loop can process a smaller frame while the web UI streams another size.

Useful settings:

| Setting | Purpose |
| --- | --- |
| `DOORLOCK_CAMERA_WIDTH` | capture width |
| `DOORLOCK_CAMERA_HEIGHT` | capture height |
| `DOORLOCK_CAMERA_FPS` | camera capture rate |
| `DOORLOCK_RECOGNITION_FPS` | how often face detection and embedding runs |
| `DOORLOCK_STREAM_FPS` | how often the browser receives the latest JPEG |
| `DOORLOCK_PROCESSING_SCALE` | scale used for recognition |
| `DOORLOCK_STREAM_SCALE` | scale used for browser stream |

If the live feed looks jagged, keep the stream at full scale:

```bash
printf 'DOORLOCK_PROCESSING_SCALE="0.5"\nDOORLOCK_STREAM_SCALE="1.0"\n' | sudo tee -a /etc/default/doorlock
sudo /etc/init.d/doorlock restart
```

For lower latency on slower Pi hardware:

```bash
sudo sed -i '/^DOORLOCK_CAMERA_WIDTH=/d;/^DOORLOCK_CAMERA_HEIGHT=/d;/^DOORLOCK_CAMERA_FPS=/d;/^DOORLOCK_RECOGNITION_FPS=/d;/^DOORLOCK_STREAM_FPS=/d' /etc/default/doorlock
printf 'DOORLOCK_CAMERA_WIDTH="640"\nDOORLOCK_CAMERA_HEIGHT="480"\nDOORLOCK_CAMERA_FPS="5"\nDOORLOCK_RECOGNITION_FPS="2"\nDOORLOCK_STREAM_FPS="5"\n' | sudo tee -a /etc/default/doorlock
sudo /etc/init.d/doorlock restart
```

If the detection box flashes, matching the recognition and stream rates is a simple compromise:

```bash
sudo sed -i '/^DOORLOCK_CAMERA_FPS=/d;/^DOORLOCK_STREAM_FPS=/d;/^DOORLOCK_RECOGNITION_FPS=/d' /etc/default/doorlock
printf 'DOORLOCK_CAMERA_FPS="5"\nDOORLOCK_STREAM_FPS="5"\nDOORLOCK_RECOGNITION_FPS="5"\n' | sudo tee -a /etc/default/doorlock
sudo /etc/init.d/doorlock restart
```

## Status Endpoint

The UI polls:

```bash
curl http://127.0.0.1:8080/status
```

Important camera fields:

- `cameraBackend`
- `cameraThreadAlive`
- `cameraFps`
- `recognitionFps`
- `streamFps`
- `processingScale`
- `streamScale`
