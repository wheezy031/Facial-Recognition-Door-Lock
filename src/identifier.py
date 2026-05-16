from pathlib import Path
import asyncio
import random
import shutil
import string

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


class Identifier:
	def __init__(self):
		self.view = no_camera_frame()
		self.encodings = {}
		self.exit = False
		self.friendly_names = {}
		self.allowed = []
		self.people_dir = PEOPLE_DIR
		self.recognizer = FaceRecognizer()

		print('loading known people')
		p = self.people_dir
		if not (p.exists() and p.is_dir()):
			print(p, 'does not exist as a directory, aborting')
			exit()

		for fn in sorted(p.glob('*.jpg')):
			name = fn.stem
			print('>>', name)
			encoding = self._load_or_create_encoding(fn)
			if encoding is None:
				print('failed to load', fn)
				continue
			self.encodings[name] = encoding

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

	def _load_or_create_encoding(self, image_path):
		encoding_path = image_path.with_suffix('.npy')
		if encoding_path.exists() and encoding_path.is_file():
			try:
				encoding = np.load(str(encoding_path)).astype(np.float32)
				norm = np.linalg.norm(encoding)
				if norm != 0:
					encoding = encoding / norm
				return encoding
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
			np.save(str(encoding_path), encoding)
		return encoding

	def setView(self, view):
		if hasattr(view, 'tobytes'):
			view = view.tobytes()
		self.view = view

	def setNoFeed(self, message='No camera feed'):
		self.view = no_camera_frame(message)

	def quit(self):
		self.exit = True
		self.recognizer.close()

	async def stream(self, response):
		try:
			while not self.exit:
				r = b''.join([b'--frame\r\nContent-Type:image/jpeg\r\n\r\n', self.view, b'\r\n'])
				await response.write(r)
				await asyncio.sleep(0.1)
		except asyncio.CancelledError:
			return
		except (ConnectionError, BrokenPipeError):
			return

	def toggleAccess(self, uid):
		if uid not in self.encodings.keys():
			return 'unknown user'

		if uid in self.allowed:
			self.allowed.remove(uid)
		else:
			self.allowed.append(uid)

		self.saveMeta()

		return 'ok'

	def hasAccess(self, uid):
		if uid not in self.encodings.keys():
			return False
		if uid in self.allowed:
			return True
		return False

	def displayName(self, uid):
		return self.friendly_names.get(uid, uid)

	def saveMeta(self, fn=None):
		p = Path(fn) if fn else self.people_dir / 'meta.txt'
		with p.open('w') as f:
			for user in self.encodings.keys():
				allowed = user in self.allowed
				name = self.friendly_names.get(user, '')
				f.write('{},{},{}\n'.format(user, allowed, name))

	def addNew(self, thumbnail, encoding):
		c = string.ascii_uppercase + string.ascii_lowercase + string.digits

		uid = ''.join(random.choice(c) for _ in range(8))
		while uid in self.encodings.keys():
			uid = ''.join(random.choice(c) for _ in range(8))

		self.encodings[uid] = encoding
		cv2.imwrite(str(self.people_dir / '{}.jpg'.format(uid)), thumbnail)
		np.save(str(self.people_dir / '{}.npy'.format(uid)), encoding)
		self.saveMeta()

		return uid

	def setName(self, uid, name):
		if uid not in self.encodings.keys():
			return False
		if name:
			self.friendly_names[uid] = name
		else:
			self.friendly_names.pop(uid, None)
		self.saveMeta()
		return True

	def getNames(self):
		ret = []
		for uid in self.encodings.keys():
			friendly = self.friendly_names.get(uid)
			ret.append({
				'uid': uid,
				'friendly': friendly,
				'name': friendly or uid,
				'allowed': True if uid in self.allowed else False
			})
		print(ret)
		return ret

	def delete(self, uid):
		if uid not in self.encodings.keys():
			return None

		del self.encodings[uid]
		if uid in self.allowed:
			self.allowed.remove(uid)
		self.friendly_names.pop(uid, None)

		for suffix in ('.jpg', '.npy'):
			p = self.people_dir / '{}{}'.format(uid, suffix)
			if p.exists() and p.is_file():
				p.unlink()

		self.saveMeta()

	def getImageLocation(self, uid):
		if uid not in self.encodings.keys():
			return None
		return str(self.people_dir / '{}.jpg'.format(uid))

	def merge(self, target, sources):
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
		merged = np.mean(
			np.stack([self.encodings[uid] for uid in merged_ids]),
			axis=0,
		).astype(np.float32)
		norm = np.linalg.norm(merged)
		if norm != 0:
			merged = merged / norm
		self.encodings[target] = merged
		np.save(str(self.people_dir / '{}.npy'.format(target)), merged)

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
			for suffix in ('.jpg', '.npy'):
				path = self.people_dir / '{}{}'.format(uid, suffix)
				if path.exists() and path.is_file():
					path.unlink()

		self.saveMeta()
		return {
			'ok': True,
			'target': target,
			'merged': sources,
			'allowed': target in self.allowed,
			'name': self.displayName(target),
		}

	def getIDFromEncoding(self, encoding, difference=None):
		if not self.encodings:
			print('no known users loaded')
			return None

		if difference is None:
			difference = self.recognizer.threshold

		other_encodings = list(self.encodings.values())
		distances = [self.recognizer.distance(other, encoding) for other in other_encodings]

		if not any([d <= difference for d in distances]):
			print('no user found')
			return None

		most_similar = int(np.argmin(distances))
		uid = list(self.encodings.keys())[most_similar]
		distance = distances[most_similar]

		print(uid, ' user, with similarity {:.1%}'.format(1 - distance))

		self.encodings[uid] = np.average(
			[encoding, self.encodings[uid]],
			axis=0,
			weights=[1, 2],
		)
		norm = np.linalg.norm(self.encodings[uid])
		if norm != 0:
			self.encodings[uid] = self.encodings[uid] / norm
		np.save(str(self.people_dir / '{}.npy'.format(uid)), self.encodings[uid])

		return uid
