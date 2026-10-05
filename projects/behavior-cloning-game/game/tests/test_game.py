import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from util.coordinate import Coordinate
from util.data import EpisodeRecorder, load_demonstrations
from util.domain import EpisodeOutcome, GameMode
from util.game import Game
from util.rectangle import Rectangle
from util.screen import Screen


class FakeInput:
    def __init__(self, moves=None):
        self.moves = list(moves or [Coordinate(0, 0)])
        self.quit_requested = False
        self.starts = []
        self.targets = []

    def reset_move(self):
        pass

    def goto(self, x, y):
        self.starts.append((x, y))

    def move_target(self, x, y):
        self.targets.append((x, y))

    def get_move(self):
        return self.moves.pop(0) if self.moves else Coordinate(0, 0)


class FakeDisplay:
    def __init__(self, outcomes=None):
        self.screen = Screen(100, 100)
        self.car = Rectangle(0, 0, 10, 10)
        self.parking = Rectangle(0, 0, 20, 20)
        self.outcomes = list(outcomes or [])
        self.message = None

    def set_caption(self, text):
        pass

    def set_background(self):
        pass

    def draw_parking(self):
        pass

    def draw_car(self):
        pass

    def message_display(self, text):
        self.message = text

    def is_car_inside_parking(self):
        return bool(self.outcomes and self.outcomes.pop(0))

    def is_car_out_of_bounds(self):
        return False


class GameLifecycleTests(unittest.TestCase):
    def test_collection_hud_shows_player_controls_and_data_progress(self):
        game = Game(
            FakeInput(),
            io.StringIO(),
            display=FakeDisplay(),
            framerate=0,
            round_delay_ms=0,
            mode=GameMode.COLLECTION,
        )
        game.episode_limit = 10

        text = game._hud_text(3)

        self.assertIn("COLLECT", text)
        self.assertIn("Arrows Move", text)
        self.assertIn("Space Pause", text)
        self.assertIn("Ep 3/10", text)
        self.assertIn("Samples 0", text)

    def test_evaluation_hud_hides_player_controls_and_shows_results(self):
        game = Game(
            FakeInput(),
            io.StringIO(),
            display=FakeDisplay(),
            framerate=0,
            round_delay_ms=0,
            mode=GameMode.EVALUATION,
        )
        game.episode_limit = 5
        game.num_success = 2

        text = game._hud_text(4)

        self.assertIn("MODEL EVALUATION", text)
        self.assertIn("Attempt 4/5", text)
        self.assertIn("Successes 2", text)
        self.assertNotIn("Arrows", text)
        self.assertNotIn("pause", text.lower())

    @patch("util.game.pygame.display.update")
    def test_many_episodes_are_iterative_and_report_a_true_percentage(self, update):
        display = FakeDisplay([True] * 1100)
        output = io.StringIO()
        game = Game(
            FakeInput(),
            output,
            display=display,
            seed=7,
            framerate=0,
            round_delay_ms=0,
        )

        with patch("builtins.print") as print_message:
            results = game.start(max_episodes=1100)

        self.assertEqual(len(results), 1100)
        self.assertTrue(all(result.outcome == EpisodeOutcome.SUCCESS for result in results))
        print_message.assert_called_with("1100: 100.00%")

    @patch("util.game.pygame.display.update")
    def test_records_negative_and_stationary_actions(self, update):
        display = FakeDisplay([False, False])
        output = io.StringIO()
        game = Game(
            FakeInput([Coordinate(-5, 0), Coordinate(0, 0)]),
            output,
            display=display,
            seed=1,
            framerate=0,
            staleness_factor=0,
            round_delay_ms=0,
        )

        result = game.run_episode(1)

        self.assertEqual(result.outcome, EpisodeOutcome.STALLED)
        rows = output.getvalue().splitlines()
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[0].endswith(",-5,0"))
        self.assertTrue(rows[1].endswith(",0,0"))

    def test_seed_reproduces_target_positions(self):
        first_input = FakeInput()
        second_input = FakeInput()
        first = Game(
            first_input,
            io.StringIO(),
            display=FakeDisplay(),
            seed=42,
            framerate=0,
            round_delay_ms=0,
        )
        second = Game(
            second_input,
            io.StringIO(),
            display=FakeDisplay(),
            seed=42,
            framerate=0,
            round_delay_ms=0,
        )

        first._reset_episode()
        second._reset_episode()

        self.assertEqual(first_input.targets, second_input.targets)
        self.assertGreaterEqual(first_input.targets[0][1], first.display.screen.play_area_top)

    @patch("util.game.pygame.display.update")
    def test_completed_episode_records_versioned_pre_action_states(self, update):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demonstrations.csv"
            display = FakeDisplay([False, True])
            game = Game(
                FakeInput([Coordinate(-5, 0), Coordinate(0, 5)]),
                io.StringIO(),
                display=display,
                seed=1,
                framerate=0,
                recorder=EpisodeRecorder(path),
                round_delay_ms=0,
            )

            result = game.run_episode(1)
            rows, legacy = load_demonstrations(path)

        self.assertEqual(result.outcome, EpisodeOutcome.SUCCESS)
        self.assertFalse(legacy)
        self.assertEqual(rows[0].action.x, -5)
        self.assertEqual(rows[0].state.blue_x, 45)
        self.assertEqual(rows[1].state.blue_x, 40)
        self.assertEqual({row.outcome for row in rows}, {EpisodeOutcome.SUCCESS})

    @patch("util.game.pygame.display.update")
    def test_waits_after_showing_round_result(self, update):
        game = Game(
            FakeInput([Coordinate(0, 0)]),
            io.StringIO(),
            display=FakeDisplay([True]),
            seed=1,
            framerate=0,
        )

        with patch.object(game, "_wait_between_rounds") as wait:
            game.run_episode(1)

        wait.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
