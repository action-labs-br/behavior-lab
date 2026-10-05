import json
import os
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pygame
import pytest
import torch
from util.model import ContinuousPolicyNetwork

from behavior_cloning_game.ui import (
    BLUE,
    ERROR,
    SUCCESS,
    TRAINING_FIELDS,
    WARNING,
    Button,
    TrainingForm,
    _draw_action_distribution,
    _draw_collection_choice,
    _draw_inspection,
    _draw_picker,
    _draw_training_config,
    artifact_creation_label,
    artifact_training_metrics,
    dataset_append_compatibility,
    discover_artifacts,
    inspect_dataset,
    model_compatibility,
    training_metric_colour,
)


def test_discover_datasets_newest_first(tmp_path):
    older = tmp_path / "demonstrations_old.csv"
    newer = tmp_path / "demonstrations_new.csv"
    older.write_text("old", encoding="utf-8")
    newer.write_text("new", encoding="utf-8")
    older.touch()
    newer.touch()
    older_time = older.stat().st_mtime - 10
    older.touch()
    newer.touch()
    os.utime(older, (older_time, older_time))

    assert discover_artifacts(tmp_path, "train") == [newer, older]
    assert discover_artifacts(tmp_path, "inspect") == [newer, older]
    assert discover_artifacts(tmp_path, "collect") == [newer, older]


def test_collection_choice_offers_new_and_append_paths():
    surface = pygame.Surface((920, 640))
    pygame.font.init()

    with patch("behavior_cloning_game.ui.pygame.mouse.get_pos", return_value=(-1, -1)):
        buttons = _draw_collection_choice(surface)

    assert {button.value for button in buttons} == {
        "collect-new",
        "collect-append",
        "back-home",
    }


def test_collection_picker_disables_incompatible_dataset(tmp_path):
    compatible = tmp_path / "current.csv"
    compatible.write_text(
        "schema_version,episode_id,step,elapsed_ms,blue_x,blue_y,target_x,target_y,"
        "action_x,action_y,outcome\n"
        "2,1,0,0,10,20,100,200,5,0,success\n",
        encoding="utf-8",
    )
    legacy = tmp_path / "legacy.csv"
    legacy.write_text(
        "Execution,clock,current_position_x,current_position_y,target_position_x,"
        "target_position_y,move_x,move_y\n"
        "1,0,10,20,100,200,5,0\n",
        encoding="utf-8",
    )
    surface = pygame.Surface((920, 640))
    pygame.font.init()

    with (
        patch("behavior_cloning_game.ui.pygame.mouse.get_pos", return_value=(-1, -1)),
        patch("behavior_cloning_game.ui._text") as draw_text,
    ):
        buttons = _draw_picker(surface, "collect", [compatible, legacy], tmp_path)

    selectable_values = {button.value for button in buttons}
    labels = [call.args[1] for call in draw_text.call_args_list]
    assert dataset_append_compatibility(compatible) == (True, "Compatible")
    assert dataset_append_compatibility(legacy) == (
        False,
        "Legacy dataset cannot be appended",
    )
    assert str(compatible) in selectable_values
    assert str(legacy) not in selectable_values
    assert "✓ Compatible" in labels
    assert "Legacy dataset cannot be appended" in labels


def test_discover_models_ignores_unrelated_json(tmp_path):
    metadata = tmp_path / "model_run.json"
    weights = tmp_path / "legacy.pth"
    unrelated = tmp_path / "evaluation.json"
    for path in (metadata, weights, unrelated):
        path.write_text("content", encoding="utf-8")

    assert set(discover_artifacts(tmp_path, "evaluate")) == {metadata, weights}


def test_discover_models_collapses_metadata_and_weights_pair(tmp_path):
    metadata = tmp_path / "model_paired.json"
    paired_weights = tmp_path / "model_paired.pth"
    legacy_weights = tmp_path / "legacy.pth"
    for path in (metadata, paired_weights, legacy_weights):
        path.write_text("content", encoding="utf-8")

    models = discover_artifacts(tmp_path, "evaluate")

    assert metadata in models
    assert paired_weights not in models
    assert legacy_weights in models
    assert len(models) == 2


def test_transformed_legacy_weights_are_incompatible_without_metadata(tmp_path):
    model = ContinuousPolicyNetwork(input_size=2, hidden_size=8, hidden_layers=2)
    weights = tmp_path / "legacy_relative.pth"
    torch.save(model.state_dict(), weights)

    compatible, reason = model_compatibility(weights)

    assert not compatible
    assert "feature transform" in reason


