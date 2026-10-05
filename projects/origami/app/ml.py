"""Frozen ResNet18 features plus a small, participant-held-out classifier."""
from io import BytesIO
import threading
import warnings

import joblib
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ENCODER = "resnet18-IMAGENET1K_V1"
PREPROCESS = "exif-rgb-thumbnail1600-weights-transform-v1"


def normalize_image(data: bytes) -> bytes:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format not in {"JPEG", "PNG"}:
                    raise ValueError("Use a JPEG or PNG image")
                if image.width * image.height > 25_000_000:
                    raise ValueError("Image exceeds 25 megapixels")
                image = ImageOps.exif_transpose(image).convert("RGB")
                image.thumbnail((1600, 1600))
                output = BytesIO()
                image.save(output, format="JPEG", quality=90)
                return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ValueError("Cannot decode image; please recapture as JPEG or PNG") from error


class ResNetEncoder:
    def __init__(self):
        self._model = None
        self._lock = threading.Lock()

    def __call__(self, data: bytes) -> np.ndarray:
        import torch
        from torchvision.models import ResNet18_Weights, resnet18

        with self._lock:
            if self._model is None:
                torch.set_num_threads(2)
                weights = ResNet18_Weights.IMAGENET1K_V1
                self._transform = weights.transforms()
                self._model = resnet18(weights=weights)
                self._model.fc = torch.nn.Identity()
                self._model.eval().requires_grad_(False)
            with Image.open(BytesIO(data)) as image:
                tensor = self._transform(image.convert("RGB")).unsqueeze(0)
            with torch.inference_mode():
                return self._model(tensor).numpy()[0]


def fit_classifier(samples: list[dict], actions: list[str], objects, encoder,
                   holdout: list[str] | None, minimum: int, progress) -> tuple[bytes, dict]:
    participants = sorted({sample["participant_id"] for sample in samples})
    if holdout is None:
        holdout = participants[-1:] if len(participants) > 1 else []
    if set(holdout) - set(participants):
        raise ValueError("Held-out participant has no eligible samples")
    train = [sample for sample in samples if sample["participant_id"] not in holdout]
    test = [sample for sample in samples if sample["participant_id"] in holdout]
    counts = {action: sum(s["action_id"] == action for s in train) for action in actions}
    missing = [action for action, count in counts.items() if count < minimum]
    if missing:
        raise ValueError(f"Need at least {minimum} training samples for every action, after holdout: {', '.join(missing)}")
    features = []
    for index, sample in enumerate(train + test):
        features.append(encoder(objects.get(sample["image_key"])))
        progress(index + 1, len(train) + len(test))
    x = np.asarray(features)
    y = [sample["action_id"] for sample in train]
    classifier = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, random_state=42))
    classifier.fit(x[:len(train)], y)
    metadata = {
        "encoder": ENCODER, "preprocessing": PREPROCESS,
        "classes": classifier.classes_.tolist(), "training_participants": sorted(set(participants) - set(holdout)),
        "test_participants": holdout, "training_samples": len(train), "test_samples": len(test),
        "training_accuracy": float(accuracy_score(y, classifier.predict(x[:len(train)]))),
        "evaluation_mode": "participant_holdout" if test else "training_only_no_holdout",
        "test_accuracy": None, "confusion_matrix": None,
        "test_counts": {action: sum(s["action_id"] == action for s in test) for action in actions},
    }
    if test:
        expected = [sample["action_id"] for sample in test]
        predicted = classifier.predict(x[len(train):])
        metadata["test_accuracy"] = float(accuracy_score(expected, predicted))
        metadata["confusion_matrix"] = confusion_matrix(expected, predicted, labels=metadata["classes"]).tolist()
    output = BytesIO()
    joblib.dump(classifier, output)
    return output.getvalue(), metadata
