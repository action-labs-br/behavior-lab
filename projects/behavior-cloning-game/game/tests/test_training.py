import json
from dataclasses import replace
import tempfile
import unittest
from pathlib import Path

import torch

from util.data import Demonstration
from util.domain import Action, GameState, TrainingConfig
from util.downsampling import load_downsampler
from util.training import (
    fit_normalization,
    load_artifact,
    save_artifact,
    split_episode_ids,
    train_policy,
    training_preset,
)


def tiny_dataset() -> list[Demonstration]:
    rows = []
    for episode_id in range(1, 6):
        for step in range(4):
            blue_x = episode_id * 10 + step
            blue_y = episode_id * 5 - step
            target_x = 100 + episode_id
            target_y = 80 - episode_id
            rows.append(
                Demonstration(
                    episode_id=episode_id,
                    step=step,
                    elapsed_ms=step * 16,
                    state=GameState(blue_x, blue_y, target_x, target_y),
                    action=Action((target_x - blue_x) / 20, (target_y - blue_y) / 20),
                )
            )
    return rows


class TrainingTests(unittest.TestCase):
    def setUp(self):
        self.rows = tiny_dataset()
        self.config = TrainingConfig(
            epochs=3,
            learning_rate=0.01,
            batch_size=4,
            hidden_size=8,
            hidden_layers=2,
            validation_fraction=0.4,
            seed=7,
        )

    def test_split_is_seeded_disjoint_and_by_episode(self):
        first = split_episode_ids(self.rows, 0.4, 7)
        second = split_episode_ids(self.rows, 0.4, 7)
        self.assertEqual(first, second)
        train_ids, validation_ids = first
        self.assertFalse(set(train_ids) & set(validation_ids))
        self.assertEqual(set(train_ids) | set(validation_ids), {1, 2, 3, 4, 5})

    def test_beginner_presets_are_valid_and_distinct(self):
        quick = training_preset("quick")
        balanced = training_preset("balanced")
        explore = training_preset("explore")
        for config in (quick, balanced, explore):
            config.validate()
        self.assertLess(quick.epochs, balanced.epochs)
        self.assertLess(balanced.hidden_size, explore.hidden_size)

    def test_normalization_is_fit_on_training_episodes_only(self):
        train_ids, _ = split_episode_ids(self.rows, 0.4, 7)
        train_rows = [row for row in self.rows if row.episode_id in train_ids]
        expected = fit_normalization(train_rows)
        result = train_policy(self.rows, self.config)
        self.assertEqual(result.normalization, expected)

    def test_training_is_reproducible(self):
        first = train_policy(self.rows, self.config)
        second = train_policy(self.rows, self.config)
        self.assertEqual(first.train_episode_ids, second.train_episode_ids)
        self.assertEqual(first.validation_episode_ids, second.validation_episode_ids)
        self.assertEqual(first.train_loss, second.train_loss)
        self.assertEqual(first.validation_loss, second.validation_loss)
        for name, value in first.model.state_dict().items():
            self.assertTrue(torch.equal(value, second.model.state_dict()[name]))

    def test_training_reports_each_epoch(self):
        updates = []
        train_policy(
            self.rows,
            self.config,
            progress=lambda epoch, train_loss, validation_loss: updates.append(
                (epoch, train_loss, validation_loss)
            ),
        )
        self.assertEqual([update[0] for update in updates], [1, 2, 3])
        self.assertTrue(all(update[1] >= 0 and update[2] >= 0 for update in updates))

    def test_downsampling_applies_only_to_training_partition(self):
        rows = []
        for episode_id in range(1, 6):
            rows.extend(
                [
                    Demonstration(
                        episode_id,
                        0,
                        0,
                        GameState(100, 100, 200, 200),
                        Action(0, 0),
                    ),
                    Demonstration(
                        episode_id,
                        1,
                        16,
                        GameState(100, 100, 200, 200),
                        Action(5, 0),
                    ),
                ]
            )

        result = train_policy(
            rows,
            self.config,
            downsampler=load_downsampler("drop-noop"),
        )

        self.assertEqual(result.downsampling["training_rows_before"], 6)
        self.assertEqual(result.downsampling["training_rows_after"], 3)
        self.assertEqual(result.downsampling["validation_rows"], 4)
        self.assertEqual(result.downsampling["name"], "drop-noop")
        self.assertEqual(result.downsampling["removed_training_episode_ids"], [])
        with tempfile.TemporaryDirectory() as directory:
            _, metadata_path = save_artifact(result, directory)
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.assertEqual(metadata["downsampling"]["name"], "drop-noop")
        self.assertEqual(len(metadata["downsampling"]["source_hash"]), 64)

    def test_downsampling_produces_a_distinct_experiment_id(self):
        rows = []
        for episode_id in range(1, 6):
            rows.extend(
                [
                    Demonstration(
                        episode_id,
                        0,
                        0,
                        GameState(100, 100, 200, 200),
                        Action(0, 0),
                    ),
                    Demonstration(
                        episode_id,
                        1,
                        16,
                        GameState(100, 100, 200, 200),
                        Action(5, 0),
                    ),
                ]
            )
        plain = train_policy(rows, self.config)
        filtered = train_policy(
            rows,
            self.config,
            downsampler=load_downsampler("drop-noop"),
        )

        with tempfile.TemporaryDirectory() as directory:
            plain_weights, _ = save_artifact(plain, directory)
            filtered_weights, _ = save_artifact(filtered, directory)

        self.assertNotEqual(plain_weights.name, filtered_weights.name)

    def test_artifact_round_trip_is_cpu_portable_and_self_describing(self):
        result = train_policy(self.rows, self.config)
        sample = torch.tensor([self.rows[0].state.features()], dtype=torch.float32)
        expected = result.model(sample)
        with tempfile.TemporaryDirectory() as directory:
            weights, metadata_path = save_artifact(result, directory)
            loaded = load_artifact(metadata_path)
            actual = loaded.model(sample)
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

            self.assertTrue(weights.exists())
            self.assertEqual(metadata["dataset_fingerprint"], result.dataset_fingerprint)
            self.assertEqual(metadata["split"]["train_episode_ids"], list(result.train_episode_ids))
            self.assertTrue(metadata["normalization"]["baked_into_first_layer"])
            self.assertEqual(next(loaded.model.parameters()).device.type, "cpu")
            self.assertTrue(torch.equal(expected, actual))

    def test_relative_feature_artifact_restores_inference_transform(self):
        config = replace(self.config, feature_transform="relative-center")
        result = train_policy(self.rows, config)
        with tempfile.TemporaryDirectory() as directory:
            _, metadata_path = save_artifact(result, directory)
            loaded = load_artifact(metadata_path)

        self.assertEqual(result.model.fc1.in_features, 2)
        self.assertEqual(loaded.model.fc1.in_features, 2)
        self.assertEqual(loaded.feature_transform.name, "relative-center")
        self.assertEqual(
            loaded.metadata["features"],
            ["relative_center_x", "relative_center_y"],
        )

    def test_artifact_refuses_to_overwrite_same_experiment(self):
        result = train_policy(self.rows, self.config)
        with tempfile.TemporaryDirectory() as directory:
            save_artifact(result, directory)
            with self.assertRaisesRegex(FileExistsError, "already exists"):
                save_artifact(result, directory)

    def test_one_episode_gives_beginner_friendly_error(self):
        one_episode = [row for row in self.rows if row.episode_id == 1]
        with self.assertRaisesRegex(ValueError, "at least two episodes"):
            train_policy(one_episode, self.config)


if __name__ == "__main__":
    unittest.main()
