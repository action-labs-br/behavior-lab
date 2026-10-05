import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import execute
import torch

from util.domain import Action, EpisodeOutcome, EvaluationConfig
from util.evaluation import (
    compare_experiments,
    evaluate_policy,
    heuristic_policy,
    save_evaluation,
    seeded_scenarios,
    untrained_policy,
)
from util.features import get_feature_transform
from util.model import ContinuousPolicyNetwork


class EvaluationTests(unittest.TestCase):
    def test_transformed_weights_require_paired_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "relative.pth"
            model = ContinuousPolicyNetwork(input_size=2, hidden_size=8, hidden_layers=2)
            torch.save(model.state_dict(), checkpoint)

            with self.assertRaisesRegex(ValueError, "paired .json"):
                execute._legacy_model(checkpoint)

    def test_execute_uses_visible_game_by_default(self):
        model = Mock()
        game = Mock()
        game.start.return_value = []
        with (
            patch.object(
                execute,
                "_resolve_model",
                return_value=(model, None, get_feature_transform("absolute")),
            ),
            patch.object(execute.FromModel, "from_model", return_value=Mock()),
            patch.object(execute, "Game", return_value=game) as game_type,
        ):
            self.assertEqual(execute.main(["model.pth", "--episodes", "2"]), 0)

        game_type.assert_called_once()
        game.start.assert_called_once_with(max_episodes=2)
        game.quit.assert_called_once()

    def test_seed_reproduces_scenarios_and_different_seed_changes_them(self):
        config = EvaluationConfig(episodes=5, max_steps=100, seed=12)
        scenarios = seeded_scenarios(config)
        self.assertEqual(scenarios, seeded_scenarios(config))
        self.assertTrue(all(scenario.target_y >= 40 for scenario in scenarios))
        self.assertNotEqual(
            seeded_scenarios(config),
            seeded_scenarios(EvaluationConfig(5, 100, 13)),
        )

    def test_expert_completes_finite_evaluation_and_counts_reconcile(self):
        config = EvaluationConfig(episodes=20, max_steps=200, seed=7)
        result = evaluate_policy(heuristic_policy, config, policy_name="expert")

        self.assertEqual(len(result.episodes), 20)
        self.assertEqual(result.metrics.successes, 20)
        self.assertEqual(result.metrics.success_rate, 1.0)
        self.assertIsNotNone(result.metrics.mean_successful_steps)
        self.assertLessEqual(max(e.steps for e in result.episodes), 200)
        self.assertEqual(
            result.metrics.successes
            + result.metrics.stalled
            + result.metrics.out_of_bounds,
            result.metrics.episodes,
        )

    def test_untrained_baseline_stalls_at_exact_step_limit(self):
        config = EvaluationConfig(episodes=4, max_steps=3, seed=2)
        result = evaluate_policy(untrained_policy, config)

        self.assertEqual(result.metrics.successes, 0)
        self.assertEqual(result.metrics.stalled, 4)
        self.assertTrue(all(e.steps == 3 for e in result.episodes))
        self.assertIsNone(result.metrics.mean_successful_steps)

    def test_out_of_bounds_policy_is_reported(self):
        result = evaluate_policy(
            lambda state: Action(1000, 0),
            EvaluationConfig(episodes=3, max_steps=4, seed=8),
        )
        self.assertEqual(result.metrics.out_of_bounds, 3)
        self.assertTrue(all(e.outcome == EpisodeOutcome.OUT_OF_BOUNDS for e in result.episodes))

    def test_save_and_compare_training_and_evaluation_results(self):
        result = evaluate_policy(
            heuristic_policy,
            EvaluationConfig(episodes=2, max_steps=200, seed=1),
            experiment="model_abc.json",
        )
        with tempfile.TemporaryDirectory() as directory:
            evaluation_path = Path(directory) / "evaluation.json"
            training_path = Path(directory) / "training.json"
            save_evaluation(result, evaluation_path)
            training_path.write_text(
                json.dumps(
                    {
                        "dataset_fingerprint": "abc",
                        "config": {"epochs": 10, "learning_rate": 0.01},
                        "metrics": {
                            "best_epoch": 2,
                            "validation_loss": [2.0, 1.0],
                        },
                    }
                ),
                encoding="utf-8",
            )

            saved = json.loads(evaluation_path.read_text(encoding="utf-8"))
            rows = compare_experiments([evaluation_path, training_path])

        self.assertEqual(saved["experiment"], "model_abc.json")
        self.assertEqual(saved["metrics"]["episodes"], 2)
        self.assertEqual(rows[0]["kind"], "evaluation")
        self.assertEqual(rows[0]["success_rate"], 1.0)
        self.assertEqual(rows[1]["best_validation_loss"], 1.0)

    def test_rejects_wrong_number_of_supplied_scenarios(self):
        with self.assertRaisesRegex(ValueError, "Expected 2"):
            evaluate_policy(
                heuristic_policy,
                EvaluationConfig(episodes=2),
                scenarios=seeded_scenarios(EvaluationConfig(episodes=1)),
            )


if __name__ == "__main__":
    unittest.main()
