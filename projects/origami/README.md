# Origami Behaviour Cloning

A small FastAPI app for collecting photos **before** paper-airplane folds, training a frozen-ResNet18 + logistic-regression policy, and showing predictions during a presentation.

## Run locally

Run all commands from `projects/origami/`. Python 3.11+ is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
export TORCH_HOME="$PWD/.local/torch"
PYTHONPATH=. python scripts/verify_encoder.py
uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8080
```

Open <http://127.0.0.1:8080>. Local defaults: event code `ORIGAMI42`; presenter password `local-admin` at `/admin`. These are development defaults. Production rejects them. Local metadata is SQLite and images/models are files under `.local/`; a restart preserves both. No AWS credentials are needed locally.

Common commands are available through `make`: `make venv` creates and installs the local environment, `source .venv/bin/activate` loads it into your shell, `make run` starts the local server, `make test` runs tests and checks the frontend JavaScript, and `make deploy` tests, builds, updates, and verifies an already provisioned ECS Express Mode deployment. Deployment requires the AWS CLI, Docker Buildx, valid AWS credentials, and deployment state under `.deploy/`.

The encoder smoke command downloads ImageNet weights on its first run. The Docker build performs that download ahead of deployment. Keep `TORCH_HOME` the same for the smoke command and server. CPU-only inference is used.

## Language

Use the **Language / Idioma** selector in the header to choose English or Português (Brasil). The choice is remembered in the browser and defaults to Portuguese for Portuguese-language browsers. Participant instructions, presenter controls, and model action labels follow the selected language. Switching languages preserves the current step and selected photo. Translations are in `app/static/i18n.js`; stored action IDs stay the same in both languages.

## Presentation workflow

1. Use rectangular paper. Capture the current paper state, confirm upload, then perform the revealed action. Finish each action before advancing. A browser refresh preserves the current run; click **Start or resume**.
2. Collect at least two training examples **per action**, plus a separate participant for held-out evaluation. Six participants doing one complete run produce 48 photos; holding one out leaves five training examples per action. This is a tiny educational dataset, not an accuracy guarantee.
3. Open `/admin`. Review the gallery, exclude bad samples, choose a held-out participant, and click **Train model**. With only one participant, evaluation is explicitly marked training-only. Training currently requires every configured action to meet the minimum; partial runs are eligible only insofar as the combined dataset covers all actions.
4. Inspect the metrics and try a new image. Probabilities are uncalibrated classifier scores, not assurances of correctness. The model has no `done` or `unknown` action.
5. Before the talk, rehearse with real photos, verify a model, then **Mark as fallback**. The presenter can explicitly **Activate** it later. No real dataset or pretrained origami classifier is included in this repository.
6. After the talk, delete the dataset manually in the admin panel. Models remain available. The cloud teardown guide also removes models and infrastructure.

The eight-step airplane sequence in `config/experiment.yaml` is an initial candidate. Rehearse its instructions and camera orientation, particularly the last two wing steps, against the 5–10 minute budget. Dog-face instructions can be added later as a separate experiment. Use a new experiment ID when changing a sequence; config fingerprints reject mixing incompatible runs or models.

## AWS commands

Separate Markdown runbooks contain the commands to provision resources:

1. [Storage, DynamoDB, and ECR](docs/aws/01-foundation.md)
2. [IAM roles and Secrets Manager](docs/aws/02-roles-and-secrets.md)
3. [ECS Express Mode deployment](docs/aws/03-ecs-deployment.md)
4. [App Runner alternative for existing customers](docs/aws/04-apprunner-existing-customers.md)
5. [Manual cleanup and teardown](docs/aws/05-cleanup.md)
6. [Private environment records](docs/aws/06-deployed-environment.md)
7. [Redeployment and rollback](docs/aws/07-redeployment.md)

The resumable foundation script is `python3 scripts/provision_aws.py --profile your-demo-profile --region us-east-1`. It provisions the storage, registry, secrets, roles, and cluster; deployment details go into `.deploy/deployment.json` and generated app credentials into the private `.deploy/access.json`. The AWS CLI profile is used only for provisioning, while the running application uses its ECS task role.

Nothing is deployed automatically by starting the local app. AWS documents App Runner's closure to new customers; ECS Express Mode is the documented alternative. Both use the same container, private S3 objects, and DynamoDB metadata.

AWS configuration: `APP_ENV=production`, `STORAGE_BACKEND=aws`, `AWS_REGION`, `S3_BUCKET`, `DYNAMODB_TABLE`, `SESSION_SECRET`, `EVENT_CODE`, `ADMIN_PASSWORD`. Optional local overrides: `DATA_DIR`, `EXPERIMENT_CONFIG`, `TORCH_HOME`. Secrets are injected from Secrets Manager, not committed. The app implements same-origin mutation protection via a required request header, signed HttpOnly session cookies, separate admin authorization, and production Secure cookies.

Uploads use size-constrained presigned **POST**, an intentional adjustment from the spec's PUT example. S3 receives the original; completion decodes, checks format/pixels, applies EXIF orientation, strips metadata, and writes a normalized immutable image before marking the sample ready. Original uploads expire after five minutes but the object itself persists until completion/cleanup. Repeating cleanup after grants expire removes late writes.

## Implementation boundaries

- Training runs in a background thread in the web process with a persistent 15-minute operation lease. The lease prevents concurrent training/activation/cleanup across workers. An interrupted job can be retried after expiry; it does not resume automatically. The last good model remains active. Avoid redeploying during training.
- Active model and fallback pointers live in persistent metadata. Workers reload their cached classifier when the active version changes. Joblib artifacts are loaded only from the application's own private store, never from user uploads.
- Manual dataset cleanup retains model artifacts and their metrics/participant IDs. Full infrastructure teardown removes everything. Current application supports one configured experiment per deployment.
- Only JPEG/PNG, up to 10 MiB and 25 megapixels, are accepted. HEIC needs conversion. Mobile camera permission/format behavior and real folding still require device rehearsal.
- No admission cap is imposed. The cloud recipe starts with one task and 4 GiB; concurrency and latency at 20 participants must be measured during rehearsal.
- There is no login rate limiter yet. Keep event/admin credentials private; consider an edge rate limit if the demo is broadly advertised.

## Validation

```bash
python -m pytest -q
node --check app/static/app.js
PYTHONPATH=. python scripts/verify_encoder.py
```

API tests use deterministic fake embeddings to verify labels, access boundaries, retries, holdout isolation, persistence, fallback, cleanup, and failure recovery. AWS adapters are tested using Moto. The separate encoder smoke check runs the actual pretrained model. Neither proves recognition quality on real airplanes.

Manual rehearsal: iPhone Safari and Android Chrome capture; desktop uploads; upload interruption/retry; two browser sessions; 20 simultaneous participants; held-out inference; model recovery after service restart. Provisioning commands must also be validated in the target AWS account.
