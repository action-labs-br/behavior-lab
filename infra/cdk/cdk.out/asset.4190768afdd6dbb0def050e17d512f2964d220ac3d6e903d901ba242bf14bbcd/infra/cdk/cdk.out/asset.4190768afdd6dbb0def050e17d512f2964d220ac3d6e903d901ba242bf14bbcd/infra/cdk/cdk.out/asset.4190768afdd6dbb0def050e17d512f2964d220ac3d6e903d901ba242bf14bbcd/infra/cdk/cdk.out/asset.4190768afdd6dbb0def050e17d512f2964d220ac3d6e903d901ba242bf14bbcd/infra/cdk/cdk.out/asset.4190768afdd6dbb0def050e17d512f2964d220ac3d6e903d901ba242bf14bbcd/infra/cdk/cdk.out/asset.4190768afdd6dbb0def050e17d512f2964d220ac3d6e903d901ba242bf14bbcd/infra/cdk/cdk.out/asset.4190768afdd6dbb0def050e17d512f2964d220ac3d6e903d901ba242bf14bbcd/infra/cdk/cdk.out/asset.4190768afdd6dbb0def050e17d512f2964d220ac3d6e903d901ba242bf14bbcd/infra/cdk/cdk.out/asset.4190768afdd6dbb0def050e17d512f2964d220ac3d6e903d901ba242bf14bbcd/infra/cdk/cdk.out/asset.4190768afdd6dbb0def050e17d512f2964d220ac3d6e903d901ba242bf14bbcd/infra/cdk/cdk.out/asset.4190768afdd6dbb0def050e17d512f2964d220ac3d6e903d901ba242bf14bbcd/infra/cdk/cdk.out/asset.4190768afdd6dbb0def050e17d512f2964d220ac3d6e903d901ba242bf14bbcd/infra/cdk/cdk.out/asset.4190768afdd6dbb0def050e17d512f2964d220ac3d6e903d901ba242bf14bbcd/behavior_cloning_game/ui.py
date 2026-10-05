"""Graphical launcher for the behavior-cloning learning workflow."""

from __future__ import annotations

import csv
import json
import math
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import pygame

WINDOW_SIZE = (920, 640)
BACKGROUND = (244, 247, 252)
PANEL = (255, 255, 255)
INK = (25, 35, 55)
MUTED = (91, 105, 130)
BLUE = (53, 115, 255)
BLUE_DARK = (35, 82, 190)
BORDER = (218, 225, 237)
SUCCESS = (31, 135, 85)
WARNING = (218, 139, 45)
ERROR = (190, 55, 62)

WORKFLOWS = (
    ("collect", "1", "Collect", "Play with the arrow keys and record demonstrations."),
    ("inspect", "2", "Inspect", "Review states, actions, outcomes, and data balance."),
    ("train", "3", "Train", "Fit a policy and save a reproducible experiment."),
    ("evaluate", "4", "Evaluate", "Watch a trained policy attempt the task."),
)

TRAINING_PRESETS = {
    "quick": ("10", "0.001", "32", "32", "2", "0.2", "42"),
    "balanced": ("30", "0.001", "32", "64", "2", "0.2", "42"),
    "explore": ("50", "0.001", "32", "128", "4", "0.2", "42"),
}
FEATURE_TRANSFORMS = ("absolute", "relative-center", "relative-containment")
TRAINING_FIELDS = (
    ("epochs", "Epochs"),
    ("learning_rate", "Learning rate"),
    ("batch_size", "Batch size"),
    ("hidden_size", "Hidden size"),
    ("hidden_layers", "Hidden layers"),
    ("validation_fraction", "Validation fraction"),
    ("seed", "Random seed"),
)
PRESET_TOOLTIPS = {
    "quick": "Fast baseline with fewer epochs and a smaller network.",
    "balanced": "Recommended starting point balancing training time and model capacity.",
    "explore": "Longer training with a larger, deeper network for comparison experiments.",
}
FEATURE_TOOLTIPS = {
    "absolute": "Uses the blue circle and target positions as four input features.",
    "relative-center": (
        "Uses the normalized horizontal and vertical distance between object centers."
    ),
    "relative-containment": "Uses the distance needed to move the circle fully inside the target.",
}
TRAINING_FIELD_TOOLTIPS = {
    "epochs": "Complete passes over the training data. More epochs take longer and may overfit.",
    "learning_rate": (
        "Controls the size of each optimizer update. Values that are too large can be unstable."
    ),
    "batch_size": (
        "Training samples used per update. Smaller batches make more frequent, noisier updates."
    ),
    "hidden_size": (
        "Neurons in each hidden layer. Larger layers increase model capacity and training cost."
    ),
    "hidden_layers": "Number of hidden layers in the policy network. This trainer supports 2 or 4.",
    "validation_fraction": (
        "Fraction of complete episodes reserved to measure performance during training."
    ),
    "seed": "Controls the reproducible episode split, model initialization, and batch order.",
}
DROP_NOOP_TOOLTIP = (
    "Removes stationary (0, 0) actions only from the training partition. "
    "Validation rows and the original CSV are unchanged."
)


