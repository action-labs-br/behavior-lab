# Behavior Cloning Game Guidelines

Run commands from `projects/behavior-cloning-game/` unless the command explicitly
changes into a subdirectory.

- `behavior_cloning_game/` contains the guided launcher and CLI.
- `game/` contains the Pygame implementation, training scripts, shared game logic, and datasets.
- `web/` contains the browser learning lab and its local API.
- `infra/cdk/` contains AWS infrastructure for the browser learning lab.
- `docs/` contains learner, instructor, and web platform documentation.

Keep reusable game behavior in `game/util/` and entry-point scripts focused on
orchestration. `game/data/` is the default artifact location; commit datasets or
checkpoints only when they are intentional fixtures.

Install the desktop project with `python -m pip install -e .`. Run the Pygame scripts
from `game/` when using their script-based workflow. The project's `pyproject.toml`
configures tests in `game/tests/` and `tests/`.
