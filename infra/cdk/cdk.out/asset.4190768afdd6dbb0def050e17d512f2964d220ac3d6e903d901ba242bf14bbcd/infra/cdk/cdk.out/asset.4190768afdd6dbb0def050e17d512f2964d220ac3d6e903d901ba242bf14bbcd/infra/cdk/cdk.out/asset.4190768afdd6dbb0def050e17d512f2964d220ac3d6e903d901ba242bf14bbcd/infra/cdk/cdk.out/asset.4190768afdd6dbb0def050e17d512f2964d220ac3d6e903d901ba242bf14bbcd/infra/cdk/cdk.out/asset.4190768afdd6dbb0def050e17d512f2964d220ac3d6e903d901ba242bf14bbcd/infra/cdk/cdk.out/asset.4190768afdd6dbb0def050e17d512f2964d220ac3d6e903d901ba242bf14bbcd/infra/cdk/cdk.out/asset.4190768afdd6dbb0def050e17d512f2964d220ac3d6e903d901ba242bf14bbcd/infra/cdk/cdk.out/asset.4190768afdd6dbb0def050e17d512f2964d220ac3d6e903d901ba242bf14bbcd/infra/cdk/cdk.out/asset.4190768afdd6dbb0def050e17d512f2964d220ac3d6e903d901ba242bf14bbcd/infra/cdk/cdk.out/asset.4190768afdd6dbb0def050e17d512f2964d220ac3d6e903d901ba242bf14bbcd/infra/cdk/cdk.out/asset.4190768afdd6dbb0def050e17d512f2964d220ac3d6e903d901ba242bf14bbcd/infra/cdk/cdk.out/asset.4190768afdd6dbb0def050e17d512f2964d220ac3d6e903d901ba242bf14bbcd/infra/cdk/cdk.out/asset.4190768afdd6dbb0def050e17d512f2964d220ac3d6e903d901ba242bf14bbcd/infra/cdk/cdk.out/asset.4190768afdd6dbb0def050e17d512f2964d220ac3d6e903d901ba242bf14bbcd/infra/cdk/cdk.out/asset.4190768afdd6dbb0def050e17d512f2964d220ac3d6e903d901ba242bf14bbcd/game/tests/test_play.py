import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import play

from util.data import Demonstration, write_demonstrations
from util.domain import Action, EpisodeOutcome, GameState


def demonstration(episode_id: int) -> Demonstration:
    return Demonstration(
        episode_id=episode_id,
        step=0,
        elapsed_ms=0,
        state=GameState(100, 100, 200, 200),
        action=Action(5, 0),
        outcome=EpisodeOutcome.SUCCESS,
    )


class ResumeCollectionTests(unittest.TestCase):
    def test_dataset_resumes_after_highest_episode_and_preserves_hud_totals(self):
        with tempfile.TemporaryDirectory() as directory:
            dataset = Path(directory) / "existing.csv"
            write_demonstrations(dataset, [demonstration(2), demonstration(7)])
            game = Mock()
            game.start.return_value = []

            with patch.object(play, "Game", return_value=game) as game_type:
                status = play.main(["--dataset", str(dataset), "--episodes", "3"])

        self.assertEqual(status, 0)
        game.start.assert_called_once_with(execution_id=7, max_episodes=3)
        recorder = game_type.call_args.kwargs["recorder"]
        self.assertEqual(recorder.completed_episodes, 2)
        self.assertEqual(recorder.written_samples, 2)

    def test_legacy_dataset_is_rejected_before_game_starts(self):
        dataset = (
            Path(__file__).parents[1]
            / "data"
            / "demonstrations_20241218_161040.csv"
        )
        with patch.object(play, "Game") as game_type:
            status = play.main(["--dataset", str(dataset)])

        self.assertEqual(status, 1)
        game_type.assert_not_called()

    def test_existing_output_requires_explicit_dataset_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            dataset = Path(directory) / "existing.csv"
            dataset.write_text("already here", encoding="utf-8")

            with patch.object(play, "Game") as game_type:
                status = play.main(["--output", str(dataset)])

        self.assertEqual(status, 1)
        game_type.assert_not_called()


if __name__ == "__main__":
    unittest.main()