@dataclass
class TrainingForm:
    """Editable graphical training options translated to train.py arguments."""

    preset: str
    epochs: str
    learning_rate: str
    batch_size: str
    hidden_size: str
    hidden_layers: str
    validation_fraction: str
    seed: str
    feature_transform: str = "absolute"
    drop_noop: bool = False

    @classmethod
    def for_preset(cls, preset: str) -> TrainingForm:
        return cls(preset, *TRAINING_PRESETS[preset])

    def apply_preset(self, preset: str) -> None:
        values = TRAINING_PRESETS[preset]
        self.preset = preset
        for (name, _), value in zip(TRAINING_FIELDS, values, strict=True):
            setattr(self, name, value)

    def arguments(self, path: Path) -> list[str]:
        """Validate the form and return arguments accepted by game/train.py."""
        integer_fields = {
            "epochs": "Epochs",
            "batch_size": "Batch size",
            "hidden_size": "Hidden size",
            "hidden_layers": "Hidden layers",
            "seed": "Random seed",
        }
        parsed_integers: dict[str, int] = {}
        for name, label in integer_fields.items():
            try:
                parsed_integers[name] = int(getattr(self, name))
            except ValueError as error:
                raise ValueError(f"{label} must be a whole number.") from error
        for name in ("epochs", "batch_size", "hidden_size"):
            if parsed_integers[name] < 1:
                label = integer_fields[name]
                raise ValueError(f"{label} must be at least 1.")
        if parsed_integers["hidden_layers"] not in (2, 4):
            raise ValueError("Hidden layers must be 2 or 4.")
        try:
            learning_rate = float(self.learning_rate)
        except ValueError as error:
            raise ValueError("Learning rate must be a number.") from error
        if not math.isfinite(learning_rate) or learning_rate <= 0:
            raise ValueError("Learning rate must be positive.")
        try:
            validation_fraction = float(self.validation_fraction)
        except ValueError as error:
            raise ValueError("Validation fraction must be a number.") from error
        if not math.isfinite(validation_fraction) or not 0 < validation_fraction < 1:
            raise ValueError("Validation fraction must be between 0 and 1.")

        arguments = [
            str(path),
            "--preset", self.preset,
            "--features", self.feature_transform,
        ]
        for name, _ in TRAINING_FIELDS:
            arguments.extend([f"--{name.replace('_', '-')}", getattr(self, name)])
        if self.drop_noop:
            arguments.extend(["--downsample", "drop-noop"])
        return arguments


@dataclass(frozen=True)
class Button:
    rectangle: pygame.Rect
    label: str
    value: str

    def contains(self, position: tuple[int, int]) -> bool:
        return self.rectangle.collidepoint(position)


def inspect_dataset(path: Path, game_directory: Path) -> Any:
    """Load a dataset summary using the same services as the script command."""
    game_path = str(game_directory)
    if game_path not in sys.path:
        sys.path.insert(0, game_path)
    from util.data import load_demonstrations
    from util.inspection import summarize_demonstrations

    rows, legacy = load_demonstrations(path)
    return summarize_demonstrations(rows, legacy=legacy)


def discover_artifacts(data_directory: Path, command: str) -> list[Path]:
    """Return newest compatible artifacts for a workflow."""
    if command in {"collect", "inspect", "train"}:
        paths = set(data_directory.glob("*.csv"))
    else:
        metadata_paths = {path.stem: path for path in data_directory.glob("model_*.json")}
        paths = set(metadata_paths.values())
        paths.update(
            path
            for path in data_directory.glob("*.pth")
            if path.stem not in metadata_paths
        )
    return sorted(paths, key=lambda path: (path.stat().st_mtime, path.name), reverse=True)


def dataset_append_compatibility(path: Path) -> tuple[bool, str]:
    """Return whether collection can safely append to a demonstration CSV."""
    try:
        modified_ns = path.stat().st_mtime_ns
    except OSError:
        return False, "Dataset is missing"
    return _cached_dataset_append_compatibility(str(path.resolve()), modified_ns)


@lru_cache(maxsize=128)
def _cached_dataset_append_compatibility(
    path_text: str,
    modified_ns: int,
) -> tuple[bool, str]:
    del modified_ns
    required_columns = {
        "schema_version",
        "episode_id",
        "step",
        "elapsed_ms",
        "blue_x",
        "blue_y",
        "target_x",
        "target_y",
        "action_x",
        "action_y",
        "outcome",
    }
    legacy_columns = {
        "Execution",
        "clock",
        "current_position_x",
        "current_position_y",
        "target_position_x",
        "target_position_y",
        "move_x",
        "move_y",
    }
    try:
        path = Path(path_text)
        if path.stat().st_size == 0:
            return False, "Dataset is empty"
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            columns = set(reader.fieldnames or ())
            if legacy_columns.issubset(columns):
                return False, "Legacy dataset cannot be appended"
            if not required_columns.issubset(columns):
                return False, "Unsupported dataset schema"
            for row in reader:
                if int(row["schema_version"]) != 2:
                    return False, "Only schema version 2 can be appended"
                int(row["episode_id"])
                int(row["step"])
                int(row["elapsed_ms"])
                for name in (
                    "blue_x",
                    "blue_y",
                    "target_x",
                    "target_y",
                    "action_x",
                    "action_y",
                ):
                    float(row[name])
                if row["outcome"] not in {
                    "success",
                    "out_of_bounds",
                    "stalled",
                    "quit",
                    "unknown",
                }:
                    return False, "Dataset contains an unknown outcome"
    except (csv.Error, KeyError, OSError, TypeError, UnicodeError, ValueError):
        return False, "Dataset contains invalid rows"
    return True, "Compatible"


def model_compatibility(path: Path) -> tuple[bool, str]:
    """Return whether an evaluation artifact can be loaded, with a display reason."""
    try:
        modified_ns = path.stat().st_mtime_ns
    except OSError:
        return False, "File is missing"
    weights_modified_ns = modified_ns
    if path.suffix == ".json":
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
            weights_modified_ns = (path.parent / metadata["weights_file"]).stat().st_mtime_ns
        except (KeyError, OSError, TypeError, json.JSONDecodeError):
            weights_modified_ns = -1
    return _cached_model_compatibility(
        str(path.resolve()), modified_ns, weights_modified_ns
    )


