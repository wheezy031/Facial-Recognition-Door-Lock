from pathlib import Path
import asyncio
import os
import random
import shutil
import string
import threading
import time

import cv2
import numpy as np

from recognizer import FaceRecognizer


APP_DIR = Path(__file__).resolve().parent
PEOPLE_DIR = APP_DIR / 'people'


def no_camera_frame(message='No camera feed'):
	frame = np.full((720, 1280, 3), (33, 39, 48), dtype=np.uint8)
	center_x = frame.shape[1] // 2
	center_y = frame.shape[0] // 2 - 28

	cv2.rectangle(
		frame,
		(center_x - 118, center_y - 70),
		(center_x + 80, center_y + 70),
		(190, 199, 211),
		6,
		cv2.LINE_AA,
	)
	cv2.rectangle(
		frame,
		(center_x + 80, center_y - 34),
		(center_x + 148, center_y + 34),
		(190, 199, 211),
		6,
		cv2.LINE_AA,
	)
	cv2.circle(frame, (center_x - 20, center_y), 34, (190, 199, 211), 6, cv2.LINE_AA)

	cv2.putText(
		frame,
		message,
		(center_x - 185, center_y + 145),
		cv2.FONT_HERSHEY_SIMPLEX,
		1.15,
		(230, 235, 241),
		3,
		cv2.LINE_AA,
	)
	cv2.putText(
		frame,
		'Waiting for camera frames',
		(center_x - 190, center_y + 190),
		cv2.FONT_HERSHEY_SIMPLEX,
		0.75,
		(150, 160, 174),
		2,
		cv2.LINE_AA,
	)

	ret, jpeg = cv2.imencode('.jpg', frame)
	if not ret:
		return bytes()
	return jpeg.tobytes()


def _truthy(value):
	return str(value).strip().lower() in ('1', 'true', 'yes', 'y', 'on')


def _env_float(name, default):
	try:
		return float(os.environ.get(name, default))
	except (TypeError, ValueError):
		return default


def _env_int(name, default):
	try:
		return int(os.environ.get(name, default))
	except (TypeError, ValueError):
		return default


