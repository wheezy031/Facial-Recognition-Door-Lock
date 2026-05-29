import os
import select
import shutil
import subprocess
import threading
import time

import cv2
import gpiozero
import numpy as np


relay = None
relay_error_reported = False
unlock_timer = None
last_access_granted = {}
door_state_lock = threading.RLock()
camera_state_lock = threading.RLock()
door_state = {
	'state': 'locked',
	'relayActive': False,
	'lastAction': 'startup',
	'lastChanged': None,
	'unlockUntil': None,
	'unlockSeconds': None,
	'error': None,
}
camera_state = {
	'cameraActive': False,
	'motionEnabled': False,
	'motionDetected': None,
	'motionPin': None,
	'motionCooldownSeconds': None,
	'motionLastChanged': None,
	'motionError': None,
}


def truthy(value):
	return str(value).strip().lower() in ('1', 'true', 'yes', 'y', 'on')


def env_float(name, default):
	try:
		value = float(os.environ.get(name, default))
	except ValueError:
		return default
	if value <= 0:
		return default
	return value


def env_int(name, default):
	try:
		value = int(os.environ.get(name, default))
	except ValueError:
		return default
	if value <= 0:
		return default
	return value


def scaled_frame(frame, scale):
	if scale == 1.0:
		return frame

	interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
	return cv2.resize(frame, None, fx=scale, fy=scale, interpolation=interpolation)


def cameraState():
	with camera_state_lock:
		return dict(camera_state)


def updateCameraState(**updates):
	with camera_state_lock:
		camera_state.update(updates)
		return dict(camera_state)


class NullRelay:
	def on(self):
		return None

	def blink(self, *args, **kwargs):
		return None

	def off(self):
		return None


def get_relay():
	global relay

	if relay is not None:
		return relay

	if truthy(os.environ.get('DOORLOCK_DISABLE_RELAY', '')):
		relay = NullRelay()
		return relay

	pin = int(os.environ.get('DOORLOCK_RELAY_PIN', '14'))
	try:
		relay = gpiozero.LED(pin)
	except Exception as e:
		raise RuntimeError(
			'GPIO relay pin {} could not be opened. Stop any duplicate doorlock '
			'processes, or set DOORLOCK_RELAY_PIN to a free GPIO pin. Original '
			'error: {}'.format(pin, e)
		)
	return relay


def close_relay():
	global relay

	with door_state_lock:
		_cancel_unlock_timer_unlocked()

	if relay is not None and hasattr(relay, 'close'):
		relay.close()
	relay = None
	with door_state_lock:
		_set_door_state_unlocked('locked', False, 'shutdown')


def report_relay_error(error):
	global relay_error_reported

	if not relay_error_reported:
		print(error)
		relay_error_reported = True


def _snapshot_door_state_unlocked():
	state = dict(door_state)
	if state['unlockUntil'] is not None:
		state['remainingSeconds'] = max(0, round(state['unlockUntil'] - time.time(), 1))
	else:
		state['remainingSeconds'] = 0
	return state


def doorState():
	with door_state_lock:
		return _snapshot_door_state_unlocked()


def _set_door_state_unlocked(state, relay_active, action, unlock_until=None, unlock_seconds=None, error=None):
	door_state.update({
		'state': state,
		'relayActive': relay_active,
		'lastAction': action,
		'lastChanged': time.time(),
		'unlockUntil': unlock_until,
		'unlockSeconds': unlock_seconds,
		'error': error,
	})
	return _snapshot_door_state_unlocked()


def _cancel_unlock_timer_unlocked():
	global unlock_timer

	if unlock_timer is not None:
		unlock_timer.cancel()
		unlock_timer = None


def _auto_lock():
	global unlock_timer

	try:
		get_relay().off()
		with door_state_lock:
			unlock_timer = None
			_set_door_state_unlocked('locked', False, 'auto-lock')
	except Exception as e:
		with door_state_lock:
			unlock_timer = None
			_set_door_state_unlocked('error', False, 'auto-lock', error=str(e))
		print(e)