@lru_cache(maxsize=128)
def _cached_model_compatibility(
    path_text: str,
    modified_ns: int,
    weights_modified_ns: int,
) -> tuple[bool, str]:
    # Both timestamps are cache keys so changed metadata or weights are re-inspected.
    del modified_ns, weights_modified_ns
    path = Path(path_text)
    expected_input_size = 4
    expected_hidden_size: int | None = None
    expected_hidden_layers: int | None = None
    weights_path = path
    if path.suffix == ".json":
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
            transform = metadata.get("feature_transform", "absolute")
            expected_inputs = {
                "absolute": 4,
                "relative-center": 2,
                "relative-containment": 2,
            }
            expected_input_size = expected_inputs[transform]
            model = metadata["model"]
            if int(model["input_size"]) != expected_input_size:
                return False, "Feature count does not match the model"
            expected_hidden_size = int(model["hidden_size"])
            expected_hidden_layers = int(model["hidden_layers"])
            weights_file = metadata["weights_file"]
            if not isinstance(weights_file, str):
                raise TypeError
            weights_path = path.parent / weights_file
            if weights_path.resolve().parent != path.resolve().parent:
                return False, "Weights must be beside the model metadata"
            if not weights_path.is_file():
                return False, "Referenced weights file is missing"
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            return False, "Model metadata is incomplete or invalid"

    try:
        import torch

        state = torch.load(weights_path, map_location="cpu", weights_only=True)
        fc1 = state["fc1.weight"]
        fc2 = state["fc2.weight"]
        output = state["out.weight"]
        hidden_size, input_size = fc1.shape
        hidden_layers = 4 if "fc3.weight" in state else 2
        required = {"fc1.weight", "fc1.bias", "fc2.weight", "fc2.bias", "out.weight", "out.bias"}
        if hidden_layers == 4:
            required.update({"fc3.weight", "fc3.bias", "fc4.weight", "fc4.bias"})
        if set(state) != required:
            return False, "Checkpoint does not match the policy network"
        if input_size != expected_input_size:
            if path.suffix == ".pth":
                return False, "Needs paired JSON to identify its feature transform"
            return False, "Weights use a different feature count"
        if fc2.shape != (hidden_size, hidden_size) or output.shape != (2, hidden_size):
            return False, "Checkpoint layer shapes are incompatible"
        if expected_hidden_size is not None and hidden_size != expected_hidden_size:
            return False, "Weights use a different hidden size"
        if expected_hidden_layers is not None and hidden_layers != expected_hidden_layers:
            return False, "Weights use a different layer count"
    except (KeyError, OSError, RuntimeError, TypeError, ValueError):
        return False, "Checkpoint is unreadable or incomplete"
    return True, "Compatible"


def artifact_creation_label(path: Path) -> str:
    """Return a local creation timestamp, preferring recorded artifact metadata."""
    metadata_path = path if path.suffix == ".json" else path.with_suffix(".json")
    if metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            created_at = metadata.get("created_at")
            if isinstance(created_at, str):
                timestamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                if timestamp.tzinfo is not None:
                    timestamp = timestamp.astimezone()
                return timestamp.strftime("%Y-%m-%d %H:%M:%S")
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")


def artifact_training_metrics(path: Path) -> tuple[float, float | None] | None:
    """Return best validation and final training loss from model metadata."""
    metadata_path = path if path.suffix == ".json" else path.with_suffix(".json")
    if not metadata_path.is_file():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metrics = metadata["metrics"]
        validation_losses = [float(value) for value in metrics["validation_loss"]]
        if not validation_losses or not all(math.isfinite(value) for value in validation_losses):
            raise ValueError
        best_validation = min(validation_losses)
        training_losses = [float(value) for value in metrics.get("train_loss", ())]
        final_training = (
            training_losses[-1]
            if training_losses and math.isfinite(training_losses[-1])
            else None
        )
        return best_validation, final_training
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def training_metric_colour(
    value: float,
    comparable_values: Sequence[float],
) -> tuple[int, int, int]:
    """Colour a validation loss by its relative rank among visible models."""
    ranked = sorted(set(comparable_values))
    if len(ranked) < 2:
        return BLUE
    percentile = ranked.index(value) / (len(ranked) - 1)
    if percentile <= 1 / 3:
        return SUCCESS
    if percentile <= 2 / 3:
        return WARNING
    return ERROR


def _font(size: int, *, bold: bool = False) -> pygame.font.Font:
    return pygame.font.SysFont("arial", size, bold=bold)


def _text(
    surface: pygame.Surface,
    value: str,
    position: tuple[int, int],
    size: int,
    colour: tuple[int, int, int] = INK,
    *,
    bold: bool = False,
) -> None:
    surface.blit(_font(size, bold=bold).render(value, True, colour), position)


def _draw_header(surface: pygame.Surface) -> None:
    pygame.draw.circle(surface, BLUE, (61, 56), 24)
    pygame.draw.circle(surface, PANEL, (61, 56), 9)
    _text(surface, "Behavior Cloning Lab", (101, 31), 28, bold=True)
    _text(surface, "Collect  →  Inspect  →  Train  →  Evaluate", (102, 66), 15, MUTED)


def _workflow_buttons(surface: pygame.Surface) -> list[Button]:
    buttons: list[Button] = []
    for index, (command, number, title, description) in enumerate(WORKFLOWS):
        column, row = index % 2, index // 2
        rectangle = pygame.Rect(48 + column * 424, 132 + row * 174, 400, 144)
        hovered = rectangle.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(
            surface,
            (248, 251, 255) if hovered else PANEL,
            rectangle,
            border_radius=14,
        )
        pygame.draw.rect(surface, BLUE if hovered else BORDER, rectangle, width=2, border_radius=14)
        pygame.draw.circle(surface, BLUE, (rectangle.x + 38, rectangle.y + 38), 20)
        number_surface = _font(17, bold=True).render(number, True, PANEL)
        number_rectangle = number_surface.get_rect(center=(rectangle.x + 38, rectangle.y + 38))
        surface.blit(number_surface, number_rectangle)
        _text(surface, title, (rectangle.x + 72, rectangle.y + 22), 23, bold=True)
        _text(surface, description, (rectangle.x + 24, rectangle.y + 78), 15, MUTED)
        buttons.append(Button(rectangle, title, command))
    return buttons


