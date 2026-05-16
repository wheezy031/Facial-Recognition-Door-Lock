import os
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np

try:
	from ai_edge_litert.interpreter import Interpreter
except ImportError:
	try:
		from tflite_runtime.interpreter import Interpreter
	except ImportError:
		from tensorflow.lite.python.interpreter import Interpreter


def _env_float(name, default):
	try:
		return float(os.environ.get(name, default))
	except ValueError:
		return default


class FaceRecognizer:
	def __init__(self, model_path=None):
		model_path = model_path or os.environ.get('DOORLOCK_EMBEDDING_MODEL')
		if not model_path:
			model_path = Path(__file__).resolve().parent / 'models' / 'face_embedder.tflite'

		self.model_path = Path(model_path)
		if not self.model_path.is_file():
			raise RuntimeError(
				'Face embedding model not found: {}. Set DOORLOCK_EMBEDDING_MODEL '
				'or place a model at src/models/face_embedder.tflite.'.format(self.model_path)
			)

		min_confidence = _env_float('DOORLOCK_FACE_MIN_CONFIDENCE', 0.5)
		model_selection = int(os.environ.get('DOORLOCK_FACE_MODEL_SELECTION', '0'))
		self.threshold = _env_float('DOORLOCK_FACE_THRESHOLD', 0.45)
		self.crop_padding = _env_float('DOORLOCK_FACE_CROP_PADDING', 0.25)
		self.input_mean = _env_float('DOORLOCK_EMBEDDING_MEAN', 127.5)
		self.input_std = _env_float('DOORLOCK_EMBEDDING_STD', 128.0)

		self.detector = mp.solutions.face_detection.FaceDetection(
			model_selection=model_selection,
			min_detection_confidence=min_confidence,
		)

		self.interpreter = Interpreter(model_path=str(self.model_path))
		self.interpreter.allocate_tensors()
		self.input_details = self.interpreter.get_input_details()[0]
		self.output_details = self.interpreter.get_output_details()[0]

		shape = self.input_details['shape']
		if len(shape) != 4:
			raise RuntimeError('Expected a 4D model input tensor, got {}'.format(shape))

		self.input_dtype = self.input_details['dtype']
		if shape[-1] in (1, 3):
			self.channels_first = False
			self.input_height = int(shape[1])
			self.input_width = int(shape[2])
		elif shape[1] in (1, 3):
			self.channels_first = True
			self.input_height = int(shape[2])
			self.input_width = int(shape[3])
		else:
			raise RuntimeError('Could not infer image layout from input tensor {}'.format(shape))

	def close(self):
		self.detector.close()

	def detect_faces(self, frame_bgr):
		height, width = frame_bgr.shape[:2]
		frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
		results = self.detector.process(frame_rgb)
		if not results.detections:
			return []

		boxes = []
		for detection in results.detections:
			bbox = detection.location_data.relative_bounding_box
			left = int(bbox.xmin * width)
			top = int(bbox.ymin * height)
			right = int((bbox.xmin + bbox.width) * width)
			bottom = int((bbox.ymin + bbox.height) * height)
			boxes.append(self._pad_box((left, top, right, bottom), width, height))
		return boxes

	def extract_embeddings(self, frame_bgr):
		faces = []
		for box in self.detect_faces(frame_bgr):
			left, top, right, bottom = box
			thumbnail = frame_bgr[top:bottom, left:right]
			if thumbnail.size == 0:
				continue
			embedding = self.embedding_from_face(thumbnail)
			faces.append({
				'box': box,
				'thumbnail': thumbnail,
				'embedding': embedding,
			})
		return faces

	def embedding_from_image(self, image_bgr):
		faces = self.extract_embeddings(image_bgr)
		if not faces:
			return None

		def area(face):
			left, top, right, bottom = face['box']
			return (right - left) * (bottom - top)

		return max(faces, key=area)['embedding']

	def embedding_from_face(self, face_bgr):
		face_rgb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)
		resized = cv2.resize(face_rgb, (self.input_width, self.input_height))

		if np.issubdtype(self.input_dtype, np.floating):
			model_input = (resized.astype(np.float32) - self.input_mean) / self.input_std
			model_input = model_input.astype(self.input_dtype)
		else:
			model_input = resized.astype(self.input_dtype)

		if self.channels_first:
			model_input = np.transpose(model_input, (2, 0, 1))

		model_input = np.expand_dims(model_input, axis=0)
		self.interpreter.set_tensor(self.input_details['index'], model_input)
		self.interpreter.invoke()
		embedding = self.interpreter.get_tensor(self.output_details['index'])
		return self._normalize(embedding.reshape(-1).astype(np.float32))

	def distance(self, known_embedding, candidate_embedding):
		return 1.0 - float(np.dot(known_embedding, candidate_embedding))

	def _normalize(self, embedding):
		norm = np.linalg.norm(embedding)
		if norm == 0:
			return embedding
		return embedding / norm

	def _pad_box(self, box, width, height):
		left, top, right, bottom = box
		box_width = right - left
		box_height = bottom - top
		pad_x = int(box_width * self.crop_padding)
		pad_y = int(box_height * self.crop_padding)
		return (
			max(0, left - pad_x),
			max(0, top - pad_y),
			min(width, right + pad_x),
			min(height, bottom + pad_y),
		)
