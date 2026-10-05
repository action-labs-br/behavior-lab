import unittest

from util.data import Demonstration
from util.domain import Action, EpisodeOutcome, GameState
from util.inspection import format_summary, summarize_demonstrations


def row(
    episode: int,
    step: int,
    action: tuple[float, float],
    outcome: EpisodeOutcome,
    state: tuple[float, float, float, float],
) -> Demonstration:
    return Demonstration(
        episode_id=episode,
        step=step,
        elapsed_ms=step * 10,
        state=GameState(*state),
        action=Action(*action),
        outcome=outcome,
    )


class DatasetInspectionTests(unittest.TestCase):
    def test_summary_counts_ranges_and_actions_deterministically(self):
        rows = [
            row(1, 0, (0, 0), EpisodeOutcome.SUCCESS, (10, 20, 100, 200)),
            row(1, 1, (5, 0), EpisodeOutcome.SUCCESS, (15, 20, 100, 200)),
            row(2, 0, (-5, 0), EpisodeOutcome.STALLED, (30, 40, 80, 160)),
            row(3, 0, (0, 0), EpisodeOutcome.OUT_OF_BOUNDS, (5, 50, 120, 150)),
        ]

        summary = summarize_demonstrations(rows)

        self.assertEqual(summary.samples, 4)
        self.assertEqual(summary.episodes, 3)
        self.assertEqual(summary.outcomes["success"], 1)
        self.assertEqual(summary.outcomes["stalled"], 1)
        self.assertEqual(summary.outcomes["out_of_bounds"], 1)
        self.assertEqual(
            summary.action_histogram, {(-5, 0): 1, (0, 0): 2, (5, 0): 1}
        )
        self.assertEqual(summary.no_op_ratio, 0.5)
        self.assertEqual(summary.coordinate_ranges["blue_x"], (5, 30))
        self.assertEqual(summary.coordinate_ranges["target_y"], (150, 200))
        self.assertEqual(summary.warnings, ())

    def test_legacy_and_imbalanced_data_has_plain_language_guidance(self):
        rows = [
            row(1, index, (0, 0), EpisodeOutcome.UNKNOWN, (1, 2, 3, 4))
            for index in range(3)
        ]

        summary = summarize_demonstrations(rows, legacy=True)
        rendered = format_summary(summary)

        self.assertIn("fewer than 3 episodes", rendered)
        self.assertIn("legacy dataset", rendered)
        self.assertIn("More than half", rendered)
        self.assertIn("Only one action", rendered)
        self.assertIn("Features (X)", rendered)
        self.assertIn("Labels (y)", rendered)

    def test_empty_data_is_safe_to_inspect(self):
        summary = summarize_demonstrations([])

        self.assertEqual(summary.samples, 0)
        self.assertEqual(summary.coordinate_ranges, {})
        self.assertEqual(summary.no_op_ratio, 0.0)
        self.assertIn("no samples", summary.warnings[0])


if __name__ == "__main__":
    unittest.main()
