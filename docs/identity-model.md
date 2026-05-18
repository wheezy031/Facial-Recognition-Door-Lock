# Identity Model and Samples

The app uses MediaPipe for face detection and a TensorFlow Lite embedding model for identity matching.

## Embedding Model

Download MobileFaceNet from the `face_detection_tflite` repository:

```bash
mkdir -p src/models
curl -L -o src/models/face_embedder.tflite \
  https://raw.githubusercontent.com/hugocornellier/face_detection_tflite/main/assets/models/mobilefacenet.tflite
```

The file should be about 5.2 MB.

Keep it named:

```text
src/models/face_embedder.tflite
```

Or set a custom path:

```bash
DOORLOCK_EMBEDDING_MODEL="/path/to/face_embedder.tflite"
```

Do not use the `face_detection_*.tflite` files here. MediaPipe already handles detection; this project needs an embedding model for matching one identity against another.

## Stored Identity Files

Identity data is stored under:

```text
src/people/
```

Common files:

```text
<uid>.jpg               profile image shown in the UI
<uid>.npy               centroid embedding
<uid>.embeddings.npy    multiple embeddings for the same person
meta.txt                allow/deny state and friendly names
```

Existing single-vector `.npy` files are still supported. When identities are loaded or updated, the app creates `<uid>.embeddings.npy`.

## Identity Samples

Each person can store multiple face embeddings. This improves matching because the same person can be captured under different lighting, angle, and motion conditions.

Use the web UI `Add sample` button while the person is visible to capture another embedding for that identity.

Merging people keeps samples from the merged identities instead of collapsing everything into one vector.

Useful tuning values in `/etc/default/doorlock`:

```bash
DOORLOCK_MAX_EMBEDDINGS_PER_PERSON="20"
DOORLOCK_SAMPLE_THRESHOLD="0.60"
DOORLOCK_AUTO_LEARN="1"
DOORLOCK_AUTO_LEARN_INTERVAL_SECONDS="20"
DOORLOCK_ACCESS_COOLDOWN_SECONDS="10"
```

## Matching Flow

1. The camera worker captures a frame.
2. MediaPipe detects faces.
3. Each face crop is passed into the TFLite embedding model.
4. The embedding is compared against stored samples.
5. If the best distance is under the threshold, the identity is recognised.
6. If the recognised identity is allowed, the relay unlocks.

## Training Script

The repository includes:

```text
src/train_identity_model.py
```

Use this script on a Pi to capture training images and create the local identity data used by the app. The model file itself is not trained by this project; the app uses the downloaded TFLite embedding model and stores local identity embeddings.
