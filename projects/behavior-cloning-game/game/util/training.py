"""Small, reproducible behavior-cloning training pipeline.

The functions in this module intentionally expose the important teaching steps:
episode splitting, feature normalization, shuffled batches, and validation.
"""

from __future__ import annotations

import copy
import hashlib
import json
import platform
import random
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset
from util.data import Demonstration
from util.domain import TrainingConfig
from util.downsampling import DownsampleContext, LoadedDownsampler
from util.features import FeatureTransform, get_feature_transform
from util.model import ContinuousPolicyNetwork

ACTION_NAMES = ("action_x", "action_y")
MODEL_VERSION = 1
TRAINING_PRESETS = {
    "quick": TrainingConfig(epochs=10, hidden_size=32, hidden_layers=2),
    "balanced": TrainingConfig(epochs=30, hidden_size=64, hidden_layers=2),
    "explore": TrainingConfig(epochs=50, hidden_size=128, hidden_layers=4),
}


@dataclass(frozen=True)
class Normalization:
    mean: tuple[float, ...]
    std: tuple[float, ...]


@dataclass(frozen=True)
class TrainingResult:
    model: ContinuousPolicyNetwork
    normalization: Normalization
    train_episode_ids: tuple[int, ...]
    validation_episode_ids: tuple[int, ...]
    train_loss: tuple[float, ...]
    validation_loss: tuple[float, ...]
    best_epoch: int
    dataset_fingerprint: str
    config: TrainingConfig
    downsampling: dict[str, object] | None = None


@dataclass(frozen=True)
class LoadedArtifact:
    model: ContinuousPolicyNetwork
    metadata: dict[str, object]
    feature_transform: FeatureTransform


def training_preset(name: str) -> TrainingConfig:
    """Return one of the documented beginner starting points."""
    try:
        return TRAINING_PRESETS[name.lower()]
    except KeyError as error:
        choices = ", ".join(TRAINING_PRESETS)
        raise ValueError(f"Unknown training preset {name!r}; choose one of: {choices}") from error


