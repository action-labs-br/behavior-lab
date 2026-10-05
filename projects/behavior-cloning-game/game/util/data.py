import csv
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

from util.domain import Action, EpisodeOutcome, GameState


SCHEMA_VERSION = 2
CSV_COLUMNS = (
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
)
LEGACY_COLUMNS = (
    "Execution",
    "clock",
    "current_position_x",
    "current_position_y",
    "target_position_x",
    "target_position_y",
    "move_x",
    "move_y",
)


class DatasetError(ValueError):
    """An actionable problem with a demonstration dataset."""


@dataclass(frozen=True)
class Demonstration:
    episode_id: int
    step: int
    elapsed_ms: int
    state: GameState
    action: Action
    outcome: EpisodeOutcome = EpisodeOutcome.UNKNOWN
    schema_version: int = SCHEMA_VERSION

    def as_row(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "episode_id": self.episode_id,
            "step": self.step,
            "elapsed_ms": self.elapsed_ms,
            "blue_x": self.state.blue_x,
            "blue_y": self.state.blue_y,
            "target_x": self.state.target_x,
            "target_y": self.state.target_y,
            "action_x": self.action.x,
            "action_y": self.action.y,
            "outcome": self.outcome.value,
        }


class EpisodeRecorder:
    def __init__(
        self,
        destination: str | Path,
        *,
        completed_episodes: int = 0,
        written_samples: int = 0,
    ):
        self.destination = Path(destination)
        self._buffer: list[Demonstration] = []
        self.completed_episodes = completed_episodes
        self.written_samples = written_samples

    @property
    def buffered_samples(self) -> int:
        return len(self._buffer)

    def record(self, demonstration: Demonstration) -> None:
        self._buffer.append(demonstration)

    def finish_episode(self, outcome: EpisodeOutcome) -> int:
        completed = [replace(row, outcome=outcome) for row in self._buffer]
        self._buffer.clear()
        if not completed:
            return 0

        self.destination.parent.mkdir(parents=True, exist_ok=True)
        exists = self.destination.exists() and self.destination.stat().st_size > 0
        with self.destination.open("a", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS)
            if not exists:
                writer.writeheader()
            writer.writerows(row.as_row() for row in completed)
        self.completed_episodes += 1
        self.written_samples += len(completed)
        return len(completed)

    def discard_episode(self) -> None:
        self._buffer.clear()


def write_demonstrations(path: str | Path, rows: Iterable[Demonstration]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(row.as_row() for row in rows)


def load_demonstrations(path: str | Path) -> tuple[list[Demonstration], bool]:
    source = Path(path)
    if not source.exists():
        raise DatasetError(f"Dataset not found: {source}")
    if source.stat().st_size == 0:
        raise DatasetError(f"Dataset is empty: {source}")

    with source.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        columns = tuple(reader.fieldnames or ())
        if set(CSV_COLUMNS).issubset(columns):
            return [_parse_v2(row, source) for row in reader], False
        if set(LEGACY_COLUMNS).issubset(columns):
            return _parse_legacy(reader, source), True

    missing_v2 = sorted(set(CSV_COLUMNS) - set(columns))
    raise DatasetError(
        f"Dataset {source} has an unsupported schema. Missing v2 columns: "
        f"{', '.join(missing_v2)}"
    )


def _parse_v2(row: dict[str, str], source: Path) -> Demonstration:
    try:
        version = int(row["schema_version"])
        if version != SCHEMA_VERSION:
            raise DatasetError(
                f"Dataset {source} uses schema version {version}; expected {SCHEMA_VERSION}"
            )
        return Demonstration(
            episode_id=int(row["episode_id"]),
            step=int(row["step"]),
            elapsed_ms=int(row["elapsed_ms"]),
            state=GameState(
                float(row["blue_x"]),
                float(row["blue_y"]),
                float(row["target_x"]),
                float(row["target_y"]),
            ),
            action=Action(float(row["action_x"]), float(row["action_y"])),
            outcome=EpisodeOutcome(row["outcome"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, DatasetError):
            raise
        raise DatasetError(f"Dataset {source} contains an invalid row: {error}") from error


def _parse_legacy(reader: Iterable[dict[str, str]], source: Path) -> list[Demonstration]:
    rows: list[Demonstration] = []
    steps: dict[int, int] = {}
    try:
        for row in reader:
            episode_id = int(row["Execution"])
            step = steps.get(episode_id, 0)
            steps[episode_id] = step + 1
            rows.append(
                Demonstration(
                    episode_id=episode_id,
                    step=step,
                    elapsed_ms=int(row["clock"]),
                    state=GameState(
                        float(row["current_position_x"]),
                        float(row["current_position_y"]),
                        float(row["target_position_x"]),
                        float(row["target_position_y"]),
                    ),
                    action=Action(float(row["move_x"]), float(row["move_y"])),
                )
            )
    except (KeyError, TypeError, ValueError) as error:
        raise DatasetError(f"Legacy dataset {source} contains an invalid row: {error}") from error
    return rows
