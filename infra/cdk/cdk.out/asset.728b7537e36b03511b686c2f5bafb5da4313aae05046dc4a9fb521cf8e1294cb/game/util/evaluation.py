"""Finite, deterministic and headless policy evaluation.

This module deliberately keeps the game rules visible.  A policy receives the
four values in :class:`GameState` and returns a two-dimensional action; the
evaluator applies that action until the box succeeds, leaves the screen, or
uses the configured step budget.
"""

from __future__ import annotations

import json
import random
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Sequence

import torch

from util.domain import Action, EpisodeOutcome, EvaluationConfig, GameState
from util.screen import HUD_HEIGHT
from util.features import FeatureTransform, get_feature_transform


Policy = Callable[[GameState], Action]


@dataclass(frozen=True)
class Scenario:
    blue_x: float
    blue_y: float
    target_x: float
    target_y: float

    def initial_state(self) -> GameState:
        return GameState(self.blue_x, self.blue_y, self.target_x, self.target_y)


@dataclass(frozen=True)
class EvaluationEpisode:
    episode_id: int
    scenario: Scenario
    outcome: EpisodeOutcome
    steps: int
    trajectory: tuple[GameState, ...] = ()


@dataclass(frozen=True)
class EvaluationMetrics:
    episodes: int
    successes: int
    success_rate: float
    mean_successful_steps: float | None
    median_successful_steps: float | None
    stalled: int
    out_of_bounds: int


@dataclass(frozen=True)
class EvaluationResult:
    config: EvaluationConfig
    metrics: EvaluationMetrics
    episodes: tuple[EvaluationEpisode, ...]
    policy_name: str
    experiment: str | None = None


def seeded_scenarios(
    config: EvaluationConfig,
    *,
    screen_size: tuple[int, int] = (800, 600),
    blue_size: int = 50,
    target_size: int = 70,
    play_area_top: int = HUD_HEIGHT,
) -> tuple[Scenario, ...]:
    """Create the exact scenarios used by the interactive game."""
    config.validate()
    width, height = screen_size
    if target_size < blue_size:
        raise ValueError("target_size must be at least as large as blue_size")
    if width < target_size or height < target_size:
        raise ValueError("screen must be large enough to contain the target")
    blue_x = (width - blue_size) / 2
    blue_y = (height - blue_size) / 2
    generator = random.Random(config.seed)
    return tuple(
        Scenario(
            blue_x,
            blue_y,
            generator.randint(0, width - target_size),
            generator.randint(play_area_top, height - target_size),
        )
        for _ in range(config.episodes)
    )


def _inside_target(state: GameState, blue_size: int, target_size: int) -> bool:
    return (
        state.blue_x >= state.target_x
        and state.blue_x + blue_size <= state.target_x + target_size
        and state.blue_y >= state.target_y
        and state.blue_y + blue_size <= state.target_y + target_size
    )