def _draw_home(surface: pygame.Surface, status: tuple[str, bool] | None) -> list[Button]:
    surface.fill(BACKGROUND)
    _draw_header(surface)
    _text(surface, "Choose the next step", (48, 105), 17, MUTED)
    buttons = _workflow_buttons(surface)
    pygame.draw.rect(surface, PANEL, (48, 500, 824, 88), border_radius=12)
    if status:
        message, succeeded = status
        _text(surface, message, (72, 523), 17, SUCCESS if succeeded else ERROR, bold=True)
        _text(surface, "Choose another step whenever you are ready.", (72, 550), 14, MUTED)
    else:
        _text(
            surface,
            "Tip: collect several varied demonstrations before training.",
            (72, 531),
            16,
            MUTED,
        )
    _text(surface, "Press 1–4 to choose a step • Esc to exit", (48, 608), 13, MUTED)
    return buttons


def _draw_collection_choice(surface: pygame.Surface) -> list[Button]:
    """Ask whether collection should create or append to a dataset."""
    surface.fill(BACKGROUND)
    _draw_header(surface)
    _text(surface, "Collect demonstrations", (48, 112), 24, bold=True)
    _text(surface, "Where should the new demonstrations be saved?", (48, 148), 15, MUTED)

    choices = (
        (
            "Create a new dataset",
            "Start a timestamped CSV and record episode 1.",
            "collect-new",
        ),
        (
            "Append to an existing dataset",
            "Choose a compatible CSV and continue its episode numbering.",
            "collect-append",
        ),
    )
    buttons: list[Button] = []
    for index, (title, description, value) in enumerate(choices):
        rectangle = pygame.Rect(48, 198 + index * 132, 824, 108)
        hovered = rectangle.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(surface, PANEL, rectangle, border_radius=12)
        pygame.draw.rect(
            surface,
            BLUE if hovered else BORDER,
            rectangle,
            width=2,
            border_radius=12,
        )
        pygame.draw.circle(surface, BLUE, (rectangle.x + 35, rectangle.y + 36), 15)
        _text(
            surface,
            "+" if index == 0 else "↳",
            (rectangle.x + 29, rectangle.y + 24),
            18,
            PANEL,
            bold=True,
        )
        _text(surface, title, (rectangle.x + 64, rectangle.y + 20), 19, bold=True)
        _text(surface, description, (rectangle.x + 64, rectangle.y + 55), 14, MUTED)
        buttons.append(Button(rectangle, title, value))

    back = Button(pygame.Rect(48, 572, 112, 42), "Back", "back-home")
    pygame.draw.rect(surface, PANEL, back.rectangle, border_radius=8)
    pygame.draw.rect(surface, BORDER, back.rectangle, width=2, border_radius=8)
    _text(surface, "← Back", (back.rectangle.x + 19, back.rectangle.y + 10), 16, INK, bold=True)
    _text(
        surface,
        "The original CSV is validated before any rows are appended.",
        (400, 587),
        13,
        MUTED,
    )
    buttons.append(back)
    return buttons


def _short_path(path: Path, data_directory: Path) -> str:
    try:
        return str(path.relative_to(data_directory.parent.parent))
    except ValueError:
        return str(path)


def _draw_picker(
    surface: pygame.Surface,
    command: str,
    artifacts: Sequence[Path],
    data_directory: Path,
) -> list[Button]:
    surface.fill(BACKGROUND)
    _draw_header(surface)
    title = next(item[2] for item in WORKFLOWS if item[0] == command)
    noun = "dataset" if command in {"collect", "inspect", "train"} else "model"
    _text(surface, f"{title}: choose a {noun}", (48, 112), 24, bold=True)
    picker_guidance = (
        "Lower validation loss is better • Colors compare the models shown."
        if command == "evaluate"
        else (
            "Only compatible schema-v2 datasets can be appended."
            if command == "collect"
            else "Newest files appear first."
        )
    )
    _text(surface, picker_guidance, (48, 145), 15, MUTED)
    buttons = [Button(pygame.Rect(48, 572, 112, 42), "Back", "back")]
    if not artifacts:
        _text(surface, f"No compatible {noun} files were found in game/data.", (48, 214), 18, MUTED)
    visible_artifacts = artifacts[:7]
    training_metrics = (
        {path: artifact_training_metrics(path) for path in visible_artifacts}
        if command == "evaluate"
        else {}
    )
    compatibilities = (
        {path: model_compatibility(path) for path in visible_artifacts}
        if command == "evaluate"
        else (
            {path: dataset_append_compatibility(path) for path in visible_artifacts}
            if command == "collect"
            else {}
        )
    )
    validation_losses = [
        metrics[0] for metrics in training_metrics.values() if metrics is not None
    ]
    for index, path in enumerate(visible_artifacts):
        rectangle = pygame.Rect(48, 184 + index * 51, 824, 42)
        compatible, compatibility_reason = compatibilities.get(path, (True, ""))
        hovered = compatible and rectangle.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(surface, PANEL if compatible else BACKGROUND, rectangle, border_radius=8)
        pygame.draw.rect(surface, BLUE if hovered else BORDER, rectangle, width=2, border_radius=8)
        display_name = path.stem if command == "evaluate" else path.name
        title_y = rectangle.y + (3 if command == "evaluate" else 8)
        _text(
            surface,
            display_name,
            (rectangle.x + 16, title_y),
            16,
            INK if compatible else MUTED,
            bold=True,
        )
        if command == "evaluate":
            _text(
                surface,
                f"Created: {artifact_creation_label(path)}",
                (rectangle.x + 16, rectangle.y + 23),
                12,
                MUTED,
            )
            status_label = "✓ Compatible" if compatible else "Unavailable"
            _text(
                surface,
                status_label,
                (rectangle.x + 715, rectangle.y + 3),
                12,
                SUCCESS if compatible else MUTED,
                bold=True,
            )
            if compatible:
                metrics = training_metrics[path]
                metric_colour = (
                    training_metric_colour(metrics[0], validation_losses)
                    if metrics is not None
                    else MUTED
                )
                pygame.draw.circle(
                    surface, metric_colour, (rectangle.x + 570, rectangle.y + 30), 6
                )
                metric_label = "Metrics unavailable"
                if metrics is not None:
                    validation_loss, training_loss = metrics
                    training_label = (
                        f"{training_loss:.6g}" if training_loss is not None else "—"
                    )
                    metric_label = f"Val {validation_loss:.6g}  •  Train {training_label}"
                _text(
                    surface,
                    metric_label,
                    (rectangle.x + 584, rectangle.y + 22),
                    12,
                    metric_colour,
                    bold=True,
                )
            else:
                _text(
                    surface,
                    compatibility_reason,
                    (rectangle.x + 500, rectangle.y + 22),
                    12,
                    MUTED,
                )
        else:
            if command == "collect":
                _text(
                    surface,
                    "✓ Compatible" if compatible else compatibility_reason,
                    (rectangle.x + (700 if compatible else 500), rectangle.y + 10),
                    13,
                    SUCCESS if compatible else MUTED,
                    bold=compatible,
                )
            else:
                _text(
                    surface,
                    _short_path(path, data_directory),
                    (rectangle.x + 430, rectangle.y + 10),
                    13,
                    MUTED,
                )
        if compatible:
            buttons.append(Button(rectangle, display_name, str(path)))
    back = buttons[0]
    pygame.draw.rect(surface, PANEL, back.rectangle, border_radius=8)
    pygame.draw.rect(surface, BORDER, back.rectangle, width=2, border_radius=8)
    _text(surface, "← Back", (back.rectangle.x + 19, back.rectangle.y + 10), 16, INK, bold=True)
    _text(surface, "Esc to go back", (740, 588), 13, MUTED)
    return buttons