def unlockDoor(seconds=None):
	global unlock_timer

	if seconds is None:
		seconds = env_float('DOORLOCK_UNLOCK_SECONDS', 5.0)

	try:
		get_relay().on()
	except Exception as e:
		with door_state_lock:
			_set_door_state_unlocked('error', False, 'unlock', error=str(e))
		raise

	timer = threading.Timer(seconds, _auto_lock)
	timer.daemon = True

	with door_state_lock:
		_cancel_unlock_timer_unlocked()
		unlock_timer = timer
		state = _set_door_state_unlocked(
			'unlocked',
			True,
			'unlock',
			unlock_until=time.time() + seconds,
			unlock_seconds=seconds,
		)
	timer.start()
	return state


def lockDoor():
	try:
		get_relay().off()
	except Exception as e:
		with door_state_lock:
			_set_door_state_unlocked('error', False, 'lock', error=str(e))
		raise

	with door_state_lock:
		_cancel_unlock_timer_unlocked()
		return _set_door_state_unlocked('locked', False, 'lock')


def accessGranted(name=None):
	key = name or 'unknown'
	now = time.time()
	cooldown = env_float('DOORLOCK_ACCESS_COOLDOWN_SECONDS', 10.0)
	with door_state_lock:
		if door_state['state'] == 'unlocked':
			return
		if now - last_access_granted.get(key, 0) < cooldown:
			return
	last_access_granted[key] = now

	print('Access Granted')
	if name:
		print('Hello', name)
	try:
		unlockDoor()
	except Exception as e:
		report_relay_error(e)


def accessDenied(name=None):
	print('Access Denied')
	try:
		lockDoor()
	except Exception as e:
		report_relay_error(e)


class Picamera2Camera:
	def __init__(self, size=(1280, 720)):
		from picamera2 import Picamera2

		fps = env_int('DOORLOCK_CAMERA_FPS', 10)
		self.picam = Picamera2()
		config = self.picam.create_video_configuration(
			main={'size': size, 'format': 'RGB888'}
		)
		self.picam.configure(config)
		self.picam.set_controls({'FrameRate': fps})
		self.picam.start()
		print('opened Picamera2 at {}x{} {} fps'.format(size[0], size[1], fps))

	def capture_array(self):
		frame_rgb = self.picam.capture_array()
		return cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

	def close(self):
		self.picam.stop()


class RpicamVidCamera:
	def __init__(self, size=(1280, 720)):
		command = shutil.which('rpicam-vid') or shutil.which('libcamera-vid')
		if command is None:
			raise RuntimeError('No camera backend found. Install rpicam-apps or python3-picamera2.')

		width, height = size
		fps = env_int('DOORLOCK_CAMERA_FPS', 10)
		self.process = subprocess.Popen(
			[
				command,
				'--codec', 'mjpeg',
				'--inline',
				'--nopreview',
				'--timeout', '0',
				'--framerate', str(fps),
				'--width', str(width),
				'--height', str(height),
				'-o', '-',
			],
			stdout=subprocess.PIPE,
			stderr=subprocess.DEVNULL,
		)
		self.buffer = b''
		self.stdout_fd = self.process.stdout.fileno()
		self.read_timeout = env_float('DOORLOCK_CAMERA_READ_TIMEOUT_SECONDS', 2.0)
		self.max_buffer_bytes = max(65536, env_int('DOORLOCK_CAMERA_MAX_BUFFER_BYTES', 4 * 1024 * 1024))
		os.set_blocking(self.stdout_fd, False)
		print('opened rpicam-vid at {}x{} {} fps'.format(width, height, fps))

	def _read_available(self, timeout):
		ready, _, _ = select.select([self.stdout_fd], [], [], timeout)
		if not ready:
			if self.process.poll() is not None:
				raise RuntimeError('camera process stopped')
			raise RuntimeError('camera frame timed out')

		while ready:
			try:
				chunk = os.read(self.stdout_fd, 65536)
			except BlockingIOError:
				break
			if not chunk:
				raise RuntimeError('camera process stopped')

			self.buffer += chunk
			if len(self.buffer) > self.max_buffer_bytes:
				self.buffer = self.buffer[-self.max_buffer_bytes:]

			ready, _, _ = select.select([self.stdout_fd], [], [], 0)

	def _pop_latest_jpeg(self):
		latest = None
		while True:
			start = self.buffer.find(b'\xff\xd8')
			if start == -1:
				self.buffer = self.buffer[-1:]
				return latest

			end = self.buffer.find(b'\xff\xd9', start + 2)
			if end == -1:
				if start > 0:
					self.buffer = self.buffer[start:]
				return latest

			latest = self.buffer[start:end + 2]
			self.buffer = self.buffer[end + 2:]

	def capture_array(self):
		deadline = time.monotonic() + self.read_timeout
		while True:
			timeout = max(0.01, deadline - time.monotonic())
			self._read_available(timeout)
			jpeg = self._pop_latest_jpeg()
			if jpeg is None:
				if time.monotonic() >= deadline:
					raise RuntimeError('camera frame timed out')
				continue

			frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
			if frame is not None:
				return frame
			if time.monotonic() >= deadline:
				raise RuntimeError('camera frame decode failed')

	def close(self):
		if self.process.poll() is None:
			self.process.terminate()
			try:
				self.process.wait(timeout=5)
			except subprocess.TimeoutExpired:
				self.process.kill()


