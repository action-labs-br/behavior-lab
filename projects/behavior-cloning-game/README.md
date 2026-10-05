# Behavior Cloning Game

Record a person moving a blue circle into a target, train a PyTorch policy on those
demonstrations, and evaluate how well the policy imitates them. This project includes
the Pygame desktop app, a browser learning lab, a local API, and AWS infrastructure.
Run the commands in this guide from `projects/behavior-cloning-game/` unless stated
otherwise.

## Quick start

The project supports Python 3.11 through 3.13. From this directory:

```bash
python3 -m venv .venv
source .venv/bin/activate          # macOS/Linux
# .venv\Scripts\Activate.ps1      # Windows PowerShell
python -m pip install -e .
python -m behavior_cloning_game
```

The final command opens a graphical launcher for the full learning loop:

```text
Collect demonstrations -> Inspect the data -> Train a policy -> Evaluate it
```

Dataset inspection is displayed in the launcher with sample and episode counts,
outcomes, action balance, no-op ratio, and data-quality guidance.
Before training, the launcher lets you choose preprocessing, feature representation,
presets, and individual hyperparameters.

Start with the [five-minute quick start](docs/quickstart.md) for a guided first run.
Use `python -m behavior_cloning_game --text` when you prefer the terminal menu or
are working without a graphical display.

## Command-line workflow

The same steps can be run directly from this directory:

```bash
python -m behavior_cloning_game collect -- --episodes 10 --seed 7
python -m behavior_cloning_game inspect game/data/demonstrations_TIMESTAMP.csv
python -m behavior_cloning_game train game/data/demonstrations_TIMESTAMP.csv -- --preset quick
python -m behavior_cloning_game evaluate game/data/model_RUN_ID.json -- --episodes 20
```

Use `--headless` during evaluation to collect reproducible metrics without opening a
window:

```bash
python -m behavior_cloning_game evaluate game/data/model_RUN_ID.json -- --headless
```

Options placed after `--` are forwarded to the underlying workflow. Run the scripts
in `game/` directly when you want to explore each implementation step or see all of
its options:

```bash
cd game
python play.py --help
python inspect_data.py --help
python train.py --help
python execute.py --help
```

## Outputs

Generated artifacts are stored in `game/data/` by default:

- `demonstrations_*.csv` contains recorded states, actions, and episode outcomes.
- `model_*.pth` contains trained PyTorch weights.
- `model_*.json` describes the matching feature transform, normalization, training
  configuration, data split, and metrics.

Prefer the JSON experiment file when evaluating a newly trained model. It supplies
the metadata needed to reproduce inference, especially for relative feature
transforms. Generated datasets and checkpoints should not be committed unless they
are intentional fixtures. The small, tracked sample files used by tests live in
`game/data/fixtures/`; new run artifacts stay directly under `game/data/` and are
ignored by Git.

## Project map

- `behavior_cloning_game/` provides the guided menu and packaged command-line entry
  point.
- `game/` contains the collection, inspection, training, and evaluation scripts.
- `web/` contains the browser learning lab and its local-first API.
- `game/util/` contains reusable game, data, feature, model, and evaluation logic.
- `game/tests/` and `tests/` contain the automated test suites.
- `docs/` contains the [guided lessons](docs/lessons.md),
  [instructor guide](docs/instructor-guide.md), and extension documentation.

See the [game workflow guide](game/readme.md) for data semantics, training controls,
feature transforms, and downsampling plugins.

## Web learning lab

The browser learning lab records demonstrations and saves schema-v2 CSV datasets
through a local API. Start the API in one
terminal and the frontend in another:

```bash
python -m pip install -e . -r web/api/requirements.txt
python -m uvicorn web.api.app:app --reload
```

```bash
cd web
npm install
npm run dev
```

Open <http://127.0.0.1:5173>. Local project metadata and CSV files are stored under
`.local-data/`, which is ignored by Git. The API storage interface is intentionally
small so this local filesystem adapter can be replaced by S3 for deployment. See
the [web platform specification](docs/web-platform-spec.md) for the product scope
and deployment design.

Training jobs run asynchronously in one local worker thread and expose epoch
progress in the project page. Completed policies can now run a seeded evaluation;
the page reports success and failure metrics and replays saved episode trajectories.
Evaluation is synchronous for this small local MVP. This worker and filesystem
storage are for local development. The AWS pilot uses a private S3 bucket for
metadata, datasets, and model artifacts; an SQS queue invokes a CPU Lambda worker
for training; and CloudFront serves the static application and forwards API calls
to a Lambda-backed HTTP API. Cognito sign-in is required for application API routes,
and public registration is disabled; an administrator must create each allowed
user. See the [web platform specification](docs/web-platform-spec.md) for its
limits and deployment details.

To prepare the frontend and review the infrastructure template, install the CDK
dependencies and run synthesis:

```bash
npm --prefix infra/cdk ci
npm --prefix web ci
npm --prefix web run build
npm --prefix infra/cdk run synth
```

Deployment also requires AWS credentials, a bootstrapped CDK environment, and a
running Docker daemon because the API and training worker use a container image.
After deployment, create an invited user in the Cognito console using the
`CognitoUserPoolId` output; self-service registration is disabled.

Pause the pilot with `npm --prefix infra/cdk run pause`, and resume it with
`npm --prefix infra/cdk run resume`. Pausing removes application API routes and the
SQS worker trigger while preserving project data and Cognito users. A training
invocation already in progress may finish; queued runs wait for resume. CloudFront,
Cognito, API bootstrap, SQS, and S3 remain provisioned, so pause prevents training
compute but does not eliminate all AWS charges.

## Development

Install the development tools and run the tests from this directory:

```bash
python -m pip install -e '.[dev]'
python -m pytest
```

Keep reusable behavior in `game/util/` and entry-point scripts focused on
orchestration. Potential future teaching extensions include a graphical menu,
corrective-demonstration tooling, experiment charts, and an optional classification
policy; these are ideas rather than a committed implementation schedule.
