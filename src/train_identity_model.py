#!/usr/bin/env python3
"""
Capture face samples on a Raspberry Pi and export a small TFLite identity model.

This script does not train a face embedding network from scratch. It uses the
pretrained DOORLOCK_EMBEDDING_MODEL to turn captured faces into embeddings, then
exports a tiny nearest-centroid classifier as TensorFlow Lite.

The generated identity model is separate from src/models/face_embedder.tflite.
Keep face_embedder.tflite in place for the door lock runtime.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from recognizer import FaceRecognizer


APP_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET_DIR = APP_DIR / 'training'
DEFAULT_MODELS_DIR = APP_DIR / 'models'
DEFAULT_PEOPLE_DIR = APP_DIR / 'people'
DEFAULT_IDENTITY_MODEL = DEFAULT_MODELS_DIR / 'doorlock_identity_classifier.tflite'
IMAGE_SUFFIXES = ('.jpg', '.jpeg', '.png')


def normalise_label(label):
	label = re.sub(r'[^A-Za-z0-9_-]+', '_', label.strip())
	label = label.strip('_')
	if not label:
		raise ValueError('person label must contain at least one letter or number')
	return label


def normalize_vector(vector):
	vector = vector.astype(np.float32)
	norm = np.linalg.norm(vector)
	if norm == 0:
		return vector
	return vector / norm


class Picamera2Camera:
	def __init__(self, size):
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
	def __init__(self, size):
		command = shutil.which('rpicam-vid') or shutil.which('libcamera-vid')
		if command is None:
			raise RuntimeError('No rpicam-vid or libcamera-vid command found')

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


class OpenCVCamera:
	def __init__(self, index, size):
		self.capture = cv2.VideoCapture(index)
		if not self.capture.isOpened():
			raise RuntimeError('OpenCV camera index {} could not be opened'.format(index))

		width, height = size
		self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
		self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

	def capture_array(self):
		ret, frame = self.capture.read()
		if not ret:
			raise RuntimeError('OpenCV camera frame capture failed')
		return frame

	def close(self):
		self.capture.release()


def open_camera(backend, size, opencv_index):
	if backend in ('auto', 'picamera2'):
		try:
			camera = Picamera2Camera(size)
			print('using Picamera2 camera backend')
			return camera
		except Exception as e:
			if backend == 'picamera2':
				raise
			print('Picamera2 unavailable:', e)

	if backend in ('auto', 'rpicam'):
		try:
			camera = RpicamVidCamera(size)
			print('using rpicam/libcamera camera backend')
			return camera
		except Exception as e:
			if backend == 'rpicam':
				raise
			print('rpicam/libcamera unavailable:', e)

	if backend in ('auto', 'opencv'):
		camera = OpenCVCamera(opencv_index, size)
		print('using OpenCV camera backend')
		return camera

	raise RuntimeError('no usable camera backend found')


def next_sample_index(person_dir, label):
	highest = 0
	for path in person_dir.glob('{}_*'.format(label)):
		match = re.search(r'_(\d+)\.', path.name)
		if match:
			highest = max(highest, int(match.group(1)))
	return highest + 1


def largest_face(faces):
	def area(face):
		left, top, right, bottom = face['box']
		return (right - left) * (bottom - top)

	return max(faces, key=area)


def capture_command(args):
	label = normalise_label(args.person)
	person_dir = args.dataset_dir / label
	person_dir.mkdir(parents=True, exist_ok=True)

	size = (args.width, args.height)
	camera = open_camera(args.camera, size, args.opencv_index)
	recognizer = FaceRecognizer(model_path=args.embedding_model)
	sample_index = next_sample_index(person_dir, label)
	captured = 0
	last_capture = 0.0
	last_status = 0.0

	print('capturing {} samples for {}'.format(args.samples, label))
	print('look at the camera and keep only this person in frame')
	print('press Ctrl-C to stop early')

	try:
		while captured < args.samples:
			frame = camera.capture_array()
			faces = recognizer.extract_embeddings(frame)

			now = time.monotonic()
			if len(faces) != 1:
				if now - last_status >= 1.0:
					print('waiting for exactly one face, found {}'.format(len(faces)))
					last_status = now
				continue

			if now - last_capture < args.interval:
				continue

			face = largest_face(faces)
			image_path = person_dir / '{}_{:04d}.jpg'.format(label, sample_index)
			embedding_path = image_path.with_suffix('.npy')

			if not cv2.imwrite(str(image_path), face['thumbnail']):
				raise RuntimeError('failed to write {}'.format(image_path))
			np.save(str(embedding_path), face['embedding'])

			captured += 1
			sample_index += 1
			last_capture = now
			print('captured {}/{}: {}'.format(captured, args.samples, image_path))

	except KeyboardInterrupt:
		print('')
		print('capture stopped')
	finally:
		camera.close()
		recognizer.close()

	print('samples stored in {}'.format(person_dir))


def image_paths(person_dir):
	paths = []
	for suffix in IMAGE_SUFFIXES:
		paths.extend(person_dir.glob('*{}'.format(suffix)))
		paths.extend(person_dir.glob('*{}'.format(suffix.upper())))
	return sorted(set(paths))


def embedding_from_training_image(recognizer, image_path):
	embedding_path = image_path.with_suffix('.npy')
	if embedding_path.exists():
		return normalize_vector(np.load(str(embedding_path)).reshape(-1))

	image = cv2.imread(str(image_path))
	if image is None:
		print('skipping unreadable image:', image_path)
		return None

	embedding = recognizer.embedding_from_image(image)
	if embedding is None:
		embedding = recognizer.embedding_from_face(image)
	if embedding is None:
		print('skipping image with no usable face:', image_path)
		return None

	np.save(str(embedding_path), embedding)
	return normalize_vector(embedding)


def load_training_data(dataset_dir, recognizer, min_samples):
	labels = []
	centroids = []
	sample_counts = {}
	representatives = {}

	if not dataset_dir.exists():
		raise RuntimeError('dataset directory does not exist: {}'.format(dataset_dir))

	for person_dir in sorted(path for path in dataset_dir.iterdir() if path.is_dir()):
		label = normalise_label(person_dir.name)
		embeddings = []
		images = image_paths(person_dir)

		for image_path in images:
			embedding = embedding_from_training_image(recognizer, image_path)
			if embedding is not None:
				embeddings.append(embedding)

		if len(embeddings) < min_samples:
			print(
				'skipping {}: only {} usable samples, need {}'.format(
					label, len(embeddings), min_samples
				)
			)
			continue

		centroid = normalize_vector(np.mean(np.stack(embeddings), axis=0))
		labels.append(label)
		centroids.append(centroid)
		sample_counts[label] = len(embeddings)
		if images:
			representatives[label] = images[0]

	if not labels:
		raise RuntimeError('no trainable people found in {}'.format(dataset_dir))

	return labels, np.stack(centroids).astype(np.float32), sample_counts, representatives


def import_tensorflow():
	try:
		import tensorflow as tf
		return tf
	except ImportError as e:
		raise RuntimeError(
			'Training/export needs full TensorFlow, not only TensorFlow Lite. '
			'Install it in the training environment with: python -m pip install tensorflow'
		) from e


def export_tflite_classifier(centroids, output_model):
	tf = import_tensorflow()

	input_dim = int(centroids.shape[1])
	label_count = int(centroids.shape[0])

	inputs = tf.keras.Input(shape=(input_dim,), dtype=tf.float32, name='embedding')
	outputs = tf.keras.layers.Dense(
		label_count,
		use_bias=False,
		activation=None,
		name='cosine_similarity',
	)(inputs)
	model = tf.keras.Model(inputs=inputs, outputs=outputs)
	model.get_layer('cosine_similarity').set_weights([centroids.T.astype(np.float32)])

	converter = tf.lite.TFLiteConverter.from_keras_model(model)
	tflite_model = converter.convert()

	output_model.parent.mkdir(parents=True, exist_ok=True)
	output_model.write_bytes(tflite_model)


def labels_path_for(output_model):
	return output_model.with_suffix('.labels.json')


def read_meta(meta_path):
	meta = {}
	if not meta_path.exists():
		return meta

	for line in meta_path.read_text().splitlines():
		line = line.strip()
		if not line:
			continue
		parts = [part.strip() for part in line.split(',')]
		uid = parts[0]
		allowed = parts[1] if len(parts) > 1 else 'False'
		name = ','.join(parts[2:]).strip() if len(parts) > 2 else ''
		meta[uid] = {'allowed': allowed, 'name': name}
	return meta


def write_people_files(people_dir, labels, centroids, representatives, allow_new):
	people_dir.mkdir(parents=True, exist_ok=True)
	meta_path = people_dir / 'meta.txt'
	meta = read_meta(meta_path)

	for index, label in enumerate(labels):
		np.save(str(people_dir / '{}.npy'.format(label)), centroids[index])
		if label in representatives:
			shutil.copyfile(
				str(representatives[label]),
				str(people_dir / '{}.jpg'.format(label)),
			)
		if label not in meta:
			meta[label] = {'allowed': 'True' if allow_new else 'False', 'name': label}

	with meta_path.open('w') as f:
		for label in sorted(meta.keys()):
			item = meta[label]
			f.write('{},{},{}\n'.format(label, item['allowed'], item['name']))


def train_command(args):
	recognizer = FaceRecognizer(model_path=args.embedding_model)
	try:
		labels, centroids, sample_counts, representatives = load_training_data(
			args.dataset_dir,
			recognizer,
			args.min_samples,
		)
	finally:
		recognizer.close()

	output_model = args.output_model
	output_labels = args.output_labels or labels_path_for(output_model)

	print('training labels:', ', '.join(labels))
	print('embedding size:', centroids.shape[1])
	export_tflite_classifier(centroids, output_model)

	metadata = {
		'model_type': 'nearest_centroid_cosine',
		'labels': labels,
		'embedding_dim': int(centroids.shape[1]),
		'sample_counts': sample_counts,
		'score_threshold_hint': args.score_threshold,
		'notes': (
			'This model expects normalized embeddings from the configured '
			'face_embedder.tflite model as input.'
		),
	}
	output_labels.parent.mkdir(parents=True, exist_ok=True)
	output_labels.write_text(json.dumps(metadata, indent=2, sort_keys=True) + '\n')

	if args.update_people:
		write_people_files(
			args.people_dir,
			labels,
			centroids,
			representatives,
			args.allow_new,
		)

	print('wrote TFLite identity model:', output_model)
	print('wrote labels metadata:', output_labels)
	if args.update_people:
		print('updated runtime people directory:', args.people_dir)


def capture_train_command(args):
	capture_command(args)
	train_args = argparse.Namespace(
		dataset_dir=args.dataset_dir,
		embedding_model=args.embedding_model,
		output_model=args.output_model,
		output_labels=args.output_labels,
		min_samples=args.min_samples,
		score_threshold=args.score_threshold,
		update_people=args.update_people,
		people_dir=args.people_dir,
		allow_new=args.allow_new,
	)
	train_command(train_args)


def add_shared_capture_args(parser):
	parser.add_argument('person', help='person label, for example user1')
	parser.add_argument('--samples', type=int, default=60)
	parser.add_argument('--interval', type=float, default=0.25)
	parser.add_argument('--dataset-dir', type=Path, default=DEFAULT_DATASET_DIR)
	parser.add_argument('--embedding-model', type=Path)
	parser.add_argument('--camera', choices=('auto', 'picamera2', 'rpicam', 'opencv'), default='auto')
	parser.add_argument('--opencv-index', type=int, default=0)
	parser.add_argument('--width', type=int, default=1280)
	parser.add_argument('--height', type=int, default=720)


def add_shared_train_args(parser, include_data_args=True):
	if include_data_args:
		parser.add_argument('--dataset-dir', type=Path, default=DEFAULT_DATASET_DIR)
		parser.add_argument('--embedding-model', type=Path)
	parser.add_argument('--output-model', type=Path, default=DEFAULT_IDENTITY_MODEL)
	parser.add_argument('--output-labels', type=Path)
	parser.add_argument('--min-samples', type=int, default=5)
	parser.add_argument('--score-threshold', type=float, default=0.55)
	parser.add_argument('--people-dir', type=Path, default=DEFAULT_PEOPLE_DIR)
	parser.add_argument('--allow-new', action='store_true')
	parser.add_argument('--no-update-people', dest='update_people', action='store_false')
	parser.set_defaults(update_people=True)


def parse_args(argv):
	parser = argparse.ArgumentParser(
		description='Capture face samples and export a TFLite identity classifier.'
	)
	subparsers = parser.add_subparsers(dest='command', required=True)

	capture_parser = subparsers.add_parser('capture')
	add_shared_capture_args(capture_parser)
	capture_parser.set_defaults(func=capture_command)

	train_parser = subparsers.add_parser('train')
	add_shared_train_args(train_parser)
	train_parser.set_defaults(func=train_command)

	capture_train_parser = subparsers.add_parser('capture-train')
	add_shared_capture_args(capture_train_parser)
	add_shared_train_args(capture_train_parser, include_data_args=False)
	capture_train_parser.set_defaults(func=capture_train_command)

	return parser.parse_args(argv)


def main(argv=None):
	args = parse_args(argv or sys.argv[1:])
	try:
		args.func(args)
	except Exception as e:
		print('error:', e, file=sys.stderr)
		return 1
	return 0


if __name__ == '__main__':
	raise SystemExit(main())
