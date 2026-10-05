"""Watch a model play, with optional finite headless evaluation."""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import torch

from util.domain import EvaluationConfig, GameMode
from util.evaluation import (
    compare_experiments,
    evaluate_policy,
    heuristic_policy,
    save_evaluation,
    torch_policy,
    untrained_policy,
)
from util.model import ContinuousPolicyNetwork
from util.coordinate import Coordinate
from util.game import Game
from util.inputs import FromModel
from util.features import FeatureTransform, get_feature_transform
from util.training import load_artifact


def _legacy_model(path: Path) -> ContinuousPolicyNetwork:
    try:
        state_dict = torch.load(path, map_location="cpu", weights_only=True)
        hidden_layers = 4 if "fc3.weight" in state_dict else 2
        hidden_size = int(state_dict["fc1.weight"].shape[0])
        input_size = int(state_dict["fc1.weight"].shape[1])
        if input_size != 4:
            raise ValueError(
                "this checkpoint uses transformed features that cannot be identified "
                "from weights alone; use its paired .json experiment file"
            )
        model = ContinuousPolicyNetwork(
            input_size=input_size,
            hidden_size=hidden_size,
            hidden_layers=hidden_layers,
            device="cpu",
        )
        model.load_state_dict(state_dict)
    except (OSError, KeyError, RuntimeError, ValueError) as error:
        raise ValueError(f"Could not load model checkpoint {path}: {error}") from error
    model.eval()
    return model


def _resolve_model(
    argument: str,
) -> tuple[ContinuousPolicyNetwork, str | None, FeatureTransform]:
    path = Path(argument)
    if path.suffix == ".json":
        loaded = load_artifact(path)
        return loaded.model, str(path), loaded.feature_transform
    if not path.suffix:
        path = path.with_suffix(".pth")
    return _legacy_model(path), None, get_feature_transform("absolute")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Watch a behavior-cloning model play in the game window. "
            "Use --headless for reproducible metrics without a display."
        )
    )
    parser.add_argument("model", nargs="?", help="experiment .json or legacy .pth path")
    parser.add_argument("--episodes", type=int, default=20)
    parser.add_argument("--max-steps", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--baseline", choices=("expert", "untrained"))
    parser.add_argument(
        "--headless",
        action="store_true",
        help="run reproducible evaluation without opening the game window",
    )
    parser.add_argument("--output", type=Path, help="evaluation JSON destination")
    parser.add_argument(
        "--compare", nargs="+", type=Path, metavar="JSON", help="compare saved results"
    )
    return parser


def _watch_model(
    model: ContinuousPolicyNetwork,
    config: EvaluationConfig,
    name: str,
    feature_transform: FeatureTransform,
) -> None:
    controller = FromModel.from_model(
        model,
        Coordinate(375, 275),
        Coordinate(0, 0),
        feature_transform,
    )
    game = Game(
        input=controller,
        output=io.StringIO(),
        seed=config.seed,
        max_steps=config.max_steps,
        mode=GameMode.EVALUATION,
    )
    try:
        results = game.start(max_episodes=config.episodes)
    finally:
        game.quit()

    completed = [result for result in results if result.outcome.value != "quit"]
    successes = sum(result.outcome.value == "success" for result in completed)
    print(f"Policy: {name}")
    print(f"Visible attempts: {successes}/{len(completed)} succeeded")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.compare:
        print(json.dumps(compare_experiments(args.compare), indent=2))
        return 0
    if not args.model and not args.baseline:
        build_parser().error("provide a model path, --baseline, or --compare")

    config = EvaluationConfig(args.episodes, args.max_steps, args.seed)
    experiment = None
    feature_transform = get_feature_transform("absolute")
    if args.baseline == "expert":
        policy, name = heuristic_policy, "hand-coded expert"
    elif args.baseline == "untrained":
        policy, name = untrained_policy, "untrained (no action)"
    else:
        model, experiment, feature_transform = _resolve_model(args.model)
        policy, name = torch_policy(model, feature_transform), Path(args.model).stem

    headless = args.headless or args.baseline is not None
    if not headless:
        if args.output:
            build_parser().error("saving evaluation JSON requires --headless")
        _watch_model(model, config, name, feature_transform)
        return 0

    result = evaluate_policy(
        policy, config, policy_name=name, experiment=experiment
    )
    metrics = result.metrics
    print(f"Policy: {name}")
    print(
        f"Successes: {metrics.successes}/{metrics.episodes} "
        f"({metrics.success_rate:.1%})"
    )
    print(
        "Successful steps (mean / median): "
        f"{metrics.mean_successful_steps} / {metrics.median_successful_steps}"
    )
    print(f"Failures: {metrics.stalled} stalled, {metrics.out_of_bounds} out of bounds")
    if args.output:
        print(f"Evaluation saved to {save_evaluation(result, args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
