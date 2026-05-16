#!/bin/sh
set -eu

PYTHON_BIN="${PYTHON_BIN:-/home/declan/conda-envs/fr-doorlock-py312/bin/python}"

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
