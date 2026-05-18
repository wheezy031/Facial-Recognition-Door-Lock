# Raspberry Pi Setup

This guide covers installing the app on a Raspberry Pi and running it as a service.

## Install Miniforge and Python 3.12

Raspberry Pi OS may ship with a Python version that does not have compatible MediaPipe wheels. On 64-bit Pi systems, use Miniforge to create a Python 3.12 environment before running `setup.sh`.

Check the CPU architecture:

```bash
uname -m
```

For `aarch64`, install Miniforge:

```bash
cd "$HOME"
curl -L -o Miniforge3-Linux-aarch64.sh \
  https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-aarch64.sh
bash Miniforge3-Linux-aarch64.sh -b -p "$HOME/miniforge3"
```

Load conda into the current shell:

```bash
. "$HOME/miniforge3/etc/profile.d/conda.sh"
```

Create the app environment:

```bash
mkdir -p "$HOME/conda-envs"
conda create -y -p "$HOME/conda-envs/fr-doorlock-py312" python=3.12 pip
conda activate "$HOME/conda-envs/fr-doorlock-py312"
python -V
```

Expected Python version:

```text
Python 3.12.x
```

If `python -V` still shows another version, check that the environment is active:

```bash
which python
```

It should point inside:

```text
$HOME/conda-envs/fr-doorlock-py312/bin/python
```

## Clone and Install

```bash
git clone https://github.com/Jaycar-Electronics/Facial-Recognition-Door-Lock
cd Facial-Recognition-Door-Lock
DOORLOCK_PYTHON_BIN="$HOME/conda-envs/fr-doorlock-py312/bin/python" ./setup.sh
```

The setup script writes defaults to `/etc/default/doorlock` and installs the init script at `/etc/init.d/doorlock`.

The setup script installs Python packages into the Python executable provided by `DOORLOCK_PYTHON_BIN`.

## Reusing the Environment

To activate the environment later:

```bash
. "$HOME/miniforge3/etc/profile.d/conda.sh"
conda activate "$HOME/conda-envs/fr-doorlock-py312"
```

To run commands without activating:

```bash
"$HOME/conda-envs/fr-doorlock-py312/bin/python" -m pip list
```

## Optional Virtualenv Alternative

The setup script can still use a normal Python virtualenv if it contains a compatible Python and packages. For Raspberry Pi 64-bit, conda Python 3.12 is the recommended path because MediaPipe wheels are more predictable.

If your system already has a compatible Python, create a virtualenv:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -V
```

Then run setup with:

```bash
DOORLOCK_PYTHON_BIN="$PWD/.venv/bin/python" ./setup.sh
```

The service will use whichever Python path is written to `DOORLOCK_PYTHON_BIN` in `/etc/default/doorlock`.

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
DOORLOCK_PYTHON_BIN="/home/pi/conda-envs/fr-doorlock-py312/bin/python"
DOORLOCK_PORT="8080"
DOORLOCK_EMBEDDING_MODEL="/home/pi/Facial-Recognition-Door-Lock/src/models/face_embedder.tflite"
```

See [camera backends and tuning](camera-backends.md) for camera settings.
