import tempfile
import unittest
from pathlib import Path

from util.data import Demonstration
from util.domain import Action, GameState
from util.downsampling import (
    DownsampleContext,
    DownsampleResult,
    available_downsamplers,
    load_downsampler,
)


def row(episode_id: int, step: int, action: Action) -> Demonstration:
    return Demonstration(
        episode_id=episode_id,
        step=step,
        elapsed_ms=step * 16,
        state=GameState(100 + step, 100, 200, 200),
        action=action,
    )


class DownsamplingTests(unittest.TestCase):
    def test_drop_noop_plugin_keeps_only_movement_rows(self):
        rows = [
            row(1, 0, Action(0, 0)),
            row(1, 1, Action(5, 0)),
            row(2, 0, Action(0, -5)),
        ]
        plugin = load_downsampler("drop-noop")

        result = plugin.apply(rows, DownsampleContext(seed=42))

        self.assertEqual([item.action for item in result.rows], [Action(5, 0), Action(0, -5)])
        self.assertIn("Removed 1", result.description)
        self.assertEqual(len(plugin.source_hash), 64)

    def test_plugin_name_cannot_escape_downsampler_directory(self):
        with self.assertRaisesRegex(ValueError, "names may contain"):
            load_downsampler("../outside")

    def test_invalid_plugin_contract_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "broken.py").write_text("DOWNSAMPLER = object()\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must export"):
                load_downsampler("broken", directory)

    def test_available_plugins_include_drop_noop(self):
        self.assertIn("drop-noop", available_downsamplers())

    def test_plugin_can_remove_an_all_noop_training_episode(self):
        plugin = load_downsampler("drop-noop")
        rows = [row(1, 0, Action(0, 0)), row(2, 0, Action(5, 0))]

        result = plugin.apply(rows, DownsampleContext(seed=42))

        self.assertEqual([item.episode_id for item in result.rows], [2])


if __name__ == "__main__":
    unittest.main()
