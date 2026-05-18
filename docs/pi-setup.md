# Raspberry Pi Setup

This guide covers installing the app on a Raspberry Pi and running it as a service.

## Clone and Install

```bash
git clone https://github.com/Jaycar-Electronics/Facial-Recognition-Door-Lock
cd Facial-Recognition-Door-Lock
./setup.sh
```

On Raspberry Pi 64-bit systems, use a Python 3.12 environment for MediaPipe:

```bash
DOORLOCK_PYTHON_BIN="$HOME/conda-envs/fr-doorlock-py312/bin/python" ./setup.sh
```

The setup script writes defaults to `/etc/default/doorlock` and installs the init script at `/etc/init.d/doorlock`.

## Python Environment

The app expects Python packages to be installed in the configured Python environment. The most common setup is a Python 3.12 conda environment:

```bash
. "$HOME/miniforge3/etc/profile.d/conda.sh"
conda create -y -p "$HOME/conda-envs/fr-doorlock-py312" python=3.12 pip
conda activate "$HOME/conda-envs/fr-doorlock-py312"
python -V
```

Then run setup with:

```bash
DOORLOCK_PYTHON_BIN="$HOME/conda-envs/fr-doorlock-py312/bin/python" ./setup.sh
```

## Download the Embedding Model

Download the MobileFaceNet embedding model and place it where the service expects it:

```bash
mkdir -p src/models
curl -L -o src/models/face_embedder.tflite \
  https://raw.githubusercontent.com/hugocornellier/face_detection_tflite/main/assets/models/mobilefacenet.tflite
```

The file should be about 5.2 MB. Keep it named `face_embedder.tflite`, or set `DOORLOCK_EMBEDDING_MODEL` in `/etc/default/doorlock`.

Do not use the `face_detection_*.tflite` files here. MediaPipe already handles face detection; this app needs an embedding model for identity matching.

## Service Commands

Restart the service:

```bash
sudo /etc/init.d/doorlock restart
```

Check status:

```bash
sudo /etc/init.d/doorlock status
```

Follow logs:

```bash
tail -f /var/log/doorlock.log
```

Open the web UI:

```text
http://<raspberry-pi-ip>:8080/
```

Check backend status:

```bash
curl http://127.0.0.1:8080/status
```

## Updating Files From a Development Machine

From your development machine:

```bash
rsync -av \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude 'src/people/' \
  --exclude 'src/models/*.tflite' \
  /path/to/Facial-Recognition-Door-Lock/ \
  <user>@<pi-ip>:/home/<user>/Facial-Recognition-Door-Lock/
```

If the init script changed, update the installed service copy:

```bash
ssh <user>@<pi-ip> 'cd /home/<user>/Facial-Recognition-Door-Lock && sudo install -m 755 src/doorlock.init.sh /etc/init.d/doorlock && sudo /etc/init.d/doorlock restart'
```

## Useful Defaults

Defaults are stored in `/etc/default/doorlock`.

Common values:

```bash
DOORLOCK_APP_DIR="/home/pi/Facial-Recognition-Door-Lock/src"
DOORLOCK_PYTHON_BIN="/home/pi/Facial-Recognition-Door-Lock/.venv/bin/python"
DOORLOCK_PORT="8080"
DOORLOCK_EMBEDDING_MODEL="/home/pi/Facial-Recognition-Door-Lock/src/models/face_embedder.tflite"
```

See [camera backends and tuning](camera-backends.md) for camera settings.