def evaluate_policy(
    policy: Policy,
    config: EvaluationConfig = EvaluationConfig(),
    *,
    policy_name: str = "model",
    experiment: str | None = None,
    scenarios: Sequence[Scenario] | None = None,
    screen_size: tuple[int, int] = (800, 600),
    blue_size: int = 50,
    target_size: int = 70,
    play_area_top: int = HUD_HEIGHT,
    capture_trajectory: bool = False,
) -> EvaluationResult:
    """Evaluate ``policy`` on a finite scenario set without opening a window."""
    config.validate()
    chosen = tuple(scenarios) if scenarios is not None else seeded_scenarios(
        config,
        screen_size=screen_size,
        blue_size=blue_size,
        target_size=target_size,
        play_area_top=play_area_top,
    )
    if len(chosen) != config.episodes:
        raise ValueError(
            f"Expected {config.episodes} evaluation scenarios, received {len(chosen)}"
        )

    width, height = screen_size
    episode_results: list[EvaluationEpisode] = []
    for episode_id, scenario in enumerate(chosen, start=1):
        state = scenario.initial_state()
        trajectory = [state] if capture_trajectory else []
        outcome = EpisodeOutcome.STALLED
        steps = 0
        if _inside_target(state, blue_size, target_size):
            outcome = EpisodeOutcome.SUCCESS
        else:
            for steps in range(1, config.max_steps + 1):
                action = policy(state)
                if not isinstance(action, Action):
                    raise TypeError("Policies must return an Action")
                state = GameState(
                    state.blue_x + action.x,
                    state.blue_y + action.y,
                    state.target_x,
                    state.target_y,
                )
                if capture_trajectory:
                    trajectory.append(state)
                if _inside_target(state, blue_size, target_size):
                    outcome = EpisodeOutcome.SUCCESS
                    break
                if (
                    state.blue_x < 0
                    or state.blue_x > width - blue_size
                    or state.blue_y < play_area_top
                    or state.blue_y > height - blue_size
                ):
                    outcome = EpisodeOutcome.OUT_OF_BOUNDS
                    break
        episode_results.append(
            EvaluationEpisode(episode_id, scenario, outcome, steps, tuple(trajectory))
        )

    successful_steps = [
        episode.steps
        for episode in episode_results
        if episode.outcome == EpisodeOutcome.SUCCESS
    ]
    successes = len(successful_steps)
    stalled = sum(e.outcome == EpisodeOutcome.STALLED for e in episode_results)
    out_of_bounds = sum(
        e.outcome == EpisodeOutcome.OUT_OF_BOUNDS for e in episode_results
    )
    metrics = EvaluationMetrics(
        episodes=len(episode_results),
        successes=successes,
        success_rate=successes / len(episode_results),
        mean_successful_steps=(statistics.mean(successful_steps) if successful_steps else None),
        median_successful_steps=(
            statistics.median(successful_steps) if successful_steps else None
        ),
        stalled=stalled,
        out_of_bounds=out_of_bounds,
    )
    return EvaluationResult(config, metrics, tuple(episode_results), policy_name, experiment)


def heuristic_policy(state: GameState, step_size: float = 5) -> Action:
    """A transparent expert that heads for the nearest valid target position."""
    max_blue_offset = 20  # 70-pixel target minus 50-pixel circle diameter

    def movement(position: float, target: float) -> float:
        if position < target:
            return min(step_size, target - position)
        if position > target + max_blue_offset:
            return max(-step_size, target + max_blue_offset - position)
        return 0.0

    return Action(
        movement(state.blue_x, state.target_x),
        movement(state.blue_y, state.target_y),
    )


def untrained_policy(state: GameState) -> Action:
    """A no-learning baseline: take no action regardless of state."""
    return Action(0.0, 0.0)


def torch_policy(
    model: torch.nn.Module,
    feature_transform: FeatureTransform | None = None,
) -> Policy:
    """Adapt a regression model to the small policy protocol."""
    model.eval()
    transform = feature_transform or get_feature_transform("absolute")

    def predict(state: GameState) -> Action:
        with torch.no_grad():
            features = torch.tensor([transform.apply(state)], dtype=torch.float32)
            prediction = torch.round(model(features).cpu())[0]
        return Action(float(prediction[0]), float(prediction[1]))

    return predict


def save_evaluation(result: EvaluationResult, destination: str | Path) -> Path:
    """Save metrics and per-episode results as portable JSON."""
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(result)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def compare_experiments(paths: Sequence[str | Path]) -> list[dict[str, object]]:
    """Read training/evaluation JSON files into concise comparison rows."""
    comparison = []
    for source in paths:
        path = Path(source)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Could not read experiment result {path}: {error}") from error
        metrics = document.get("metrics", {})
        config = document.get("config", {})
        is_evaluation = "successes" in metrics
        comparison.append(
            {
                "path": str(path),
                "kind": "evaluation" if is_evaluation else "training",
                "dataset_fingerprint": document.get("dataset_fingerprint"),
                "episodes": metrics.get("episodes"),
                "success_rate": metrics.get("success_rate"),
                "best_epoch": metrics.get("best_epoch"),
                "best_validation_loss": (
                    min(metrics.get("validation_loss", []))
                    if metrics.get("validation_loss")
                    else None
                ),
                "epochs": config.get("epochs"),
                "learning_rate": config.get("learning_rate"),
            }
        )
    return comparison