def _panel(surface: pygame.Surface, rectangle: pygame.Rect) -> None:
    pygame.draw.rect(surface, PANEL, rectangle, border_radius=12)
    pygame.draw.rect(surface, BORDER, rectangle, width=1, border_radius=12)


def _wrap(value: str, limit: int) -> list[str]:
    words = value.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > limit:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _draw_tooltip(
    surface: pygame.Surface,
    value: str,
    mouse_position: tuple[int, int],
) -> None:
    """Draw a wrapped tooltip near the pointer without leaving the window."""
    lines = _wrap(value, 54)
    font = _font(13)
    width = max(font.size(line)[0] for line in lines) + 24
    height = len(lines) * 18 + 18
    left = min(mouse_position[0] + 14, surface.get_width() - width - 8)
    top = min(mouse_position[1] + 18, surface.get_height() - height - 8)
    rectangle = pygame.Rect(max(8, left), max(8, top), width, height)
    pygame.draw.rect(surface, INK, rectangle, border_radius=8)
    pygame.draw.rect(surface, BLUE, rectangle, width=1, border_radius=8)
    for index, line in enumerate(lines):
        _text(surface, line, (rectangle.x + 12, rectangle.y + 9 + index * 18), 13, PANEL)


def _draw_inspection(
    surface: pygame.Surface,
    path: Path,
    summary: Any,
) -> list[Button]:
    surface.fill(BACKGROUND)
    _draw_header(surface)
    _text(surface, "Dataset inspection", (48, 105), 24, bold=True)
    _text(surface, path.name, (48, 138), 15, MUTED)

    metrics = (
        ("Samples", str(summary.samples)),
        ("Episodes", str(summary.episodes)),
        ("No-op actions", f"{summary.no_op_ratio:.1%}"),
    )
    for index, (label, value) in enumerate(metrics):
        rectangle = pygame.Rect(48 + index * 282, 174, 260, 82)
        _panel(surface, rectangle)
        _text(surface, label, (rectangle.x + 18, rectangle.y + 14), 14, MUTED)
        _text(surface, value, (rectangle.x + 18, rectangle.y + 37), 25, bold=True)

    outcomes_panel = pygame.Rect(48, 276, 260, 188)
    _panel(surface, outcomes_panel)
    _text(surface, "Episode outcomes", (66, 294), 17, bold=True)
    outcome_colours = {
        "success": SUCCESS,
        "out_of_bounds": ERROR,
        "stalled": (218, 139, 45),
        "quit": MUTED,
        "unknown": MUTED,
    }
    visible_outcomes = [
        item for item in summary.outcomes.items() if item[1] or item[0] != "quit"
    ]
    for index, (name, count) in enumerate(visible_outcomes[:5]):
        y = 327 + index * 25
        pygame.draw.circle(surface, outcome_colours.get(name, MUTED), (70, y + 7), 5)
        _text(surface, name.replace("_", " ").title(), (84, y), 14, MUTED)
        _text(surface, str(count), (276, y), 14, INK, bold=True)

    actions_panel = pygame.Rect(328, 276, 544, 188)
    _panel(surface, actions_panel)
    _text(surface, "Action distribution", (346, 294), 17, bold=True)
    action_items = sorted(
        summary.action_histogram.items(), key=lambda item: (-item[1], item[0])
    )
    maximum = max((count for _, count in action_items), default=1)
    for index, ((x, y), count) in enumerate(action_items[:5]):
        top = 327 + index * 25
        _text(surface, f"({x:g}, {y:g})", (346, top), 14, MUTED)
        pygame.draw.rect(surface, BORDER, (430, top + 3, 330, 12), border_radius=6)
        width = max(3, round(330 * count / maximum))
        pygame.draw.rect(surface, BLUE, (430, top + 3, width, 12), border_radius=6)
        _text(surface, str(count), (780, top), 14, INK, bold=True)
    if len(action_items) > 5:
        _text(surface, f"+ {len(action_items) - 5} more actions", (346, 447), 12, MUTED)
    expand_actions = Button(actions_panel, "Expand action distribution", "expand-actions")
    _text(surface, "Click to view all", (738, 296), 12, BLUE_DARK, bold=True)

    guidance_panel = pygame.Rect(48, 484, 824, 96)
    _panel(surface, guidance_panel)
    heading = "Data-quality guidance" if summary.warnings else "Ready to train"
    _text(surface, heading, (66, 500), 16, bold=True)
    guidance = summary.warnings or ("No obvious data-quality warnings were found.",)
    line_y = 526
    for warning in guidance[:2]:
        for line in _wrap(warning, 92)[:2]:
            colour = ERROR if summary.warnings else SUCCESS
            _text(surface, f"• {line}", (66, line_y), 13, colour)
            line_y += 18

    back = Button(pygame.Rect(48, 594, 112, 38), "Back", "back")
    train = Button(pygame.Rect(680, 594, 192, 38), "Train", "train-selected")
    for button, fill, colour in ((back, PANEL, INK), (train, BLUE, PANEL)):
        pygame.draw.rect(surface, fill, button.rectangle, border_radius=8)
        if button is back:
            pygame.draw.rect(surface, BORDER, button.rectangle, width=2, border_radius=8)
        label = "← Datasets" if button is back else "Train this dataset →"
        label_surface = _font(15, bold=True).render(label, True, colour)
        label_rectangle = label_surface.get_rect(center=button.rectangle.center)
        surface.blit(label_surface, label_rectangle)
    return [back, train, expand_actions]


