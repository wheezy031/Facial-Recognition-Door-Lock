#!/bin/sh
set -eu

REPO_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-${DOORLOCK_PYTHON_BIN:-$REPO_DIR/.venv/bin/python}}"

if [ ! -x "$PYTHON_BIN" ]; then
	echo "Python not found or not executable: $PYTHON_BIN"
	exit 1
fi

"$PYTHON_BIN" - <<'PY'
import sys
import platform
import os
import shutil

print("python", sys.version.split()[0])
print("machine", platform.machine())

import numpy as np
print("numpy", np.__version__)

import cv2
print("cv2", cv2.__version__)

import mediapipe as mp
print("mediapipe", mp.__version__)

camera_backend = os.environ.get("DOORLOCK_CAMERA_BACKEND", "auto")
if camera_backend == "mock":
    print("camera backend mock")
elif camera_backend in ("opencv", "usb", "v4l2"):
    device = os.environ.get("DOORLOCK_CAMERA_DEVICE")
    source = device or int(os.environ.get("DOORLOCK_CAMERA_INDEX", "0"))
    cap = cv2.VideoCapture(source, cv2.CAP_V4L2)
    fourcc = os.environ.get("DOORLOCK_CAMERA_FOURCC", "MJPG")
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc[:4]))
    ok, frame = cap.read()
    print("opencv camera", source, "opened", cap.isOpened(), "frame", ok)
    if frame is not None:
        print("opencv frame shape", frame.shape, "mean", float(frame.mean()))
    cap.release()
else:
    camera_command = shutil.which("rpicam-vid") or shutil.which("libcamera-vid")
    if camera_command:
        print("camera command", camera_command)
    else:
        try:
            from picamera2 import Picamera2
            print("picamera2 ok")
        except ImportError:
            print("warning: no camera backend found")

try:
    from ai_edge_litert.interpreter import Interpreter
    print("ai-edge-litert ok")
except ImportError:
    from tflite_runtime.interpreter import Interpreter
    print("tflite-runtime ok")

print("smoke test passed")
PY
