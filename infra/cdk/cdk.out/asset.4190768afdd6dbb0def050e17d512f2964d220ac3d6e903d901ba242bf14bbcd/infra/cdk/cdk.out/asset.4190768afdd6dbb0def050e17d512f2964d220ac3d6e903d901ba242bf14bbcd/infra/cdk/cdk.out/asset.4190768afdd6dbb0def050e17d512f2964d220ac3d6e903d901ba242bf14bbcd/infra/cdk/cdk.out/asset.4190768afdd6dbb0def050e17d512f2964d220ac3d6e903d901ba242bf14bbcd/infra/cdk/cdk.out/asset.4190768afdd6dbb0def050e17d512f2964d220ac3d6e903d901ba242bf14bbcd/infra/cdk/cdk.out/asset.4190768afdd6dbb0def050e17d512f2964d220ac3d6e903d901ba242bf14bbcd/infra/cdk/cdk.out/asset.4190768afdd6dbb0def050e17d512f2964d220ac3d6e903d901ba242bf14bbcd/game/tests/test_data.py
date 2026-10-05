import csv
import tempfile
import unittest
from pathlib import Path

from util.data import DatasetError, Demonstration, EpisodeRecorder, load_demonstrations
from util.domain import Action, EpisodeOutcome, GameState


class DatasetTests(unittest.TestCase):
    def test_all_actions_round_trip_with_episode_outcome(self):
        actions = [
            Action(-5, 0),
            Action(5, 0),
            Action(0, -5),
            Action(0, 5),
            Action(-5, -5),
            Action(0, 0),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demonstrations.csv"
            recorder = EpisodeRecorder(path)
            for step, action in enumerate(actions):
                recorder.record(
                    Demonstration(
                        episode_id=1,
                        step=step,
                        elapsed_ms=step * 16,
                        state=GameState(100, 200, 300, 400),
                        action=action,
                    )
                )

            self.assertEqual(recorder.finish_episode(EpisodeOutcome.SUCCESS), len(actions))
            self.assertEqual(recorder.completed_episodes, 1)
            self.assertEqual(recorder.written_samples, len(actions))
            self.assertEqual(recorder.buffered_samples, 0)
            loaded, legacy = load_demonstrations(path)

        self.assertFalse(legacy)
        self.assertEqual([row.action for row in loaded], actions)
        self.assertEqual({row.outcome for row in loaded}, {EpisodeOutcome.SUCCESS})

    def test_incomplete_episode_can_be_discarded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demonstrations.csv"
            recorder = EpisodeRecorder(path)
            recorder.record(
                Demonstration(1, 0, 0, GameState(0, 0, 10, 10), Action(0, 0))
            )
            recorder.discard_episode()
            self.assertEqual(recorder.finish_episode(EpisodeOutcome.QUIT), 0)
            self.assertFalse(path.exists())

    def test_current_repository_dataset_loads_as_legacy(self):
        path = Path(__file__).parents[1] / "data" / "demonstrations_20241218_161040.csv"
        rows, legacy = load_demonstrations(path)
        self.assertTrue(legacy)
        self.assertGreater(len(rows), 0)
        self.assertEqual(rows[0].outcome, EpisodeOutcome.UNKNOWN)

    def test_bad_schema_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            with path.open("w", newline="", encoding="utf-8") as stream:
                csv.DictWriter(stream, fieldnames=["wrong"]).writeheader()

            with self.assertRaisesRegex(DatasetError, "unsupported schema"):
                load_demonstrations(path)
