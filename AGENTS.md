# Repository Guidelines

## Projects

This repository contains two independent applications under `projects/`:

- `projects/behavior-cloning-game/` contains the Behavior Cloning Game, its Pygame desktop app, browser learning lab, API, documentation, and CDK deployment.
- `projects/origami/` contains the Origami web app, model workflow, tests, and deployment guides.

Each project owns its dependencies, environment, local data, tests, and README. Run commands from that project's directory. Keep generated environments, local data, and build output out of Git; retain data files only when they are intentional fixtures.

## Style and tests

Use Python with four-space indentation and PEP 8 naming. Add type annotations to new public functions and group imports as standard library, third-party, then local modules. Follow the language and conventions used by the project being changed.

Behavior Cloning Game tests are in `projects/behavior-cloning-game/game/tests/` and `projects/behavior-cloning-game/tests/`. Origami tests are in `projects/origami/tests/`. Follow each project's README and local guidance for validation commands.

## Git changes

Keep changes focused and use short, imperative commit subjects. Pull requests should explain the motivation, list validation commands, link related issues, and call out changed datasets or checkpoints. Include a screenshot or short recording for visible frontend changes.
