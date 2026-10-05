"""Inspectable state feature transforms shared by training and inference."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from util.domain import GameState


SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
BLUE_DIAMETER = 50
TARGET_SIZE = 70
CONTAINMENT_MARGIN = TARGET_SIZE - BLUE_DIAMETER


@dataclass(frozen=True)
class FeatureTransform:
    name: str
    feature_names: tuple[str, ...]
    apply: Callable[[GameState], tuple[float, ...]]


def _absolute(state: GameState) -> tuple[float, float, float, float]:
    return state.features()


def _relative_center(state: GameState) -> tuple[float, float]:
    blue_center_x = state.blue_x + BLUE_DIAMETER / 2
    blue_center_y = state.blue_y + BLUE_DIAMETER / 2
    target_center_x = state.target_x + TARGET_SIZE / 2
    target_center_y = state.target_y + TARGET_SIZE / 2
    return (
        (target_center_x - blue_center_x) / SCREEN_WIDTH,
        (target_center_y - blue_center_y) / SCREEN_HEIGHT,
    )


def _containment_error(position: float, target: float) -> float:
    if position < target:
        return target - position
    if position > target + CONTAINMENT_MARGIN:
        return target + CONTAINMENT_MARGIN - position
    return 0.0


def _relative_containment(state: GameState) -> tuple[float, float]:
    return (
        _containment_error(state.blue_x, state.target_x) / SCREEN_WIDTH,
        _containment_error(state.blue_y, state.target_y) / SCREEN_HEIGHT,
    )


FEATURE_TRANSFORMS = {
    "absolute": FeatureTransform(
        "absolute",
        ("blue_x", "blue_y", "target_x", "target_y"),
        _absolute,
    ),
    "relative-center": FeatureTransform(
        "relative-center",
        ("relative_center_x", "relative_center_y"),
        _relative_center,
    ),
    "relative-containment": FeatureTransform(
        "relative-containment",
        ("containment_error_x", "containment_error_y"),
        _relative_containment,
    ),
}


def get_feature_transform(name: str) -> FeatureTransform:
    try:
        return FEATURE_TRANSFORMS[name]
    except KeyError as error:
        choices = ", ".join(FEATURE_TRANSFORMS)
        raise ValueError(f"Unknown feature transform {name!r}; choose one of: {choices}") from error
