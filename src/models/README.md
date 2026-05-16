# Face Embedding Model

Place the TensorFlow Lite face embedding model here:

```text
src/models/face_embedder.tflite
```

The application uses MediaPipe for face detection and this model for identity
embeddings. You can override the model path with:

```sh
export DOORLOCK_EMBEDDING_MODEL=/path/to/face_embedder.tflite
```

The default preprocessing assumes common MobileFaceNet-style input:

```text
(rgb - 127.5) / 128.0
```

Override those values if your model expects different normalization:

```sh
export DOORLOCK_EMBEDDING_MEAN=127.5
export DOORLOCK_EMBEDDING_STD=128.0
```

## Capturing People and Exporting an Identity Model

Use `src/train_identity_model.py` on the Raspberry Pi to capture face samples
and export a small TensorFlow Lite identity classifier:

```sh
cd /home/declan/Facial-Recognition-Door-Lock-mediapipe
. /home/declan/conda-envs/fr-doorlock-py312/bin/activate

python src/train_identity_model.py capture --person declan --samples 60
python src/train_identity_model.py train --allow-new
```

Or capture one person and immediately train:

```sh
python src/train_identity_model.py capture-train --person declan --samples 60 --allow-new
```

The script writes:

```text
src/models/doorlock_identity_classifier.tflite
src/models/doorlock_identity_classifier.labels.json
```

It also updates `src/people/*.jpg`, `src/people/*.npy`, and `src/people/meta.txt`
unless `--no-update-people` is passed.

The training/export step needs full TensorFlow in the environment:

```sh
python -m pip install -r requirements-train.txt
```

The identity classifier does not replace `face_embedder.tflite`. It expects
embeddings from `face_embedder.tflite` as input.