def _draw_action_distribution(
    surface: pygame.Surface,
    path: Path,
    summary: Any,
    scroll_offset: int,
) -> tuple[list[Button], int]:
    """Draw the complete action histogram in a vertically scrollable view."""
    surface.fill(BACKGROUND)
    _draw_header(surface)
    _text(surface, "Action distribution", (48, 105), 24, bold=True)
    _text(surface, path.name, (48, 138), 15, MUTED)

    action_items = sorted(
        summary.action_histogram.items(), key=lambda item: (-item[1], item[0])
    )
    _text(surface, f"{len(action_items)} unique actions", (688, 112), 15, MUTED)

    viewport = pygame.Rect(48, 174, 824, 372)
    _panel(surface, viewport)
    row_height = 30
    content_padding = 18
    content_height = content_padding * 2 + len(action_items) * row_height
    maximum_scroll = max(0, content_height - viewport.height)
    scroll_offset = max(0, min(scroll_offset, maximum_scroll))
    maximum = max((count for _, count in action_items), default=1)

    if not action_items:
        _text(surface, "No actions were found in this dataset.", (66, 198), 15, MUTED)
    previous_clip = surface.get_clip()
    surface.set_clip(viewport)
    for index, ((x, y), count) in enumerate(action_items):
        top = viewport.top + content_padding + index * row_height - scroll_offset
        if top + row_height <= viewport.top or top >= viewport.bottom:
            continue
        _text(surface, f"({x:g}, {y:g})", (70, top + 4), 14, MUTED)
        pygame.draw.rect(surface, BORDER, (190, top + 7, 560, 12), border_radius=6)
        width = max(3, round(560 * count / maximum))
        pygame.draw.rect(surface, BLUE, (190, top + 7, width, 12), border_radius=6)
        _text(surface, str(count), (784, top + 4), 14, INK, bold=True)
    surface.set_clip(previous_clip)

    if maximum_scroll:
        track = pygame.Rect(852, viewport.top + 12, 6, viewport.height - 24)
        pygame.draw.rect(surface, BORDER, track, border_radius=3)
        thumb_height = max(28, round(track.height * viewport.height / content_height))
        thumb_travel = track.height - thumb_height
        thumb_top = track.top + round(thumb_travel * scroll_offset / maximum_scroll)
        pygame.draw.rect(
            surface, BLUE, (track.x, thumb_top, track.width, thumb_height), border_radius=3
        )
        _text(surface, "Scroll to see every action", (48, 559), 13, MUTED)

    back = Button(pygame.Rect(48, 586, 190, 42), "Back", "back-to-inspection")
    pygame.draw.rect(surface, PANEL, back.rectangle, border_radius=8)
    pygame.draw.rect(surface, BORDER, back.rectangle, width=2, border_radius=8)
    _text(surface, "← Dataset inspection", (66, 597), 15, INK, bold=True)
    _text(surface, "Mouse wheel or ↑/↓ to scroll • Esc to go back", (550, 601), 13, MUTED)
    return [back], maximum_scroll


