#!/bin/sh
set -eu

REPO_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
APP_DIR="$REPO_DIR/src"
VENV_DIR="$REPO_DIR/.venv"
DOORLOCK_DEFAULTS="/etc/default/doorlock"
APT_UPDATED=0

apt_package_installed() {
	dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -q 'install ok installed'
}

apt_package_available() {
	apt-cache show "$1" >/dev/null 2>&1
}

ensure_apt_updated() {
	if [ "$APT_UPDATED" -eq 0 ]; then
		sudo apt-get update
		APT_UPDATED=1
	fi
}

install_apt_packages() {
	missing=""
	for package in "$@"; do
		if apt_package_installed "$package"; then
			echo "apt package already installed: $package"
		else
			missing="$missing $package"
		fi
	done

	if [ -n "$missing" ]; then
		ensure_apt_updated
		sudo apt-get install -y --no-install-recommends $missing
	fi
}

install_camera_tools() {
	if command -v rpicam-vid >/dev/null 2>&1; then
		echo "camera command already installed: rpicam-vid"
		return 0
	fi

	if command -v libcamera-vid >/dev/null 2>&1; then
		echo "camera command already installed: libcamera-vid"
		return 0
	fi

	ensure_apt_updated
	if apt_package_available rpicam-apps; then
		install_apt_packages rpicam-apps
	elif apt_package_available libcamera-apps; then
		install_apt_packages libcamera-apps
	else
		echo "Warning: no rpicam/libcamera video package found. Install rpicam-apps manually if camera capture fails."
	fi
}

python_module_installed() {
	module="$1"
	"$PYTHON_BIN" - "$module" <<'PY' >/dev/null 2>&1
import importlib
import sys

importlib.import_module(sys.argv[1])
PY
}

install_pip_package() {
	package="$1"
	module="$2"
	extra_args="${3:-}"

	if python_module_installed "$module"; then
		echo "python package already installed: $package"
	else
		"$PYTHON_BIN" -m pip install --no-cache-dir $extra_args "$package"
	fi
}

if [ -n "${DOORLOCK_PYTHON_BIN:-}" ]; then
	PYTHON_BIN="$DOORLOCK_PYTHON_BIN"
else
	PYTHON_BIN="$VENV_DIR/bin/python"
fi

install_apt_packages python3-pip python3-venv
install_camera_tools

if [ "${DOORLOCK_APT_UPGRADE:-0}" = "1" ]; then
	ensure_apt_updated
	sudo apt-get upgrade -y
fi

if [ -z "${DOORLOCK_PYTHON_BIN:-}" ] && [ ! -x "$PYTHON_BIN" ]; then
	python3 -m venv "$VENV_DIR"
fi

if [ ! -x "$PYTHON_BIN" ]; then
	echo "Python not found or not executable: $PYTHON_BIN"
	echo "Set DOORLOCK_PYTHON_BIN to an existing Python 3.12 environment if needed."
	exit 1
fi

PYTHON_VERSION="$("$PYTHON_BIN" -c 'import sys; print("{}.{}".format(sys.version_info.major, sys.version_info.minor))')"
if [ "$PYTHON_VERSION" != "3.12" ]; then
	echo "Warning: MediaPipe on Raspberry Pi aarch64 is expected to work best with Python 3.12."
	echo "Current Python: $PYTHON_VERSION"
fi

install_pip_package sanic sanic
install_pip_package numpy numpy
install_pip_package gpiozero gpiozero
install_pip_package lgpio lgpio
install_pip_package mediapipe==0.10.18 mediapipe '--only-binary=:all:'
install_pip_package ai-edge-litert==2.1.5 ai_edge_litert '--only-binary=:all:'

sudo tee "$DOORLOCK_DEFAULTS" >/dev/null <<EOF
DOORLOCK_REPO_DIR="$REPO_DIR"
DOORLOCK_APP_DIR="$APP_DIR"
DOORLOCK_PYTHON_BIN="$PYTHON_BIN"
DOORLOCK_EMBEDDING_MODEL="$APP_DIR/models/face_embedder.tflite"
DOORLOCK_FACE_THRESHOLD="${DOORLOCK_FACE_THRESHOLD:-0.45}"
DOORLOCK_RELAY_PIN="${DOORLOCK_RELAY_PIN:-14}"
DOORLOCK_PORT="${DOORLOCK_PORT:-8080}"
DOORLOCK_CAMERA_BACKEND="${DOORLOCK_CAMERA_BACKEND:-rpicam}"
DOORLOCK_CAMERA_INDEX="${DOORLOCK_CAMERA_INDEX:-0}"
DOORLOCK_CAMERA_DEVICE="${DOORLOCK_CAMERA_DEVICE:-}"
DOORLOCK_CAMERA_WIDTH="${DOORLOCK_CAMERA_WIDTH:-1280}"
DOORLOCK_CAMERA_HEIGHT="${DOORLOCK_CAMERA_HEIGHT:-720}"
DOORLOCK_CAMERA_FPS="${DOORLOCK_CAMERA_FPS:-10}"
DOORLOCK_CAMERA_FOURCC="${DOORLOCK_CAMERA_FOURCC:-MJPG}"
DOORLOCK_PROCESSING_SCALE="${DOORLOCK_PROCESSING_SCALE:-0.5}"
DOORLOCK_STREAM_SCALE="${DOORLOCK_STREAM_SCALE:-1.0}"
DOORLOCK_RECOGNITION_FPS="${DOORLOCK_RECOGNITION_FPS:-3}"
DOORLOCK_STREAM_FPS="${DOORLOCK_STREAM_FPS:-10}"
DOORLOCK_MAX_EMBEDDINGS_PER_PERSON="${DOORLOCK_MAX_EMBEDDINGS_PER_PERSON:-20}"
DOORLOCK_SAMPLE_THRESHOLD="${DOORLOCK_SAMPLE_THRESHOLD:-0.60}"
DOORLOCK_AUTO_LEARN="${DOORLOCK_AUTO_LEARN:-1}"
DOORLOCK_AUTO_LEARN_INTERVAL_SECONDS="${DOORLOCK_AUTO_LEARN_INTERVAL_SECONDS:-20}"
DOORLOCK_ACCESS_COOLDOWN_SECONDS="${DOORLOCK_ACCESS_COOLDOWN_SECONDS:-10}"
EOF

sudo cp src/doorlock.init.sh /etc/init.d/doorlock
sudo chmod +x /etc/init.d/doorlock
sudo update-rc.d doorlock defaults

echo "###############################"
echo "Setup done."
echo ""
echo "Python:"
echo " $PYTHON_BIN"
echo ""
echo "Face embedding model:"
echo " $APP_DIR/models/face_embedder.tflite"
echo ""
echo "Use:"
echo " sudo /etc/init.d/doorlock start"
echo " sudo /etc/init.d/doorlock stop"
echo ""
echo "Your ip is:"
hostname -I 2>/dev/null || ifconfig | grep 'inet ' | grep -v '127.0.0.1' | awk '{print $2}'
echo "###############################"
