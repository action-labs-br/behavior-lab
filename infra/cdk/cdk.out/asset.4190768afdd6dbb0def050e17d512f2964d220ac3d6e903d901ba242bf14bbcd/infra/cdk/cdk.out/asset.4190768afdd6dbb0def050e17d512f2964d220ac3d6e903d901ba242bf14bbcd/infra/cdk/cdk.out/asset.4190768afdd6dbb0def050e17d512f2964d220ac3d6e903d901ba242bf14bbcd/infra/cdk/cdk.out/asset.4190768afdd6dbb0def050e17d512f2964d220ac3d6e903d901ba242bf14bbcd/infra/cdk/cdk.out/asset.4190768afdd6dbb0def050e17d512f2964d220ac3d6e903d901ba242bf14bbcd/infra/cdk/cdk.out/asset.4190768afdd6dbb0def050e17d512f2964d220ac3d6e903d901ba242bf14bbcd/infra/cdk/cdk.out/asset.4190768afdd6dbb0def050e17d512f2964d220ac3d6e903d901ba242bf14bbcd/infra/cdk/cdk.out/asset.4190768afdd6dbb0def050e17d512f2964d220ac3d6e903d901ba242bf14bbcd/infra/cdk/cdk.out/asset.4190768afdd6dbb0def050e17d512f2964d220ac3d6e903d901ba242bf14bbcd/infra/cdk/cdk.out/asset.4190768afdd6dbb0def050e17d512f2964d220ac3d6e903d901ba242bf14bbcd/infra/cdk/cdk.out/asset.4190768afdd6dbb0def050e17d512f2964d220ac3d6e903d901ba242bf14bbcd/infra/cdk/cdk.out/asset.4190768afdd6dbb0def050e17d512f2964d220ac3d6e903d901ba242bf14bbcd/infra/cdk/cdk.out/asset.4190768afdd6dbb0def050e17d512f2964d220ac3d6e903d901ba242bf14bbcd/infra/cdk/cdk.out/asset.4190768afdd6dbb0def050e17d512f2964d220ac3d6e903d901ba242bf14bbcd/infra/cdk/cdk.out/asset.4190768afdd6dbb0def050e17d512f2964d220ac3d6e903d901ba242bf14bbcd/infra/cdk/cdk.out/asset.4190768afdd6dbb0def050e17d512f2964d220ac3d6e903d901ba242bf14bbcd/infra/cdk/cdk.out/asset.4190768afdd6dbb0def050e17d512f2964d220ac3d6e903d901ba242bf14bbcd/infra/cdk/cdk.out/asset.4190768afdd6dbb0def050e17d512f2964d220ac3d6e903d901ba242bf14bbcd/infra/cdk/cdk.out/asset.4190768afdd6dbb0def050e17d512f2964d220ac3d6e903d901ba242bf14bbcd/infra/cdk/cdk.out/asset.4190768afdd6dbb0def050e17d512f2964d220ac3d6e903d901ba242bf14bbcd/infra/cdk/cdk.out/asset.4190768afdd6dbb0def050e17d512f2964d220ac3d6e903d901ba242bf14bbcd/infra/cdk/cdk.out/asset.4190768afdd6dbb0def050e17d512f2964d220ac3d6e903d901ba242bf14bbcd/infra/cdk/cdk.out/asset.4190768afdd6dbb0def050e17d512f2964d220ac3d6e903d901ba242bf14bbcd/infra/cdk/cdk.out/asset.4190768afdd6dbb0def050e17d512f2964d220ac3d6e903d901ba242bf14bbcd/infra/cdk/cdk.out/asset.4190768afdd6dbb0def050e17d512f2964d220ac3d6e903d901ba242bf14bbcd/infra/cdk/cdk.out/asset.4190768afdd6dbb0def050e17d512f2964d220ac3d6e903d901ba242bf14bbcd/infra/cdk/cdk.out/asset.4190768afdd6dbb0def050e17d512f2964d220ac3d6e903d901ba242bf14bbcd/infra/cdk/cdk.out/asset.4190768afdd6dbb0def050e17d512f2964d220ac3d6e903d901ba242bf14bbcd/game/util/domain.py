from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class GameState:
    blue_x: float
    blue_y: float
    target_x: float
    target_y: float

    def features(self) -> tuple[float, float, float, float]:
        return (self.blue_x, self.blue_y, self.target_x, self.target_y)


@dataclass(frozen=True)
class Action:
    x: float
    y: float

    def values(self) -> tuple[float, float]:
        return (self.x, self.y)


class EpisodeOutcome(str, Enum):
    SUCCESS = "success"
    OUT_OF_BOUNDS = "out_of_bounds"
    STALLED = "stalled"
    QUIT = "quit"
    UNKNOWN = "unknown"


class GameMode(str, Enum):
    COLLECTION = "collection"
    EVALUATION = "evaluation"


@dataclass(frozen=True)
class EpisodeResult:
    episode_id: int
    outcome: EpisodeOutcome
    steps: int


@dataclass(frozen=True)
class TrainingConfig:
    epochs: int = 20
    learning_rate: float = 1e-3
    batch_size: int = 32
    hidden_size: int = 64
    hidden_layers: int = 2
    validation_fraction: float = 0.2
    seed: int = 42
    feature_transform: str = "absolute"

    def validate(self) -> None:
        if self.epochs < 1:
            raise ValueError("epochs must be at least 1")
        if self.learning_rate <= 0:
            raise ValueError("learning_rate must be positive")
        if self.batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        if self.hidden_size < 1:
            raise ValueError("hidden_size must be at least 1")
        if self.hidden_layers not in (2, 4):
            raise ValueError("hidden_layers must be 2 or 4")
        if not 0 < self.validation_fraction < 1:
            raise ValueError("validation_fraction must be between 0 and 1")
        if self.feature_transform not in {
            "absolute",
            "relative-center",
            "relative-containment",
        }:
            raise ValueError(
                "feature_transform must be absolute, relative-center, "
                "or relative-containment"
            )


@dataclass(frozen=True)
class EvaluationConfig:
    episodes: int = 20
    max_steps: int = 500
    seed: int = 42

    def validate(self) -> None:
        if self.episodes < 1:
            raise ValueError("episodes must be at least 1")
        if self.max_steps < 1:
            raise ValueError("max_steps must be at least 1")