def split_episode_ids(
    rows: Sequence[Demonstration], validation_fraction: float, seed: int
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Return disjoint train and validation episode IDs using a local RNG."""
    episode_ids = sorted({row.episode_id for row in rows})
    if len(episode_ids) < 2:
        raise ValueError(
            "Training needs at least two episodes so one can be used for validation. "
            "Collect another complete demonstration and try again."
        )
    shuffled = episode_ids[:]
    random.Random(seed).shuffle(shuffled)
    validation_count = max(1, min(len(shuffled) - 1, round(len(shuffled) * validation_fraction)))
    validation = tuple(sorted(shuffled[:validation_count]))
    training = tuple(sorted(shuffled[validation_count:]))
    return training, validation


def fit_normalization(
    rows: Sequence[Demonstration],
    feature_transform: FeatureTransform | None = None,
) -> Normalization:
    transform = feature_transform or get_feature_transform("absolute")
    features = torch.tensor([transform.apply(row.state) for row in rows], dtype=torch.float64)
    if not len(features):
        raise ValueError("Cannot fit normalization on an empty training partition")
    mean = features.mean(dim=0)
    # population standard deviation is stable for even a one-row partition
    std = features.std(dim=0, unbiased=False)
    std = torch.where(std < 1e-8, torch.ones_like(std), std)
    return Normalization(tuple(mean.tolist()), tuple(std.tolist()))


def dataset_fingerprint(rows: Sequence[Demonstration]) -> str:
    records = [row.as_row() for row in rows]
    encoded = json.dumps(records, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def train_policy(
    rows: Sequence[Demonstration],
    config: TrainingConfig = TrainingConfig(),
    *,
    device: str | torch.device = "cpu",
    progress: Callable[[int, float, float], None] | None = None,
    downsampler: LoadedDownsampler | None = None,
) -> TrainingResult:
    """Train on normalized positions and retain the best validation model."""
    config.validate()
    if not rows:
        raise ValueError("Training dataset has no demonstration rows")
    train_ids, validation_ids = split_episode_ids(
        rows, config.validation_fraction, config.seed
    )
    train_rows = [row for row in rows if row.episode_id in train_ids]
    validation_rows = [row for row in rows if row.episode_id in validation_ids]
    feature_transform = get_feature_transform(config.feature_transform)
    downsampling = None
    if downsampler is not None:
        before = len(train_rows)
        downsampled = downsampler.apply(
            train_rows,
            DownsampleContext(seed=config.seed),
        )
        episodes_before = {row.episode_id for row in train_rows}
        train_rows = downsampled.rows
        episodes_after = {row.episode_id for row in train_rows}
        downsampling = {
            "name": downsampler.name,
            "source_hash": downsampler.source_hash,
            "description": downsampled.description,
            "training_rows_before": before,
            "training_rows_after": len(train_rows),
            "validation_rows": len(validation_rows),
            "removed_training_episode_ids": sorted(episodes_before - episodes_after),
        }
    normalization = fit_normalization(train_rows, feature_transform)
    mean = torch.tensor(normalization.mean, dtype=torch.float32)
    std = torch.tensor(normalization.std, dtype=torch.float32)

    def tensors(partition: Sequence[Demonstration]) -> tuple[torch.Tensor, torch.Tensor]:
        x = torch.tensor(
            [feature_transform.apply(row.state) for row in partition],
            dtype=torch.float32,
        )
        y = torch.tensor([row.action.values() for row in partition], dtype=torch.float32)
        return (x - mean) / std, y

    train_x, train_y = tensors(train_rows)
    validation_x, validation_y = tensors(validation_rows)
    target_device = torch.device(device)

    # Seed before constructing either the model or DataLoader generator.
    torch.manual_seed(config.seed)
    model = ContinuousPolicyNetwork(
        input_size=len(feature_transform.feature_names),
        hidden_size=config.hidden_size,
        hidden_layers=config.hidden_layers,
        device=target_device,
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
    criterion = nn.MSELoss()
    generator = torch.Generator().manual_seed(config.seed)
    loader = DataLoader(
        TensorDataset(train_x, train_y),
        batch_size=config.batch_size,
        shuffle=True,
        generator=generator,
    )

    train_losses: list[float] = []
    validation_losses: list[float] = []
    best_loss = float("inf")
    best_epoch = 0
    best_state: dict[str, torch.Tensor] | None = None
    for epoch in range(config.epochs):
        model.train()
        total = 0.0
        samples = 0
        for batch_x, batch_y in loader:
            batch_x, batch_y = batch_x.to(target_device), batch_y.to(target_device)
            optimizer.zero_grad()
            prediction = model(batch_x)
            loss = criterion(prediction, batch_y)
            loss.backward()
            optimizer.step()
            total += loss.item() * len(batch_x)
            samples += len(batch_x)
        train_losses.append(total / samples)

        model.eval()
        with torch.no_grad():
            prediction = model(validation_x.to(target_device))
            validation_loss = criterion(prediction, validation_y.to(target_device)).item()
        validation_losses.append(validation_loss)
        if progress is not None:
            progress(epoch + 1, train_losses[-1], validation_loss)
        if validation_loss < best_loss:
            best_loss = validation_loss
            best_epoch = epoch + 1
            best_state = copy.deepcopy(model.state_dict())

    assert best_state is not None
    model.load_state_dict(best_state)
    # Bake normalization into fc1. The saved policy accepts raw game coordinates,
    # so both new artifact loaders and the legacy execute.py path behave correctly.
    with torch.no_grad():
        weight = model.fc1.weight.clone()
        device_mean = mean.to(target_device)
        device_std = std.to(target_device)
        model.fc1.weight.copy_(weight / device_std.unsqueeze(0))
        model.fc1.bias.sub_((weight * (device_mean / device_std).unsqueeze(0)).sum(dim=1))
    model.to("cpu")

    return TrainingResult(
        model=model,
        normalization=normalization,
        train_episode_ids=train_ids,
        validation_episode_ids=validation_ids,
        train_loss=tuple(train_losses),
        validation_loss=tuple(validation_losses),
        best_epoch=best_epoch,
        dataset_fingerprint=dataset_fingerprint(rows),
        config=config,
        downsampling=downsampling,
    )


def save_artifact(result: TrainingResult, output_directory: str | Path) -> tuple[Path, Path]:
    """Save portable weights and self-describing JSON without overwriting a run."""
    run_settings = {
        "config": asdict(result.config),
        "downsampling": (
            {
                "name": result.downsampling["name"],
                "source_hash": result.downsampling["source_hash"],
            }
            if result.downsampling is not None
            else None
        ),
    }
    config_json = json.dumps(run_settings, sort_keys=True, separators=(",", ":"))
    run_id = hashlib.sha256(
        f"{result.dataset_fingerprint}:{config_json}".encode()
    ).hexdigest()[:12]
    destination = Path(output_directory)
    destination.mkdir(parents=True, exist_ok=True)
    weights_path = destination / f"model_{run_id}.pth"
    metadata_path = destination / f"model_{run_id}.json"
    if weights_path.exists() or metadata_path.exists():
        raise FileExistsError(
            f"Experiment {run_id} already exists in {destination}; "
            "change a setting or output folder."
        )
    metadata = {
        "artifact_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_version": MODEL_VERSION,
        "model": {
            "type": "continuous_regression_mse",
            "input_size": len(get_feature_transform(result.config.feature_transform).feature_names),
            "output_size": len(ACTION_NAMES),
            "hidden_size": result.config.hidden_size,
            "hidden_layers": result.config.hidden_layers,
        },
        "feature_transform": result.config.feature_transform,
        "features": list(
            get_feature_transform(result.config.feature_transform).feature_names
        ),
        "actions": list(ACTION_NAMES),
        "normalization": {
            "mean": list(result.normalization.mean),
            "std": list(result.normalization.std),
            "baked_into_first_layer": True,
        },
        "config": asdict(result.config),
        "downsampling": result.downsampling,
        "seed": result.config.seed,
        "dataset_fingerprint": result.dataset_fingerprint,
        "split": {
            "train_episode_ids": list(result.train_episode_ids),
            "validation_episode_ids": list(result.validation_episode_ids),
        },
        "metrics": {
            "train_loss": list(result.train_loss),
            "validation_loss": list(result.validation_loss),
            "best_epoch": result.best_epoch,
        },
        "dependencies": {
            "python": platform.python_version(),
            "torch": torch.__version__,
        },
        "weights_file": weights_path.name,
    }
    torch.save(result.model.state_dict(), weights_path)
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return weights_path, metadata_path


def load_artifact(metadata_path: str | Path) -> LoadedArtifact:
    """Load an experiment on CPU, regardless of where it was trained."""
    path = Path(metadata_path)
    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
        model_info = metadata["model"]
        weights_path = path.parent / metadata["weights_file"]
        model = ContinuousPolicyNetwork(
            input_size=int(model_info["input_size"]),
            hidden_size=int(model_info["hidden_size"]),
            output_size=int(model_info["output_size"]),
            hidden_layers=int(model_info["hidden_layers"]),
            device="cpu",
        )
        model.load_state_dict(torch.load(weights_path, map_location="cpu", weights_only=True))
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not load training artifact {path}: {error}") from error
    model.eval()
    feature_transform = get_feature_transform(metadata.get("feature_transform", "absolute"))
    return LoadedArtifact(
        model=model,
        metadata=metadata,
        feature_transform=feature_transform,
    )