class OpenCVCamera:
	def __init__(self, size=(1280, 720)):
		source = os.environ.get('DOORLOCK_CAMERA_DEVICE')
		if not source:
			source = int(os.environ.get('DOORLOCK_CAMERA_INDEX', '0'))

		api_preference = cv2.CAP_V4L2 if os.name == 'posix' else cv2.CAP_ANY
		self.capture = cv2.VideoCapture(source, api_preference)
		if not self.capture.isOpened():
			raise RuntimeError('OpenCV camera source {} could not be opened'.format(source))

		width, height = size
		fourcc = os.environ.get('DOORLOCK_CAMERA_FOURCC', 'MJPG')
		fps = env_int('DOORLOCK_CAMERA_FPS', 10)
		if fourcc:
			self.capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc[:4]))
		self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
		self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
		self.capture.set(cv2.CAP_PROP_FPS, fps)
		self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

		actual_width = int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH))
		actual_height = int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
		actual_fps = self.capture.get(cv2.CAP_PROP_FPS)
		actual_fourcc = int(self.capture.get(cv2.CAP_PROP_FOURCC))
		actual_fourcc = ''.join(chr((actual_fourcc >> 8 * i) & 0xFF) for i in range(4))
		print(
			'opened OpenCV camera source {} at {}x{} {:.1f} fps fourcc {}'.format(
				source,
				actual_width,
				actual_height,
				actual_fps,
				actual_fourcc,
			)
		)

		warmup_frames = int(os.environ.get('DOORLOCK_CAMERA_WARMUP_FRAMES', '10'))
		for _ in range(warmup_frames):
			self.capture.read()

	def capture_array(self):
		ret, frame = self.capture.read()
		if not ret or frame is None:
			raise RuntimeError('OpenCV camera frame capture failed')
		return frame

	def close(self):
		self.capture.release()


class MockCamera:
	def __init__(self, size=(1280, 720)):
		self.width, self.height = size
		self.frame_number = 0

	def capture_array(self):
		self.frame_number += 1
		frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
		cv2.putText(
			frame,
			'Camera disabled',
			(40, 80),
			cv2.FONT_HERSHEY_SIMPLEX,
			1.4,
			(255, 255, 255),
			3,
			cv2.LINE_AA,
		)
		cv2.putText(
			frame,
			'Set DOORLOCK_CAMERA_BACKEND=rpicam when camera is attached',
			(40, 130),
			cv2.FONT_HERSHEY_SIMPLEX,
			0.8,
			(200, 200, 200),
			2,
			cv2.LINE_AA,
		)
		cv2.putText(
			frame,
			'Frame {}'.format(self.frame_number),
			(40, 180),
			cv2.FONT_HERSHEY_SIMPLEX,
			0.8,
			(160, 160, 160),
			2,
			cv2.LINE_AA,
		)
		return frame

	def close(self):
		return None