def _draw_training_config(
    surface: pygame.Surface,
    path: Path,
    form: TrainingForm,
    active_field: str | None,
    error: str | None,
) -> list[Button]:
    """Draw preprocessing and hyperparameter choices before training starts."""
    surface.fill(BACKGROUND)
    _draw_header(surface)
    _text(surface, "Configure training", (48, 105), 24, bold=True)
    _text(surface, path.name, (48, 138), 15, MUTED)
    buttons: list[Button] = []
    tooltip_targets: list[tuple[pygame.Rect, str]] = []

    _text(surface, "Preset", (48, 174), 14, MUTED, bold=True)
    for index, preset in enumerate(TRAINING_PRESETS):
        rectangle = pygame.Rect(138 + index * 126, 164, 114, 36)
        selected = form.preset == preset
        pygame.draw.rect(surface, BLUE if selected else PANEL, rectangle, border_radius=7)
        pygame.draw.rect(surface, BLUE if selected else BORDER, rectangle, width=2, border_radius=7)
        label = preset.title()
        label_surface = _font(14, bold=True).render(label, True, PANEL if selected else INK)
        surface.blit(label_surface, label_surface.get_rect(center=rectangle.center))
        buttons.append(Button(rectangle, label, f"preset:{preset}"))
        tooltip_targets.append((rectangle, PRESET_TOOLTIPS[preset]))

    _text(surface, "Features", (48, 222), 14, MUTED, bold=True)
    feature_widths = (126, 180, 224)
    left = 138
    for feature, width in zip(FEATURE_TRANSFORMS, feature_widths, strict=True):
        rectangle = pygame.Rect(left, 212, width, 36)
        selected = form.feature_transform == feature
        pygame.draw.rect(surface, BLUE if selected else PANEL, rectangle, border_radius=7)
        pygame.draw.rect(surface, BLUE if selected else BORDER, rectangle, width=2, border_radius=7)
        label = feature.replace("-", " ").title()
        label_surface = _font(13, bold=True).render(label, True, PANEL if selected else INK)
        surface.blit(label_surface, label_surface.get_rect(center=rectangle.center))
        buttons.append(Button(rectangle, label, f"features:{feature}"))
        tooltip_targets.append((rectangle, FEATURE_TOOLTIPS[feature]))
        left += width + 10

    drop_rectangle = pygame.Rect(48, 264, 320, 34)
    box = pygame.Rect(48, 270, 20, 20)
    pygame.draw.rect(surface, BLUE if form.drop_noop else PANEL, box, border_radius=4)
    pygame.draw.rect(surface, BLUE if form.drop_noop else BORDER, box, width=2, border_radius=4)
    if form.drop_noop:
        _text(surface, "✓", (51, 267), 16, PANEL, bold=True)
    _text(surface, "Drop no-op actions from training", (78, 270), 14, INK)
    _text(surface, "Validation data and the CSV remain unchanged.", (390, 270), 13, MUTED)
    buttons.append(Button(drop_rectangle, "Drop no-op", "toggle-drop-noop"))
    tooltip_targets.append((drop_rectangle, DROP_NOOP_TOOLTIP))

    _text(surface, "Hyperparameters", (48, 313), 16, bold=True)
    for index, (name, label) in enumerate(TRAINING_FIELDS):
        column, row = index % 4, index // 4
        x = 48 + column * 206
        y = 342 + row * 80
        _text(surface, label, (x, y), 13, MUTED)
        label_width = _font(13).size(label)[0]
        question_rectangle = pygame.Rect(x + label_width + 7, y - 2, 18, 18)
        pygame.draw.circle(surface, BORDER, question_rectangle.center, 8)
        pygame.draw.circle(surface, MUTED, question_rectangle.center, 8, width=1)
        _text(
            surface,
            "?",
            (question_rectangle.x + 5, question_rectangle.y),
            13,
            MUTED,
            bold=True,
        )
        rectangle = pygame.Rect(x, y + 21, 188, 38)
        pygame.draw.rect(surface, PANEL, rectangle, border_radius=7)
        pygame.draw.rect(
            surface,
            BLUE if active_field == name else BORDER,
            rectangle,
            width=2,
            border_radius=7,
        )
        value = getattr(form, name)
        _text(surface, f"{value}{'|' if active_field == name else ''}", (x + 12, y + 30), 15)
        buttons.append(Button(rectangle, label, f"field:{name}"))
        tooltip_targets.extend(
            (
                (question_rectangle, TRAINING_FIELD_TOOLTIPS[name]),
                (rectangle, TRAINING_FIELD_TOOLTIPS[name]),
            )
        )

    if error:
        _text(surface, error, (48, 509), 13, ERROR, bold=True)
    else:
        _text(
            surface,
            "Tip: change one setting at a time so experiment results are easier to compare.",
            (48, 509),
            13,
            MUTED,
        )

    back = Button(pygame.Rect(48, 572, 150, 44), "Back", "back-to-picker")
    train = Button(pygame.Rect(680, 572, 192, 44), "Start training", "start-training")
    for button, fill, colour in ((back, PANEL, INK), (train, BLUE, PANEL)):
        pygame.draw.rect(surface, fill, button.rectangle, border_radius=8)
        if button is back:
            pygame.draw.rect(surface, BORDER, button.rectangle, width=2, border_radius=8)
        label = "← Datasets" if button is back else "Start training →"
        label_surface = _font(15, bold=True).render(label, True, colour)
        surface.blit(label_surface, label_surface.get_rect(center=button.rectangle.center))
    buttons.extend((back, train))
    try:
        mouse_position = pygame.mouse.get_pos()
    except pygame.error:
        mouse_position = (-1, -1)
    hovered_tooltip = next(
        (value for rectangle, value in tooltip_targets if rectangle.collidepoint(mouse_position)),
        None,
    )
    if hovered_tooltip:
        _draw_tooltip(surface, hovered_tooltip, mouse_position)
    return buttons