def test_evaluation_picker_disables_incompatible_models(tmp_path):
    weights = tmp_path / "model_good.pth"
    model = ContinuousPolicyNetwork(input_size=4, hidden_size=8, hidden_layers=2)
    torch.save(model.state_dict(), weights)
    compatible = tmp_path / "model_good.json"
    compatible.write_text(
        json.dumps(
            {
                "model": {"input_size": 4, "hidden_size": 8, "hidden_layers": 2},
                "feature_transform": "absolute",
                "weights_file": weights.name,
            }
        ),
        encoding="utf-8",
    )
    incompatible = tmp_path / "model_broken.json"
    incompatible.write_text("{}", encoding="utf-8")
    surface = pygame.Surface((920, 640))
    pygame.font.init()

    with (
        patch("behavior_cloning_game.ui.pygame.mouse.get_pos", return_value=(-1, -1)),
        patch("behavior_cloning_game.ui._text") as draw_text,
    ):
        buttons = _draw_picker(
            surface, "evaluate", [compatible, incompatible], tmp_path
        )

    selectable_values = {button.value for button in buttons}
    labels = [call.args[1] for call in draw_text.call_args_list]
    assert str(compatible) in selectable_values
    assert str(incompatible) not in selectable_values
    assert "✓ Compatible" in labels
    assert "Unavailable" in labels


def test_model_creation_label_uses_recorded_metadata_timestamp(tmp_path):
    model = tmp_path / "model_run.json"
    created_at = "2026-08-18T14:05:06+00:00"
    model.write_text(json.dumps({"created_at": created_at}), encoding="utf-8")

    expected = datetime.fromisoformat(created_at).astimezone().strftime("%Y-%m-%d %H:%M:%S")

    assert artifact_creation_label(model) == expected


def test_model_training_metrics_reports_best_validation_and_final_training_loss(tmp_path):
    model = tmp_path / "model_run.json"
    model.write_text(
        json.dumps(
            {
                "metrics": {
                    "validation_loss": [0.8, 0.25, 0.4],
                    "train_loss": [0.7, 0.2, 0.1],
                }
            }
        ),
        encoding="utf-8",
    )

    assert artifact_training_metrics(model) == (0.25, 0.1)


def test_legacy_model_has_no_training_metrics(tmp_path):
    model = tmp_path / "legacy.pth"
    model.write_bytes(b"weights")

    assert artifact_training_metrics(model) is None


def test_training_metric_colours_compare_visible_validation_losses():
    losses = [0.1, 0.2, 0.3, 0.4]

    assert training_metric_colour(0.1, losses) == SUCCESS
    assert training_metric_colour(0.2, losses) == SUCCESS
    assert training_metric_colour(0.3, losses) == WARNING
    assert training_metric_colour(0.4, losses) == ERROR
    assert training_metric_colour(0.1, [0.1]) == BLUE


def test_evaluation_picker_displays_model_creation_timestamp(tmp_path):
    model = tmp_path / "model_run.json"
    weights = tmp_path / "model_run.pth"
    network = ContinuousPolicyNetwork(input_size=4, hidden_size=8, hidden_layers=2)
    torch.save(network.state_dict(), weights)
    created_at = "2026-08-18T14:05:06+00:00"
    model.write_text(
        json.dumps(
            {
                "created_at": created_at,
                "model": {"input_size": 4, "hidden_size": 8, "hidden_layers": 2},
                "feature_transform": "absolute",
                "weights_file": weights.name,
                "metrics": {
                    "validation_loss": [0.4, 0.2],
                    "train_loss": [0.5, 0.1],
                },
            }
        ),
        encoding="utf-8",
    )
    expected = datetime.fromisoformat(created_at).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    surface = pygame.Surface((920, 640))
    pygame.font.init()

    with (
        patch("behavior_cloning_game.ui.pygame.mouse.get_pos", return_value=(-1, -1)),
        patch("behavior_cloning_game.ui._text") as draw_text,
    ):
        _draw_picker(surface, "evaluate", [model], tmp_path)

    values = [call.args[1] for call in draw_text.call_args_list]
    assert "model_run" in values
    assert "model_run.json" not in values
    assert f"Created: {expected}" in values
    assert "Val 0.2  •  Train 0.1" in values
    creation_call = next(
        call for call in draw_text.call_args_list if call.args[1] == f"Created: {expected}"
    )
    metrics_call = next(
        call for call in draw_text.call_args_list if call.args[1] == "Val 0.2  •  Train 0.1"
    )
    assert creation_call.args[2][0] < metrics_call.args[2][0]


def test_button_hit_area():
    button = Button(pygame.Rect(10, 20, 100, 40), "Train", "train")
    assert button.contains((20, 30))
    assert not button.contains((5, 5))


def test_inspect_dataset_uses_shared_summary(tmp_path):
    dataset = tmp_path / "demo.csv"
    dataset.write_text(
        "schema_version,episode_id,step,elapsed_ms,blue_x,blue_y,target_x,target_y,"
        "action_x,action_y,outcome\n"
        "2,1,0,0,10,20,100,200,5,0,success\n",
        encoding="utf-8",
    )

    summary = inspect_dataset(dataset, Path("game").resolve())

    assert summary.samples == 1
    assert summary.episodes == 1
    assert summary.outcomes["success"] == 1


