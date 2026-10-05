"""Small, dependency-free summaries of behavior-cloning demonstrations."""

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from util.data import Demonstration
from util.domain import EpisodeOutcome


FEATURE_NAMES = ("blue_x", "blue_y", "target_x", "target_y")
LABEL_NAMES = ("action_x", "action_y")


@dataclass(frozen=True)
class DatasetSummary:
    samples: int
    episodes: int
    outcomes: dict[str, int]
    action_histogram: dict[tuple[float, float], int]
    no_op_ratio: float
    coordinate_ranges: dict[str, tuple[float, float]]
    warnings: tuple[str, ...]
    legacy: bool = False


def summarize_demonstrations(
    rows: Iterable[Demonstration], *, legacy: bool = False
) -> DatasetSummary:
    """Return deterministic counts and beginner-focused quality warnings."""
    demonstrations = list(rows)
    episode_outcomes: dict[int, set[EpisodeOutcome]] = {}
    for row in demonstrations:
        episode_outcomes.setdefault(row.episode_id, set()).add(row.outcome)

    outcomes = {outcome.value: 0 for outcome in EpisodeOutcome}
    inconsistent_episodes = 0
    for values in episode_outcomes.values():
        if len(values) == 1:
            outcomes[next(iter(values)).value] += 1
        else:
            inconsistent_episodes += 1

    action_counts = Counter(row.action.values() for row in demonstrations)
    action_histogram = dict(sorted(action_counts.items()))
    no_op_count = action_counts.get((0.0, 0.0), 0)
    no_op_ratio = no_op_count / len(demonstrations) if demonstrations else 0.0

    coordinate_ranges: dict[str, tuple[float, float]] = {}
    if demonstrations:
        values = {
            "blue_x": [row.state.blue_x for row in demonstrations],
            "blue_y": [row.state.blue_y for row in demonstrations],
            "target_x": [row.state.target_x for row in demonstrations],
            "target_y": [row.state.target_y for row in demonstrations],
        }
        coordinate_ranges = {
            name: (min(coordinates), max(coordinates))
            for name, coordinates in values.items()
        }

    warnings: list[str] = []
    if not demonstrations:
        warnings.append("This dataset has no samples. Record a demonstration before training.")
    elif len(episode_outcomes) < 3:
        warnings.append(
            "This dataset has fewer than 3 episodes. Record more episodes before training."
        )
    if legacy:
        warnings.append(
            "This is a legacy dataset: episode outcomes were not recorded and are unknown."
        )
    if inconsistent_episodes:
        warnings.append(
            f"{inconsistent_episodes} episode(s) contain conflicting outcomes; check the CSV."
        )
    if demonstrations and no_op_ratio > 0.5:
        warnings.append(
            "More than half of the labels are no-op actions; movement may be under-represented."
        )
    if demonstrations and len(action_counts) == 1:
        warnings.append(
            "Only one action appears in the dataset; demonstrate movement in more directions."
        )

    return DatasetSummary(
        samples=len(demonstrations),
        episodes=len(episode_outcomes),
        outcomes=outcomes,
        action_histogram=action_histogram,
        no_op_ratio=no_op_ratio,
        coordinate_ranges=coordinate_ranges,
        warnings=tuple(warnings),
        legacy=legacy,
    )


def format_summary(summary: DatasetSummary) -> str:
    """Render a summary in plain language suitable for a first ML lesson."""
    lines = [
        "Dataset summary",
        "===============",
        f"Samples (state/action pairs): {summary.samples}",
        f"Episodes (game attempts): {summary.episodes}",
        "",
        "Features (X): blue_x, blue_y, target_x, target_y",
        "  X describes what the model can see before it chooses a move.",
        "Labels (y): action_x, action_y",
        "  y is the player's move that the model learns to imitate.",
        "",
        "Episode outcomes:",
    ]
    lines.extend(f"  {name}: {count}" for name, count in summary.outcomes.items())
    lines.extend(("", "Action distribution:"))
    if summary.action_histogram:
        lines.extend(
            f"  ({x:g}, {y:g}): {count}"
            for (x, y), count in summary.action_histogram.items()
        )
    else:
        lines.append("  (no actions)")
    lines.append(f"  No-op ratio: {summary.no_op_ratio:.1%}")
    lines.extend(("", "Coordinate ranges:"))
    if summary.coordinate_ranges:
        lines.extend(
            f"  {name}: {low:g} to {high:g}"
            for name, (low, high) in summary.coordinate_ranges.items()
        )
    else:
        lines.append("  (no coordinates)")
    lines.extend(("", "Guidance:"))
    if summary.warnings:
        lines.extend(f"  - {warning}" for warning in summary.warnings)
    else:
        lines.append("  No obvious data-quality warnings.")
    return "\n".join(lines)
