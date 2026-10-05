"""Small command-line front end for the complete learning loop."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

COMMAND_SCRIPTS = {
    "collect": "play.py",
    "inspect": "inspect_data.py",
    "train": "train.py",
    "evaluate": "execute.py",
}


def project_directory() -> Path:
    """Return the packaged game directory without depending on the shell's cwd."""
    return Path(__file__).resolve().parent.parent / "game"


def run_workflow(command: str, arguments: Sequence[str] = ()) -> int:
    """Run one existing workflow with the active Python interpreter."""
    game_directory = project_directory()
    script = game_directory / COMMAND_SCRIPTS[command]
    if not script.is_file():
        print(f"Could not find the {command} program at {script}.", file=sys.stderr)
        return 2
    forwarded = list(arguments)
    # Existing scripts run from game/ for compatibility. Resolve a learner's
    # input path first so relative paths still mean the shell's current folder.
    if command != "collect" and forwarded and not forwarded[0].startswith("-"):
        forwarded[0] = str(Path(forwarded[0]).resolve())
    completed = subprocess.run(
        [sys.executable, str(script), *forwarded],
        cwd=game_directory,
        check=False,
    )
    return completed.returncode


def _print_menu() -> None:
    print("\nBehavior Cloning Learning Lab")
    print("  1. Collect demonstrations")
    print("  2. Inspect a dataset")
    print("  3. Train a model")
    print("  4. Evaluate a model")
    print("  5. Exit")


def interactive_menu() -> int:
    """Guide a learner through one workflow at a time."""
    commands = {"1": "collect", "2": "inspect", "3": "train", "4": "evaluate"}
    while True:
        _print_menu()
        try:
            choice = input("Choose an option: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            return 0
        if choice == "5":
            return 0
        command = commands.get(choice)
        if command is None:
            print("Please enter a number from 1 to 5.")
            continue
        arguments: list[str] = []
        if command in {"inspect", "train", "evaluate"}:
            artifact = input("Dataset path: " if command != "evaluate" else "Model path: ").strip()
            if not artifact:
                print("A path is required.")
                continue
            arguments.append(artifact)
        if command == "train":
            preset = input("Preset [quick/balanced/explore] (balanced): ").strip().lower()
            if preset:
                if preset not in {"quick", "balanced", "explore"}:
                    print("Choose quick, balanced, or explore.")
                    continue
                arguments.extend(["--preset", preset])
        if command == "evaluate":
            episodes = input("Evaluation episodes (20): ").strip()
            if episodes:
                if not episodes.isdigit() or int(episodes) < 1:
                    print("Episodes must be a positive whole number.")
                    continue
                arguments.extend(["--episodes", episodes])
        status = run_workflow(command, arguments)
        if status:
            print(f"The {command} step exited with status {status}.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="behavior-cloning-game",
        description=(
            "Learn behavior cloning through a simple collect, inspect, train, and "
            "evaluate workflow. Run without a command for the guided menu."
        ),
        epilog=(
            "Examples: behavior-cloning-game collect | behavior-cloning-game inspect "
            "data/demo.csv | behavior-cloning-game train data/demo.csv --epochs 20 | "
            "behavior-cloning-game evaluate data/model.pth --episodes 20"
        ),
    )
    parser.add_argument(
        "--text",
        action="store_true",
        help="use the terminal menu instead of the graphical launcher",
    )
    subparsers = parser.add_subparsers(dest="command")
    descriptions = {
        "collect": "Play with the arrow keys and save demonstrations.",
        "inspect": "Explain the states and actions in a demonstration CSV.",
        "train": "Train a policy using a preset or chosen hyperparameters.",
        "evaluate": "Watch a trained policy attempt the task.",
    }
    for command, description in descriptions.items():
        child = subparsers.add_parser(
            command,
            help=description,
            description=f"{description} Arguments after -- are passed to the underlying command.",
        )
        child.add_argument(
            "arguments",
            nargs=argparse.REMAINDER,
            metavar="ARG",
            help="dataset/model path and workflow options",
        )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command is None:
        if args.text:
            return interactive_menu()
        from .ui import launch

        return launch(run_workflow, project_directory() / "data")
    forwarded = list(args.arguments)
    if "--" in forwarded:
        forwarded.remove("--")
    return run_workflow(args.command, forwarded)
