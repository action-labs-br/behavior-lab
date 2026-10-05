# ML Sandbox

This repository contains two independent machine-learning projects. They have separate
dependencies, frontends, runtime workflows, tests, and deployment instructions.

| Project | Description | Start here |
| --- | --- | --- |
| [Behavior Cloning Game](projects/behavior-cloning-game/README.md) | A Pygame game and browser learning lab that learn from demonstrations. | [Quick start](projects/behavior-cloning-game/docs/quickstart.md) |
| [Origami](projects/origami/README.md) | A web app that collects paper-folding examples and predicts the next fold. | [Origami README](projects/origami/README.md) |

## Repository layout

```text
projects/behavior-cloning-game/  Pygame app, browser app, API, and AWS infrastructure
projects/origami/                Origami web app, model workflow, and deployment guides
.github/                         Repository CI workflows
```

Each project README explains its environment and commands. Run project commands from
that project's directory. Generated environments, local data, and build output stay
within their project and are ignored by Git.