class Identifier:
	def __init__(self):
		self.lock = threading.RLock()
		self.view = no_camera_frame()
		self.encodings = {}
		self.embeddings = {}
		self.latest_faces = []
		self.last_learning = {}
		self.exit = False
		self.friendly_names = {}
		self.allowed = []
		self.people_dir = PEOPLE_DIR
		self.recognizer = FaceRecognizer()
		self.max_samples = max(1, _env_int('DOORLOCK_MAX_EMBEDDINGS_PER_PERSON', 20))
		self.sample_threshold = _env_float('DOORLOCK_SAMPLE_THRESHOLD', self.recognizer.threshold * 1.35)
		self.auto_learn = _truthy(os.environ.get('DOORLOCK_AUTO_LEARN', '1'))
		self.auto_learn_threshold = _env_float('DOORLOCK_AUTO_LEARN_THRESHOLD', self.recognizer.threshold * 0.75)
		self.auto_learn_interval = _env_float('DOORLOCK_AUTO_LEARN_INTERVAL_SECONDS', 20.0)

		print('loading known people')
		p = self.people_dir
		if not (p.exists() and p.is_dir()):
			print(p, 'does not exist as a directory, aborting')
			exit()

		for fn in sorted(p.glob('*.jpg')):
			name = fn.stem
			print('>>', name)
			samples = self._load_or_create_embeddings(fn)
			if samples is None:
				print('failed to load', fn)
				continue
			self.embeddings[name] = samples
			self.encodings[name] = self._centroid(samples)
			self._save_user_embeddings(name)

		meta = p / 'meta.txt'
		if not (meta.exists() and meta.is_file()):
			print(meta, 'does not exist as a file, empty or otherwise')
			exit()

		for line in meta.open('r').readlines():
			line = line.strip()
			if line == '':
				continue

			line = [x.strip() for x in line.split(',')]
			uid, access = line[0], line[1]

			if uid not in self.encodings.keys():
				print('err: no image for', uid)
				continue
			if _truthy(access):
				self.allowed.append(uid)

			if len(line) > 2:
				self.friendly_names[uid] = ' '.join(line[2:])

		print('loaded data')

	def _embedding_set_path(self, uid):
		return self.people_dir / '{}.embeddings.npy'.format(uid)

	def _normalize(self, embedding):
		embedding = embedding.astype(np.float32)
		norm = np.linalg.norm(embedding)
		if norm != 0:
			embedding = embedding / norm
		return embedding

	def _normalize_samples(self, samples):
		samples = np.asarray(samples, dtype=np.float32)
		if samples.ndim == 1:
			samples = np.expand_dims(samples, axis=0)
		return np.stack([self._normalize(sample) for sample in samples]).astype(np.float32)

	def _centroid(self, samples):
		return self._normalize(np.mean(samples, axis=0).astype(np.float32))

	def _limit_samples(self, samples):
		if len(samples) <= self.max_samples:
			return samples
		if self.max_samples == 1:
			return samples[-1:]
		return np.vstack([samples[:1], samples[-(self.max_samples - 1):]]).astype(np.float32)

	def _save_user_embeddings(self, uid):
		samples = self._limit_samples(self._normalize_samples(self.embeddings[uid]))
		self.embeddings[uid] = samples
		self.encodings[uid] = self._centroid(samples)
		np.save(str(self._embedding_set_path(uid)), samples)
		np.save(str(self.people_dir / '{}.npy'.format(uid)), self.encodings[uid])

	def _load_or_create_embeddings(self, image_path):
		uid = image_path.stem
		embedding_set_path = self._embedding_set_path(uid)
		encoding_path = image_path.with_suffix('.npy')

		if embedding_set_path.exists() and embedding_set_path.is_file():
			try:
				samples = self._normalize_samples(np.load(str(embedding_set_path)))
				if len(samples) > 0:
					return self._limit_samples(samples)
			except Exception as e:
				print('failed to load cached embedding samples', embedding_set_path)
				print('reason:')
				print(e)

		if encoding_path.exists() and encoding_path.is_file():
			try:
				encoding = self._normalize(np.load(str(encoding_path)).astype(np.float32))
				return np.expand_dims(encoding, axis=0)
			except Exception as e:
				print('failed to load cached encoding', encoding_path)
				print('reason:')
				print(e)

		img = cv2.imread(str(image_path))
		if img is None:
			print('failed to read', image_path)
			return None

		try:
			encoding = self.recognizer.embedding_from_image(img)
		except Exception as e:
			print('failed to create embedding for', image_path)
			print('reason:')
			print(e)
			return None

		if encoding is not None:
			encoding = self._normalize(encoding)
			np.save(str(encoding_path), encoding)
			return np.expand_dims(encoding, axis=0)
		return None

	def setView(self, view):
		if hasattr(view, 'tobytes'):
			view = view.tobytes()
		with self.lock:
			self.view = view

	def setNoFeed(self, message='No camera feed'):
		view = no_camera_frame(message)
		with self.lock:
			self.view = view

	def setCurrentFaces(self, faces):
		latest_faces = [
			{
				'thumbnail': face.get('thumbnail'),
				'embedding': self._normalize(face['embedding']),
				'time': time.time(),
			}
			for face in faces
			if face.get('embedding') is not None
		]
		with self.lock:
			self.latest_faces = latest_faces

	def quit(self):
		with self.lock:
			self.exit = True

	def close(self):
		self.recognizer.close()

	def shouldExit(self):
		with self.lock:
			return self.exit

	def currentView(self):
		with self.lock:
			return self.view

	async def stream(self, response):
		stream_fps = max(1.0, _env_float('DOORLOCK_STREAM_FPS', 10.0))
		stream_interval = 1.0 / stream_fps
		try:
			while not self.shouldExit():
				r = b''.join([b'--frame\r\nContent-Type:image/jpeg\r\n\r\n', self.currentView(), b'\r\n'])
				await response.write(r)
				await asyncio.sleep(stream_interval)
		except asyncio.CancelledError:
			return
		except (ConnectionError, BrokenPipeError):
			return

	def toggleAccess(self, uid):
		with self.lock:
			if uid not in self.encodings.keys():
				return 'unknown user'

			if uid in self.allowed:
				self.allowed.remove(uid)
			else:
				self.allowed.append(uid)

			self.saveMeta()

			return 'ok'

	def hasAccess(self, uid):
		with self.lock:
			if uid not in self.encodings.keys():
				return False
			if uid in self.allowed:
				return True
			return False

	def displayName(self, uid):
		with self.lock:
			return self.friendly_names.get(uid, uid)

	def sampleCount(self, uid):
		with self.lock:
			return len(self.embeddings.get(uid, []))

	def saveMeta(self, fn=None):
		with self.lock:
			p = Path(fn) if fn else self.people_dir / 'meta.txt'
			with p.open('w') as f:
				for user in self.encodings.keys():
					allowed = user in self.allowed
					name = self.friendly_names.get(user, '')
					f.write('{},{},{}\n'.format(user, allowed, name))

	def addNew(self, thumbnail, encoding):
		with self.lock:
			c = string.ascii_uppercase + string.ascii_lowercase + string.digits

			uid = ''.join(random.choice(c) for _ in range(8))
			while uid in self.encodings.keys():
				uid = ''.join(random.choice(c) for _ in range(8))

			encoding = self._normalize(encoding)
			self.embeddings[uid] = np.expand_dims(encoding, axis=0)
			self.encodings[uid] = encoding
			cv2.imwrite(str(self.people_dir / '{}.jpg'.format(uid)), thumbnail)
			self._save_user_embeddings(uid)
			self.saveMeta()

			return uid

	def addEmbeddingSample(self, uid, thumbnail, encoding):
		with self.lock:
			if uid not in self.encodings.keys():
				return {'ok': False, 'error': 'unknown user'}

			encoding = self._normalize(encoding)
			samples = self.embeddings.get(uid)
			if samples is None or len(samples) == 0:
				samples = np.expand_dims(self.encodings[uid], axis=0)
			self.embeddings[uid] = np.vstack([samples, encoding]).astype(np.float32)
			self._save_user_embeddings(uid)

			if thumbnail is not None:
				image_path = self.people_dir / '{}.jpg'.format(uid)
				if not image_path.exists():
					cv2.imwrite(str(image_path), thumbnail)

			self.saveMeta()
			return {
				'ok': True,
				'uid': uid,
				'samples': len(self.embeddings.get(uid, [])),
				'maxSamples': self.max_samples,
			}

	def _distance_to_uid(self, uid, encoding):
		samples = self.embeddings.get(uid)
		if samples is None or len(samples) == 0:
			samples = np.expand_dims(self.encodings[uid], axis=0)
		return min(self.recognizer.distance(sample, encoding) for sample in samples)

	def _best_current_face_for_uid(self, uid):
		with self.lock:
			if uid not in self.encodings.keys():
				return None, None
			if not self.latest_faces:
				return None, None

			distances = [
				(self._distance_to_uid(uid, face['embedding']), face)
				for face in self.latest_faces
			]
			return min(distances, key=lambda item: item[0])

	def captureSample(self, uid):
		with self.lock:
			if uid not in self.encodings.keys():
				return {'ok': False, 'error': 'unknown user'}

			distance, face = self._best_current_face_for_uid(uid)
			if face is None:
				return {'ok': False, 'error': 'no face is currently visible'}

			if distance > self.sample_threshold:
				return {
					'ok': False,
					'error': 'visible face does not confidently match {}'.format(self.displayName(uid)),
					'distance': distance,
					'threshold': self.sample_threshold,
				}

			result = self.addEmbeddingSample(uid, face['thumbnail'], face['embedding'])
			result['distance'] = distance
			return result

	def _maybeLearn(self, uid, encoding, distance):
		if not self.auto_learn or distance > self.auto_learn_threshold:
			return

		now = time.time()
		if now - self.last_learning.get(uid, 0) < self.auto_learn_interval:
			return

		self.last_learning[uid] = now
		self.addEmbeddingSample(uid, None, encoding)

	def setName(self, uid, name):
		with self.lock:
			if uid not in self.encodings.keys():
				return False
			if name:
				self.friendly_names[uid] = name
			else:
				self.friendly_names.pop(uid, None)
			self.saveMeta()
			return True

	def getNames(self):
		with self.lock:
			ret = []
			for uid in self.encodings.keys():
				friendly = self.friendly_names.get(uid)
				ret.append({
					'uid': uid,
					'friendly': friendly,
					'name': friendly or uid,
					'allowed': True if uid in self.allowed else False,
					'samples': len(self.embeddings.get(uid, [])),
				})
			return ret

	def delete(self, uid):
		with self.lock:
			if uid not in self.encodings.keys():
				return None

			del self.encodings[uid]
			self.embeddings.pop(uid, None)
			if uid in self.allowed:
				self.allowed.remove(uid)
			self.friendly_names.pop(uid, None)

			for suffix in ('.jpg', '.npy', '.embeddings.npy'):
				p = self.people_dir / '{}{}'.format(uid, suffix)
				if p.exists() and p.is_file():
					p.unlink()

			self.saveMeta()

	def getImageLocation(self, uid):
		with self.lock:
			if uid not in self.encodings.keys():
				return None
			return str(self.people_dir / '{}.jpg'.format(uid))

	def merge(self, target, sources):
		with self.lock:
			if not target or target not in self.encodings:
				return {'ok': False, 'error': 'unknown merge target'}

			unique_sources = []
			for uid in sources:
				if uid == target or uid in unique_sources:
					continue
				unique_sources.append(uid)
			sources = unique_sources

			if not sources:
				return {'ok': False, 'error': 'choose at least one source person'}

			missing = [uid for uid in sources if uid not in self.encodings]
			if missing:
				return {'ok': False, 'error': 'unknown source person: {}'.format(', '.join(missing))}

			merged_ids = [target] + sources
			merged_samples = []
			for uid in merged_ids:
				samples = self.embeddings.get(uid)
				if samples is None or len(samples) == 0:
					samples = np.expand_dims(self.encodings[uid], axis=0)
				merged_samples.append(samples)
			self.embeddings[target] = self._limit_samples(self._normalize_samples(np.vstack(merged_samples)))
			self._save_user_embeddings(target)

			if target not in self.friendly_names:
				for uid in sources:
					if uid in self.friendly_names:
						self.friendly_names[target] = self.friendly_names[uid]
						break

			any_allowed = any(uid in self.allowed for uid in merged_ids)
			for uid in sources:
				if uid in self.allowed:
					self.allowed.remove(uid)
				self.friendly_names.pop(uid, None)

			if any_allowed and target not in self.allowed:
				self.allowed.append(target)
			if not any_allowed and target in self.allowed:
				self.allowed.remove(target)

			target_image = self.people_dir / '{}.jpg'.format(target)
			if not target_image.exists():
				for uid in sources:
					source_image = self.people_dir / '{}.jpg'.format(uid)
					if source_image.exists():
						shutil.copyfile(str(source_image), str(target_image))
						break

			for uid in sources:
				del self.encodings[uid]
				self.embeddings.pop(uid, None)
				for suffix in ('.jpg', '.npy', '.embeddings.npy'):
					path = self.people_dir / '{}{}'.format(uid, suffix)
					if path.exists() and path.is_file():
						path.unlink()

			self.saveMeta()
			return {
				'ok': True,
				'target': target,
				'merged': sources,
				'allowed': target in self.allowed,
				'name': self.friendly_names.get(target, target),
				'samples': len(self.embeddings.get(target, [])),
			}

	def getIDFromEncoding(self, encoding, difference=None):
		with self.lock:
			if not self.encodings:
				print('no known users loaded')
				return None

			if difference is None:
				difference = self.recognizer.threshold

			encoding = self._normalize(encoding)
			uids = list(self.encodings.keys())
			distances = [self._distance_to_uid(uid, encoding) for uid in uids]

			if not any([d <= difference for d in distances]):
				print('no user found')
				return None

			most_similar = int(np.argmin(distances))
			uid = uids[most_similar]
			distance = distances[most_similar]

			print(uid, ' user, with similarity {:.1%}'.format(1 - distance))

			self._maybeLearn(uid, encoding, distance)

			return uid
