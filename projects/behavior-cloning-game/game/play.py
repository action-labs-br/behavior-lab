import argparse
from datetime import datetime
from pathlib import Path

from util.data import DatasetError, EpisodeRecorder, load_demonstrations
from util.domain import GameMode
from util.game import Game


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect behavior-cloning demonstrations.")
    parser.add_argument("--episodes", type=int, help="Stop after this many episodes.")
    parser.add_argument("--seed", type=int, help="Repeat the same target sequence.")
    destination = parser.add_mutually_exclusive_group()
    destination.add_argument("--output", type=Path, help="Destination for a new CSV file.")
    destination.add_argument(
        "--dataset",
        type=Path,
        help="Existing schema-v2 CSV to append new episodes to.",
    )
    return parser


def _prepare_collection(args) -> tuple[Path, int, EpisodeRecorder]:
    if args.dataset is not None:
        rows, legacy = load_demonstrations(args.dataset)
        if legacy:
            raise DatasetError(
                "Cannot append to a legacy dataset because its columns do not include "
                "schema version and outcome. Start a new dataset or migrate it first."
            )
        episode_ids = {row.episode_id for row in rows}
        last_episode_id = max(episode_ids, default=0)
        recorder = EpisodeRecorder(
            args.dataset,
            completed_episodes=len(episode_ids),
            written_samples=len(rows),
        )
        return args.dataset, last_episode_id, recorder

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = args.output or Path(__file__).parent / "data" / f"demonstrations_{timestamp}.csv"
    if destination.exists():
        raise DatasetError(
            f"Output already exists: {destination}. Use --dataset to append safely."
        )
    return destination, 0, EpisodeRecorder(destination)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        destination, last_episode_id, recorder = _prepare_collection(args)
    except DatasetError as error:
        print(f"Collection could not start: {error}")
        return 1

    if last_episode_id:
        print(
            f"Appending to {destination.resolve()}; "
            f"the next episode is {last_episode_id + 1}."
        )
    game = Game(seed=args.seed, recorder=recorder, mode=GameMode.COLLECTION)
    try:
        results = game.start(
            execution_id=last_episode_id,
            max_episodes=args.episodes,
        )
    finally:
        game.quit()

    completed = sum(result.outcome.value != "quit" for result in results)
    print(f"Saved {completed} completed episode(s) to {destination.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
