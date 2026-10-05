"""Inspect a demonstration CSV before using it to train a policy."""

import argparse
from pathlib import Path

from util.data import DatasetError, load_demonstrations
from util.inspection import format_summary, summarize_demonstrations


def dataset_path(value: str) -> Path:
    path = Path(value)
    if path.suffix:
        return path
    csv_path = path.with_suffix(".csv")
    return csv_path if csv_path.exists() else path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Explain what a behavior-cloning demonstration dataset contains."
    )
    parser.add_argument("dataset", help="path to a demonstration CSV (the .csv is optional)")
    args = parser.parse_args(argv)

    path = dataset_path(args.dataset)
    try:
        rows, legacy = load_demonstrations(path)
    except DatasetError as error:
        parser.exit(2, f"Could not inspect the dataset: {error}\n")

    print(f"File: {path.resolve()}")
    print(format_summary(summarize_demonstrations(rows, legacy=legacy)))
    if legacy:
        print(
            "\nLegacy notice: this file remains usable, but collect new data to record "
            "success and failure outcomes."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