def launch(
    run_workflow: Callable[[str, Sequence[str]], int],
    data_directory: Path,
) -> int:
    """Open the launcher and dispatch selected workflows."""
    try:
        pygame.init()
        surface = pygame.display.set_mode(WINDOW_SIZE)
    except pygame.error as error:
        print(f"Could not open the graphical launcher: {error}")
        print("Run with --text to use the terminal menu instead.")
        pygame.quit()
        return 1

    pygame.display.set_caption("Behavior Cloning Lab")
    clock = pygame.time.Clock()
    screen = "home"
    selected_command = ""
    artifacts: list[Path] = []
    inspected_path: Path | None = None
    inspection: Any = None
    action_scroll = 0
    maximum_action_scroll = 0
    training_form: TrainingForm | None = None
    active_training_field: str | None = None
    training_error: str | None = None
    status: tuple[str, bool] | None = None
    running = True

    while running:
        if screen == "home":
            buttons = _draw_home(surface, status)
        elif screen == "collect-choice":
            buttons = _draw_collection_choice(surface)
        elif screen == "inspection":
            buttons = _draw_inspection(surface, inspected_path, inspection)
        elif screen == "action-distribution":
            buttons, maximum_action_scroll = _draw_action_distribution(
                surface, inspected_path, inspection, action_scroll
            )
        elif screen == "train-config":
            buttons = _draw_training_config(
                surface,
                inspected_path,
                training_form,
                active_training_field,
                training_error,
            )
        else:
            buttons = _draw_picker(surface, selected_command, artifacts, data_directory)
        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if screen == "action-distribution":
                        screen = "inspection"
                    elif screen == "train-config":
                        screen = "picker"
                        active_training_field = None
                    elif screen == "collect-choice":
                        screen = "home"
                    elif screen in {"picker", "inspection"}:
                        screen = (
                            "collect-choice"
                            if screen == "picker" and selected_command == "collect"
                            else "home"
                        )
                    else:
                        running = False
                elif screen == "action-distribution":
                    if event.key in {pygame.K_DOWN, pygame.K_PAGEDOWN}:
                        step = 30 if event.key == pygame.K_DOWN else 300
                        action_scroll = min(maximum_action_scroll, action_scroll + step)
                    elif event.key in {pygame.K_UP, pygame.K_PAGEUP}:
                        step = 30 if event.key == pygame.K_UP else 300
                        action_scroll = max(0, action_scroll - step)
                    elif event.key == pygame.K_HOME:
                        action_scroll = 0
                    elif event.key == pygame.K_END:
                        action_scroll = maximum_action_scroll
                elif screen == "train-config" and active_training_field is not None:
                    if event.key in {pygame.K_RETURN, pygame.K_KP_ENTER}:
                        active_training_field = None
                    elif event.key == pygame.K_BACKSPACE:
                        value = getattr(training_form, active_training_field)
                        setattr(training_form, active_training_field, value[:-1])
                        training_error = None
                    elif event.unicode in "0123456789.eE+-":
                        value = getattr(training_form, active_training_field)
                        if len(value) < 16:
                            setattr(training_form, active_training_field, value + event.unicode)
                            training_error = None
                elif screen == "home" and event.unicode in "1234":
                    selected_command = WORKFLOWS[int(event.unicode) - 1][0]
                    if selected_command == "collect":
                        screen = "collect-choice"
                    else:
                        artifacts = discover_artifacts(data_directory, selected_command)
                        screen = "picker"
            elif event.type == pygame.MOUSEWHEEL and screen == "action-distribution":
                action_scroll = max(
                    0, min(maximum_action_scroll, action_scroll - event.y * 60)
                )
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                clicked = next((button for button in buttons if button.contains(event.pos)), None)
                if clicked is None:
                    continue
                if clicked.value == "back":
                    if screen == "inspection":
                        screen = "picker"
                    elif screen == "picker" and selected_command == "collect":
                        screen = "collect-choice"
                    else:
                        screen = "home"
                elif clicked.value == "back-home":
                    screen = "home"
                elif clicked.value == "collect-new":
                    code = run_workflow("collect", ())
                    status = (
                        "Collection finished."
                        if code == 0
                        else "Collection exited with an error.",
                        code == 0,
                    )
                    screen = "home"
                elif clicked.value == "collect-append":
                    selected_command = "collect"
                    artifacts = discover_artifacts(data_directory, selected_command)
                    screen = "picker"
                elif clicked.value == "back-to-picker":
                    screen = "picker"
                    active_training_field = None
                elif clicked.value == "back-to-inspection":
                    screen = "inspection"
                elif clicked.value == "expand-actions":
                    action_scroll = 0
                    screen = "action-distribution"
                elif clicked.value == "train-selected":
                    training_form = TrainingForm.for_preset("balanced")
                    active_training_field = None
                    training_error = None
                    screen = "train-config"
                elif clicked.value.startswith("preset:"):
                    training_form.apply_preset(clicked.value.removeprefix("preset:"))
                    active_training_field = None
                    training_error = None
                elif clicked.value.startswith("features:"):
                    training_form.feature_transform = clicked.value.removeprefix("features:")
                    active_training_field = None
                    training_error = None
                elif clicked.value == "toggle-drop-noop":
                    training_form.drop_noop = not training_form.drop_noop
                    active_training_field = None
                    training_error = None
                elif clicked.value.startswith("field:"):
                    active_training_field = clicked.value.removeprefix("field:")
                    training_error = None
                elif clicked.value == "start-training":
                    try:
                        training_arguments = training_form.arguments(inspected_path)
                    except ValueError as error:
                        training_error = str(error)
                    else:
                        code = run_workflow("train", training_arguments)
                        status = (
                            "Training finished."
                            if code == 0
                            else "Training exited with an error.",
                            code == 0,
                        )
                        screen = "home"
                elif screen == "home":
                    selected_command = clicked.value
                    if selected_command == "collect":
                        screen = "collect-choice"
                    else:
                        artifacts = discover_artifacts(data_directory, selected_command)
                        screen = "picker"
                else:
                    if selected_command == "collect":
                        code = run_workflow(
                            "collect", ("--dataset", str(Path(clicked.value)))
                        )
                        status = (
                            "Collection finished."
                            if code == 0
                            else "Collection exited with an error.",
                            code == 0,
                        )
                        screen = "home"
                    elif selected_command == "inspect":
                        inspected_path = Path(clicked.value)
                        try:
                            inspection = inspect_dataset(
                                inspected_path, data_directory.parent
                            )
                        except (OSError, ValueError) as error:
                            status = (f"Inspection failed: {error}", False)
                            screen = "home"
                        else:
                            screen = "inspection"
                    elif selected_command == "train":
                        inspected_path = Path(clicked.value)
                        training_form = TrainingForm.for_preset("balanced")
                        active_training_field = None
                        training_error = None
                        screen = "train-config"
                    else:
                        code = run_workflow(selected_command, (clicked.value,))
                        title = next(
                            item[2] for item in WORKFLOWS if item[0] == selected_command
                        )
                        status = (
                            f"{title} finished."
                            if code == 0
                            else f"{title} exited with an error.",
                            code == 0,
                        )
                        screen = "home"
        clock.tick(60)

    pygame.quit()
    return 0