def _summary_with_actions(count):
    return SimpleNamespace(
        samples=count,
        episodes=1,
        no_op_ratio=0.0,
        outcomes={"success": 1},
        action_histogram={(float(index), 0.0): index + 1 for index in range(count)},
        warnings=(),
    )


def test_inspection_action_distribution_opens_expanded_view():
    surface = pygame.Surface((920, 640))
    pygame.font.init()

    with patch("behavior_cloning_game.ui._text"):
        buttons = _draw_inspection(
            surface, Path("many-actions.csv"), _summary_with_actions(12)
        )

    assert any(button.value == "expand-actions" for button in buttons)


def test_expanded_action_distribution_makes_every_action_reachable():
    surface = pygame.Surface((920, 640))
    summary = _summary_with_actions(20)

    with patch("behavior_cloning_game.ui._text") as draw_text:
        _, maximum_scroll = _draw_action_distribution(
            surface, Path("many-actions.csv"), summary, 0
        )
        _draw_action_distribution(
            surface, Path("many-actions.csv"), summary, maximum_scroll
        )

    labels = {call.args[1] for call in draw_text.call_args_list}
    assert "(0, 0)" in labels
    assert "(19, 0)" in labels
    assert maximum_scroll > 0


def test_training_form_builds_cli_arguments_for_preprocessing_and_hyperparameters():
    form = TrainingForm.for_preset("quick")
    form.feature_transform = "relative-center"
    form.drop_noop = True
    form.epochs = "12"
    form.learning_rate = "0.002"

    assert form.arguments(Path("demo.csv")) == [
        "demo.csv",
        "--preset",
        "quick",
        "--features",
        "relative-center",
        "--epochs",
        "12",
        "--learning-rate",
        "0.002",
        "--batch-size",
        "32",
        "--hidden-size",
        "32",
        "--hidden-layers",
        "2",
        "--validation-fraction",
        "0.2",
        "--seed",
        "42",
        "--downsample",
        "drop-noop",
    ]


def test_training_form_rejects_invalid_values_before_starting_training():
    form = TrainingForm.for_preset("balanced")
    form.validation_fraction = "1.0"

    with pytest.raises(ValueError, match="Validation fraction"):
        form.arguments(Path("demo.csv"))


def test_training_config_exposes_all_controls():
    surface = pygame.Surface((920, 640))
    pygame.font.init()

    with patch("behavior_cloning_game.ui._text"):
        buttons = _draw_training_config(
            surface,
            Path("demo.csv"),
            TrainingForm.for_preset("balanced"),
            None,
            None,
        )

    values = {button.value for button in buttons}
    assert {"preset:quick", "preset:balanced", "preset:explore"} <= values
    assert {
        "features:absolute",
        "features:relative-center",
        "features:relative-containment",
    } <= values
    assert "toggle-drop-noop" in values
    assert "field:epochs" in values
    assert "field:seed" in values
    assert "start-training" in values


def test_training_config_shows_tooltip_when_hovering_an_option():
    surface = pygame.Surface((920, 640))
    pygame.font.init()

    with (
        patch("behavior_cloning_game.ui.pygame.mouse.get_pos", return_value=(150, 175)),
        patch("behavior_cloning_game.ui._text") as draw_text,
    ):
        _draw_training_config(
            surface,
            Path("demo.csv"),
            TrainingForm.for_preset("balanced"),
            None,
            None,
        )

    values = [call.args[1] for call in draw_text.call_args_list]
    assert "Fast baseline with fewer epochs and a smaller network." in values


def test_training_config_draws_question_help_and_tooltip_for_parameter_value():
    surface = pygame.Surface((920, 640))
    pygame.font.init()

    with (
        patch("behavior_cloning_game.ui.pygame.mouse.get_pos", return_value=(50, 370)),
        patch("behavior_cloning_game.ui._text") as draw_text,
    ):
        _draw_training_config(
            surface,
            Path("demo.csv"),
            TrainingForm.for_preset("balanced"),
            None,
            None,
        )

    values = [call.args[1] for call in draw_text.call_args_list]
    assert values.count("?") == len(TRAINING_FIELDS)
    assert any(value.startswith("Complete passes over") for value in values)


def test_training_config_question_mark_is_a_tooltip_target():
    surface = pygame.Surface((920, 640))
    pygame.font.init()

    with (
        patch("behavior_cloning_game.ui.pygame.mouse.get_pos", return_value=(100, 347)),
        patch("behavior_cloning_game.ui._text") as draw_text,
    ):
        _draw_training_config(
            surface,
            Path("demo.csv"),
            TrainingForm.for_preset("balanced"),
            None,
            None,
        )

    values = [call.args[1] for call in draw_text.call_args_list]
    assert any(value.startswith("Complete passes over") for value in values)