class AlwaysOnMotionController:
	def __init__(self, reason=None):
		self.reason = reason
		updateCameraState(
			motionEnabled=False,
			motionDetected=True,
			motionPin=None,
			motionCooldownSeconds=None,
			motionLastChanged=time.time(),
			motionError=reason,
		)

	def camera_requested(self):
		return True

	def close(self):
		return None


class MotionCameraController:
	def __init__(self):
		self.pin = int(os.environ.get('DOORLOCK_MOTION_PIN', '17'))
		self.cooldown = env_float('DOORLOCK_MOTION_CAMERA_COOLDOWN_SECONDS', 10.0)
		self.lock = threading.RLock()
		self.motion_detected = False
		self.last_motion_stop = 0.0
		self.sensor = gpiozero.MotionSensor(self.pin)
		self.sensor.when_motion = self._motion_detected
		self.sensor.when_no_motion = self._motion_stopped
		if self.sensor.motion_detected:
			self.motion_detected = True
		updateCameraState(
			motionEnabled=True,
			motionDetected=self.motion_detected,
			motionPin=self.pin,
			motionCooldownSeconds=self.cooldown,
			motionLastChanged=time.time(),
			motionError=None,
		)
		print('motion camera trigger listening on GPIO {}'.format(self.pin))

	def _motion_detected(self):
		with self.lock:
			self.motion_detected = True
		updateCameraState(motionDetected=True, motionLastChanged=time.time())
		print('motion detected on GPIO {}'.format(self.pin))

	def _motion_stopped(self):
		with self.lock:
			self.motion_detected = False
			self.last_motion_stop = time.monotonic()
		updateCameraState(motionDetected=False, motionLastChanged=time.time())
		print('motion stopped on GPIO {}; keeping camera on for {:.1f}s'.format(self.pin, self.cooldown))

	def camera_requested(self):
		with self.lock:
			if self.motion_detected:
				return True
			if self.last_motion_stop == 0.0:
				return False
			return time.monotonic() - self.last_motion_stop < self.cooldown

	def close(self):
		if hasattr(self, 'sensor') and self.sensor is not None:
			self.sensor.close()
			self.sensor = None


def open_motion_controller():
	if truthy(os.environ.get('DOORLOCK_DISABLE_MOTION_CAMERA', '')):
		return AlwaysOnMotionController()

	try:
		return MotionCameraController()
	except Exception as e:
		error = 'motion sensor unavailable; camera will stay always on: {}'.format(e)
		print(error)
		return AlwaysOnMotionController(error)


def open_camera(size=(1280, 720)):
	backend = os.environ.get('DOORLOCK_CAMERA_BACKEND', 'rpicam').strip().lower()
	if truthy(os.environ.get('DOORLOCK_DISABLE_CAMERA', '')):
		backend = 'mock'

	if backend in ('mock', 'none', 'disabled'):
		print('using mock camera backend')
		return MockCamera(size)

	if backend in ('auto', 'picamera2'):
		try:
			camera = Picamera2Camera(size)
			print('using Picamera2 camera backend')
			return camera
		except ImportError as e:
			if backend == 'picamera2':
				raise
			print('Picamera2 import failed, falling back to rpicam-vid')
			print(e)
		except Exception as e:
			if backend == 'picamera2':
				raise
			print('Picamera2 camera startup failed, falling back to rpicam-vid')
			print(e)

	if backend in ('auto', 'rpicam', 'libcamera'):
		camera = RpicamVidCamera(size)
		print('using rpicam-vid camera backend')
		return camera

	if backend in ('opencv', 'usb', 'v4l2'):
		camera = OpenCVCamera(size)
		print('using OpenCV USB camera backend')
		return camera

	raise RuntimeError('Unknown camera backend: {}'.format(backend))


