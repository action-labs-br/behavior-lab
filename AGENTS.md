# Repository Guidelines

## Project Structure & Module Organization

This repository contains two independent machine-learning projects:

- The Behavior Cloning Game spans the root Python package, `game/`, browser app in `web/`, deployment infrastructure in `infra/cdk/`, and guides in `docs/`.
- Origami is the web application in `origami/`, with its own frontend, Python environment, model workflow, tests, and deployment guides.

Keep each project's dependencies and generated local data separate. Run commands from the project or subproject directory specified by its README.

- `game/play.py` records keyboard demonstrations as CSV files.
- `game/train.py` trains a PyTorch policy and writes a `.pth` checkpoint.
- `game/execute.py` runs the game with a trained model.
- `game/util/` contains game, display, input, geometry, acceleration, and model components.
- `game/data/` contains Behavior Cloning Game demonstration datasets and model artifacts.
- `game/readme.md` documents the game workflow; root `README.md` is the repository index.
- `web/` and `infra/cdk/` contain the Behavior Cloning Game browser learning lab and its AWS infrastructure.
- `origami/README.md` documents the Origami app, while `origami/docs/aws/` contains its deployment runbooks.

Keep reusable game behavior in `game/util/`; keep entry-point scripts focused on orchestration. Do not commit local environments, generated CDK output, or large datasets and checkpoints unless they are intentional project fixtures.

## Build, Test, and Development Commands

For the Behavior Cloning Game, install from the repository root and launch the guided workflow:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m behavior_cloning_game
```

Run `play.py`, `train.py`, and `execute.py` from `game/` for the script-based workflow. For Origami, see `origami/README.md`; its `make venv`, `make test`, and `make run` commands must run from `origami/`.

## Coding Style & Naming Conventions

Use Python with four-space indentation and PEP 8 conventions. Name modules, functions, and variables with `snake_case`; use `PascalCase` for classes such as `ContinuousPolicyNetwork`; reserve `UPPER_CASE` for constants. Add type annotations to new public functions and keep imports grouped as standard library, third-party, then local modules. No formatter or linter is currently configured, so keep changes consistent with nearby code and avoid unrelated reformatting.

## Testing Guidelines

Behavior Cloning Game tests live in `game/tests/` and `tests/`; Origami tests live in `origami/tests/`. For gameplay changes, manually run `play.py` and verify movement, collision, success, and CSV output. For frontend changes, use the relevant project's documented build or syntax check. Do not add or run tests unless the task asks for verification.

## Commit & Pull Request Guidelines

Recent commits use short, imperative summaries such as `Update readme` and `Fixed initial position`. Keep commits focused and describe the user-visible change in the subject. Pull requests should explain the motivation, list validation commands, link related issues, and call out changed datasets or checkpoints. Include a screenshot or short recording for visible gameplay changes.
