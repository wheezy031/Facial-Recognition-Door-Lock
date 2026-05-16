import asyncio
import os
import shutil
import subprocess

import cv2
import gpiozero
import numpy as np


relay = None
relay_error_reported = False


def truthy(value):
	return str(value).strip().lower() in ('1', 'true', 'yes', 'y', 'on')


class NullRelay:
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

	if relay is not None and hasattr(relay, 'close'):
		relay.close()
	relay = None


def report_relay_error(error):
	global relay_error_reported

	if not relay_error_reported:
		print(error)
		relay_error_reported = True


def accessGranted(name=None):
	print('Access Granted')
	if name:
		print('Hello', name)
	try:
		get_relay().blink(5, 1, 1)
	except Exception as e:
		report_relay_error(e)


def accessDenied(name=None):
	print('Access Denied')
	try:
		get_relay().off()
	except Exception as e:
		report_relay_error(e)


class Picamera2Camera:
	def __init__(self, size=(1280, 720)):
		from picamera2 import Picamera2

		self.picam = Picamera2()
		config = self.picam.create_video_configuration(
			main={'size': size, 'format': 'RGB888'}
		)
		self.picam.configure(config)
		self.picam.start()

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
		self.process = subprocess.Popen(
			[
				command,
				'--codec', 'mjpeg',
				'--inline',
				'--nopreview',
				'--timeout', '0',
				'--width', str(width),
				'--height', str(height),
				'-o', '-',
			],
			stdout=subprocess.PIPE,
			stderr=subprocess.DEVNULL,
		)
		self.buffer = b''

	def capture_array(self):
		while True:
			chunk = self.process.stdout.read(65536)
			if not chunk:
				raise RuntimeError('camera process stopped')

			self.buffer += chunk
			start = self.buffer.find(b'\xff\xd8')
			end = self.buffer.find(b'\xff\xd9', start + 2)

			if start == -1 or end == -1:
				continue

			jpeg = self.buffer[start:end + 2]
			self.buffer = self.buffer[end + 2:]
			frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
			if frame is not None:
				return frame

	def close(self):
		if self.process.poll() is None:
			self.process.terminate()
			try:
				self.process.wait(timeout=5)
			except subprocess.TimeoutExpired:
				self.process.kill()


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
			'Set DOORLOCK_CAMERA_BACKEND=auto when camera is attached',
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


def open_camera(size=(1280, 720)):
	backend = os.environ.get('DOORLOCK_CAMERA_BACKEND', 'auto').strip().lower()
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

	raise RuntimeError('Unknown camera backend: {}'.format(backend))


async def videoProcessing(identifier, imshow=False):
	# vstream = cv2.VideoCapture(0)  # desktop webcamera
	camera = open_camera()

	print('started video stream')
	await asyncio.sleep(0.1)

	while True:
		await asyncio.sleep(0.1)
		if identifier.exit:
			break

		try:
			frame = camera.capture_array()
		except Exception as e:
			print(e)
			continue

		scaled = cv2.resize(frame, None, fx=0.5, fy=0.5)

		try:
			faces = identifier.recognizer.extract_embeddings(scaled)
		except Exception as e:
			print('face recognition failed')
			print(e)
			continue

		for face in faces:
			left, top, right, bottom = face['box']
			cv2.rectangle(scaled, (left, top), (right, bottom), (255, 0, 0), 3)

			person = identifier.getIDFromEncoding(face['embedding'])

			if person is None:
				print('adding new person')
				identifier.addNew(face['thumbnail'], face['embedding'])
				continue

			if identifier.hasAccess(person):
				accessGranted(identifier.displayName(person))
			else:
				accessDenied(identifier.displayName(person))

		ret, v = cv2.imencode('.jpg', scaled)
		if ret:
			identifier.setView(v)

	camera.close()
	close_relay()
	cv2.destroyAllWindows()