def videoProcessing(identifier, imshow=False):
	# vstream = cv2.VideoCapture(0)  # desktop webcamera
	width = int(os.environ.get('DOORLOCK_CAMERA_WIDTH', '1280'))
	height = int(os.environ.get('DOORLOCK_CAMERA_HEIGHT', '720'))
	camera_fps = env_float('DOORLOCK_CAMERA_FPS', 10.0)
	camera_interval = 1.0 / camera_fps
	idle_interval = env_float('DOORLOCK_MOTION_IDLE_POLL_SECONDS', 0.2)
	processing_scale = env_float('DOORLOCK_PROCESSING_SCALE', 0.5)
	stream_scale = env_float('DOORLOCK_STREAM_SCALE', 1.0)
	recognition_fps = env_float('DOORLOCK_RECOGNITION_FPS', 3.0)
	recognition_interval = 1.0 / recognition_fps
	camera = None
	motion = open_motion_controller()

	def close_camera_if_open(message):
		nonlocal camera
		if camera is None:
			return
		print(message)
		camera.close()
		camera = None
		updateCameraState(cameraActive=False)

	try:
		identifier.setNoFeed('Waiting for motion')
		last_camera_error = None
		last_recognition = 0.0

		while True:
			loop_started = time.monotonic()
			if identifier.shouldExit():
				break

			if not motion.camera_requested():
				close_camera_if_open('stopping camera after motion cooldown')
				identifier.setNoFeed('Waiting for motion')
				identifier.setCurrentFaces([])
				time.sleep(idle_interval)
				continue

			if camera is None:
				try:
					camera = open_camera((width, height))
				except Exception as e:
					error = str(e)
					if error != last_camera_error:
						print(e)
						last_camera_error = error
					identifier.setNoFeed('No camera feed')
					identifier.setCurrentFaces([])
					time.sleep(camera_interval)
					continue
				updateCameraState(cameraActive=True)
				print('started video stream')
				time.sleep(0.1)

			try:
				frame = camera.capture_array()
			except Exception as e:
				error = str(e)
				if error != last_camera_error:
					print(e)
					last_camera_error = error
				identifier.setNoFeed('No camera feed')
				identifier.setCurrentFaces([])
				elapsed = time.monotonic() - loop_started
				if elapsed < camera_interval:
					time.sleep(camera_interval - elapsed)
				continue
			last_camera_error = None

			stream_frame = scaled_frame(frame, stream_scale)

			now = time.monotonic()
			if now - last_recognition >= recognition_interval:
				last_recognition = now
				processing_frame = scaled_frame(frame, processing_scale)
				box_scale_x = stream_frame.shape[1] / processing_frame.shape[1]
				box_scale_y = stream_frame.shape[0] / processing_frame.shape[0]

				try:
					faces = identifier.recognizer.extract_embeddings(processing_frame)
				except Exception as e:
					print('face recognition failed')
					print(e)
					identifier.setCurrentFaces([])
					faces = []
				else:
					identifier.setCurrentFaces(faces)

				for face in faces:
					left, top, right, bottom = face['box']
					stream_box = (
						int(left * box_scale_x),
						int(top * box_scale_y),
						int(right * box_scale_x),
						int(bottom * box_scale_y),
					)
					cv2.rectangle(
						stream_frame,
						(stream_box[0], stream_box[1]),
						(stream_box[2], stream_box[3]),
						(255, 0, 0),
						3,
					)

					person = identifier.getIDFromEncoding(face['embedding'])

					if person is None:
						print('adding new person')
						identifier.addNew(face['thumbnail'], face['embedding'])
						continue

					if identifier.hasAccess(person):
						accessGranted(identifier.displayName(person))
					else:
						accessDenied(identifier.displayName(person))

			ret, v = cv2.imencode('.jpg', stream_frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
			if ret:
				identifier.setView(v)

			elapsed = time.monotonic() - loop_started
			if elapsed < camera_interval:
				time.sleep(camera_interval - elapsed)
	finally:
		if camera is not None:
			camera.close()
		updateCameraState(cameraActive=False)
		motion.close()
		close_relay()
		cv2.destroyAllWindows()
