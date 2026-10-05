"""Compatibility command for training a behavior-cloning policy."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from util.data import DatasetError, load_demonstrations
from util.downsampling import available_downsamplers, load_downsampler
from util.features import FEATURE_TRANSFORMS
from util.training import TRAINING_PRESETS, save_artifact, train_policy, training_preset


def _dataset_path(value: str) -> Path:
    path = Path(value)
    return path if path.suffix == ".csv" else path.with_suffix(".csv")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Train a behavior-cloning model from recorded demonstrations."
    )
    parser.add_argument(
        "dataset",
        nargs="?",
        help="demonstration CSV path (the .csv suffix is optional)",
    )
    parser.add_argument(
        "--preset", choices=tuple(TRAINING_PRESETS), default="balanced",
        help="beginner-friendly starting configuration (default: balanced)",
    )
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--learning-rate", type=float)
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--hidden-size", type=int)
    parser.add_argument("--hidden-layers", type=int, choices=(2, 4))
    parser.add_argument("--validation-fraction", type=float)
    parser.add_argument("--seed", type=int)
    parser.add_argument(
        "--features",
        dest="feature_transform",
        choices=tuple(FEATURE_TRANSFORMS),
        help="state representation used by the model",
    )
    parser.add_argument("--output-dir", type=Path, help="artifact directory (default: dataset folder)")
    parser.add_argument(
        "--downsample",
        metavar="NAME",
        help="workspace plugin name, for example: drop-noop",
    )
    parser.add_argument(
        "--list-downsamplers",
        action="store_true",
        help="list available workspace downsampling plugins and exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list_downsamplers:
        choices = available_downsamplers()
        print("Available downsamplers:")
        for name in choices:
            print(f"  {name}")
        return 0
    if args.dataset is None:
        build_parser().error("dataset is required unless --list-downsamplers is used")
    overrides = {
        name: getattr(args, name)
        for name in (
            "epochs", "learning_rate", "batch_size", "hidden_size",
            "hidden_layers", "validation_fraction", "seed",
            "feature_transform",
        )
        if getattr(args, name) is not None
    }
    config = replace(training_preset(args.preset), **overrides)
    dataset_path = _dataset_path(args.dataset)
    try:
        downsampler = load_downsampler(args.downsample) if args.downsample else None
        rows, legacy = load_demonstrations(dataset_path)
        print(
            f"Training with {args.preset} preset: {config.epochs} epochs, "
            f"learning rate {config.learning_rate}, batch size {config.batch_size}."
        )
        result = train_policy(
            rows,
            config,
            progress=lambda epoch, train_loss, validation_loss: print(
                f"Epoch {epoch}/{config.epochs} - "
                f"train loss: {train_loss:.6f}, validation loss: {validation_loss:.6f}"
            ),
            downsampler=downsampler,
        )
        weights, metadata = save_artifact(result, args.output_dir or dataset_path.parent)
    except (DatasetError, ValueError, FileExistsError) as error:
        print(f"Training could not start: {error}")
        return 1
    if legacy:
        print("Loaded a legacy dataset; episode outcomes are recorded as unknown.")
    if result.downsampling is not None:
        print(f"Downsampling: {result.downsampling['description']}")
        print(
            "Training rows: "
            f"{result.downsampling['training_rows_before']} before, "
            f"{result.downsampling['training_rows_after']} after; "
            f"validation rows unchanged: {result.downsampling['validation_rows']}"
        )
        removed_episodes = result.downsampling["removed_training_episode_ids"]
        if removed_episodes:
            print(
                "Training episodes removed because no samples remained: "
                + ", ".join(str(value) for value in removed_episodes)
            )
    print(f"Best validation loss: {min(result.validation_loss):.6f} (epoch {result.best_epoch})")
    print(f"Weights saved to {weights}")
    print(f"Experiment details saved to {metadata}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
