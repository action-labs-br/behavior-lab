# Repository Guidelines

## Project Structure & Module Organization

This repository contains small machine-learning experiments. The active project is `game/`, a Pygame application that learns to move a blue circle to a target from recorded demonstrations.

- `game/play.py` records keyboard demonstrations as CSV files.
- `game/train.py` trains a PyTorch policy and writes a `.pth` checkpoint.
- `game/execute.py` runs the game with a trained model.
- `game/util/` contains game, display, input, geometry, acceleration, and model components.
- `game/data/` contains demonstration datasets and model artifacts.
- `game/readme.md` documents the workflow and class design.

Keep reusable behavior in `game/util/`; keep entry-point scripts focused on orchestration. Do not commit large generated datasets or checkpoints unless they are intentional project fixtures.

## Build, Test, and Development Commands

Run project commands from `game/` so relative data and model paths resolve correctly.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python play.py
python train.py data/demonstrations_20241218_172133
python execute.py data/demonstrations_20241218_172133
```

`play.py` collects demonstrations, `train.py` produces the matching `.pth` checkpoint, and `execute.py` evaluates that checkpoint interactively.

## Coding Style & Naming Conventions

Use Python with four-space indentation and PEP 8 conventions. Name modules, functions, and variables with `snake_case`; use `PascalCase` for classes such as `ContinuousPolicyNetwork`; reserve `UPPER_CASE` for constants. Add type annotations to new public functions and keep imports grouped as standard library, third-party, then local modules. No formatter or linter is currently configured, so keep changes consistent with nearby code and avoid unrelated reformatting.

## Testing Guidelines

There is currently no automated test suite or coverage threshold. For gameplay changes, manually run `play.py` and verify movement, collision, success, and CSV output. For model changes, train on a small existing dataset and run the resulting checkpoint with `execute.py`. If adding tests, place them under `game/tests/`, name files `test_*.py`, and use `pytest` conventions.

## Commit & Pull Request Guidelines

Recent commits use short, imperative summaries such as `Update readme` and `Fixed initial position`. Keep commits focused and describe the user-visible change in the subject. Pull requests should explain the motivation, list validation commands, link related issues, and call out changed datasets or checkpoints. Include a screenshot or short recording for visible gameplay changes.
