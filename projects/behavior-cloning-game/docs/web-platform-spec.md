# Behavior Cloning Game Web Platform — Product Specification

**Status:** Local end-to-end MVP complete; AWS pilot infrastructure and S3/SQS adapters implemented  
**Version:** 1.0  
**Date:** 2026-10-04

## 1. Product summary

Turn the current behavior-cloning game into a browser-based learning lab. A learner
plays a simple target game, records demonstrations, trains a small PyTorch policy,
and watches the policy attempt the task. The platform should make the existing
record → inspect → train → evaluate loop accessible without installing Python or
running a desktop game.

The first release is a private pilot for one learner or a small invited group.
Cognito handles sign-in, public account creation is disabled, and application API
routes require a valid JWT. Data and model artifacts are stored durably in S3.

## 2. Product goals and success measures

### Goals

- Let a learner complete the full behavior-cloning workflow in a modern browser.
- Keep recorded demonstrations compatible with the existing schema-v2 CSV format.
- Reuse the existing training presets, feature transforms, validation split, and
  self-describing experiment artifacts where practical.
- Make training asynchronous, visible, and recoverable if a worker or API restarts.
- Present evaluation as a visual game replay alongside meaningful metrics.

### MVP success measures

- A new learner can record at least two complete episodes, train a model, and view
  an evaluation without a local install.
- A dataset can be downloaded as schema-v2 CSV and a completed run exposes its
  configuration, validation losses, and metrics.
- Refreshing the page or restarting the API does not lose saved projects, datasets,
  completed training runs, or model artifacts.
- Evaluation runs with a fixed seed produce repeatable metrics and trajectories.

## 3. Users and assumptions

**Primary user:** a learner exploring how supervised behavior cloning works.

**Secondary user:** a teacher or presenter demonstrating collection, training, and
evaluation to a small group.

**MVP assumptions:**

- One trusted deployment with administrator-created Cognito accounts. Public
  sign-up, multi-tenancy, and project sharing are out of scope.
- A project is a named workspace containing datasets, training runs, and evaluations.
- The game keeps its current basic task: move the blue circle into a target without
  crossing the play-area boundary. Browser gameplay may use a matching Canvas
  implementation; desktop Pygame is not run in the browser or on the server.
- CPU training is sufficient for the current small models and datasets.
- The initial deployment targets AWS. Cloud resources are defined in `infra/cdk/`;
  deployment remains an operator action after reviewing the synthesized template.

## 4. Scope

### In scope for MVP

- Responsive web application with project list and project workspace.
- Cognito hosted sign-in with administrator-created users; require JWTs on all
  project, dataset, training, evaluation, and download API routes.
- Canvas game with keyboard controls, episode status, pause/restart, and collection.
- Recording and saving demonstrations in schema-v2 format.
- Dataset summary and validation before training.
- Training preset selection (`quick`, `balanced`, `explore`) and a small set of
  supported overrides, starting with feature transform and seed.
- Asynchronous training, progress display, cancellation where safe, and clear
  terminal job states.
- Model experiment metadata and weights stored as artifacts.
- Headless, seeded evaluation and browser playback of at least one trajectory.
- Download of source CSV and evaluation JSON.
- Basic operational health checks and structured logs.

### Out of scope for MVP

- Roles, organizations, billing, public sign-up, and public sharing.
- Collaborative or simultaneous editing.
- Arbitrary model uploads, user-provided Python, or custom plugins/downsamplers.
- GPU training, large-scale dataset processing, or guaranteed high concurrency.
- In-browser PyTorch execution or live frame-by-frame inference calls to the API.
- Corrective demonstrations, model deployment as a general-purpose endpoint, and
  support for unrelated games.

## 5. Core user journey

1. The learner opens the lab and creates a project.
2. They start a collection session, play several episodes with arrow keys, and see
   episode outcomes and sample counts.
3. On finish, the platform saves the completed episodes and shows a dataset summary.
4. The learner reviews row count, episode count, outcomes, action balance, and
   no-op ratio. Invalid or insufficient data blocks training with an actionable
   explanation.
5. They select a preset, optional feature transform, and seed, then submit training.
6. The run page displays queued/running/completed/failed/cancelled state and epoch
   train/validation losses.
7. On completion, the learner starts evaluation with episode count, maximum steps,
   and seed. The backend calculates metrics and trajectories; the browser replays
   the trajectory and displays success rate, successful-step statistics, and
   failure reasons.
8. The learner can return to the project, compare runs, or download artifacts.

## 6. Functional requirements

### Projects and navigation

- Create, rename, and list projects.
- Project workspace contains **Play**, **Datasets**, **Training runs**, and
  **Evaluations** sections.
- Each dataset, run, and evaluation has a stable opaque ID and creation timestamp.
- A destructive delete action is not required in the MVP; provide an explicit
  confirmation if deletion is added during implementation.

### Browser game and collection

- Render a fixed logical play area that scales to the available viewport without
  changing recorded coordinate semantics. Use the existing logical dimensions and
  movement rules as the initial reference; document any required differences.
- Support arrow-key movement, pause/resume, start-next-episode, and end-session.
- Show current episode, samples recorded, and outcome (`success`, `out_of_bounds`,
  `stalled`, or `quit`/incomplete).
- Record one row per game step with schema version, episode ID, step, elapsed time,
  blue and target positions, action, and outcome, matching the current CSV schema.
- Save completed episodes automatically. Discard an explicitly abandoned,
  incomplete episode; explain this to the learner.
- Generate target positions from a recorded session seed so a collection session can
  be reproduced when useful.
- Prevent starting training from an empty dataset or a dataset with fewer than two
  completed episodes; the current training split requires at least two episodes.

### Dataset inspection

- Validate schema version and numeric fields on ingestion.
- Show sample count, completed episode count, outcome counts, action distribution,
  and no-op ratio.
- Warn about possible direction imbalance and repeated/no-op heavy demonstrations;
  warnings do not alter the raw dataset.
- Preserve raw demonstrations unchanged when training options are applied.
- Allow schema-v2 CSV download.

### Training

- Accept only server-defined preset/configuration values; do not accept executable
  plugins or arbitrary code from the browser.
- Validate dataset and configuration before enqueueing a job.
- Assign a stable run ID and persist the configuration, dataset fingerprint,
  progress, terminal status, and artifact locations.
- Keep training out of the synchronous API request. The worker processes queued
  jobs and reports epoch-level train and validation loss.
- Save the `.pth` weights and paired JSON experiment metadata, preserving the
  existing artifact semantics.
- A failed run records a learner-safe error message and an operator-visible detail
  in logs. A worker restart must not mark an unfinished job as completed.
- Cancellation is best effort. A queued job can be cancelled; a running job may be
  marked cancel-requested and stop at an epoch boundary.

### Evaluation and replay

- Evaluate only a completed run's paired experiment artifact.
- Allow episode count, maximum steps, and seed within server-defined bounds.
- Calculate success rate, mean/median successful steps, stalled count, and
  out-of-bounds count using existing evaluation semantics.
- Save the result as JSON with model/run reference and evaluation configuration.
- Include replayable per-step positions and outcomes for at least one episode; the
  browser animates these frames locally without per-frame API requests.
- Evaluation with identical artifact, config, and seed must be reproducible.

### Error and empty states

- Explain no projects, no datasets, invalid dataset, insufficient episodes, queued
  training, failed training, and no successful evaluation runs.
- Keep submitted configuration visible after failure so the learner can retry.
- Use friendly messages for expected validation failures and a request ID for
  unexpected server errors.

## 7. Proposed architecture

```text
Browser (React + TypeScript + Canvas) ─── Cognito hosted sign-in (PKCE)
        │ HTTPS JSON API + Cognito JWT (same CloudFront origin)
        ▼
API Gateway HTTP API
        ├── Cognito JWT authorizer
        ├── Lambda + FastAPI (on demand)
        │       ├── S3 (metadata, CSV, weights, evaluation results)
        │       └── SQS training queue
        │                  │
        │                  ▼
        │          Lambda container worker
        └── throttling and access logs

Static frontend: private S3 + CloudFront
```

### Service responsibilities

- **Frontend:** game rendering and keyboard input, workflow screens, status polling,
  loss charts, evaluation replay, and artifact downloads.
- **API:** request validation, project/dataset/run metadata, artifact downloads,
  job enqueueing, status/progress reads, and evaluation requests.
- **Worker:** load validated data, call existing training code, save artifacts,
  and update run status/progress. It runs as an SQS-triggered Lambda container;
  duplicate delivery is handled by checking persisted run state.
- **S3:** private object storage for small JSON metadata records, raw CSVs, model
  weights, paired experiment JSON, and evaluation outputs. Use opaque,
  server-generated object keys. Use a predictable prefix layout to list a project's
  datasets and runs without scanning unrelated objects.
- **SQS:** training job queue. Configure visibility timeout and retries to match
  worker behavior; make job processing idempotent because queue delivery can repeat.

The local implementation uses a single in-process worker thread and persists each
run's state in the local JSON store. It is a development adapter only: if the API
restarts during a run, that run is marked interrupted and can be retried. The AWS
pilot uses API Gateway and on-demand Lambda functions so compute can scale to zero
between requests; SQS triggers the separate training Lambda. The training function
uses a CPU-only PyTorch container image and is bounded by Lambda's 15-minute runtime
limit. Datasets that exceed that bound will need a Fargate or AWS Batch worker.

This serverless design avoids always-running API/worker tasks, an Application Load
Balancer, and NAT gateways. AWS charges still apply for Lambda execution, API Gateway
requests, SQS operations, S3 storage and requests, CloudFront data transfer, container
image storage, Cognito usage, and logs. The CloudFront site is reachable publicly,
but project and training API routes require Cognito JWTs. Public sign-up is disabled,
so only administrator-created users can access the workflow. `/health` and the public
auth-configuration endpoint reveal no project data. API throttling and a two-worker
concurrency cap further limit accidental bursts. Cognito pricing varies by feature
plan and active users; check current pricing before inviting a larger group.

The CDK `pause` command removes application API routes and the SQS event-source
mapping while retaining S3 data, the Cognito pool, and the website. This stops new
training work; an in-flight Lambda may finish, and queued messages wait until the
mapping is restored. The paused stack still has storage, CloudFront, and other
request-based charges.

For this single-user MVP, S3-backed metadata is a deliberate cost and simplicity
choice. S3 provides strong read-after-write consistency for object PUT/DELETE and
atomic replacement of an individual key, but it does not provide transactions
across multiple objects and concurrent writes to one key need application-level
coordination. Store metadata as one small JSON object per project, dataset, run, or
evaluation. Create immutable records with conditional writes, and update mutable run
records with ETag-based conditional writes and retry to avoid lost progress updates.
Write artifacts before publishing their object keys in a completed run record.
Use S3 prefix listing only for small MVP project collections; do not treat S3 as a
general query engine. If filtering, concurrent editing, or relationships become
complex, migrate the metadata store to a database.

The first implementation should keep evaluation synchronous only if measured
runtime stays comfortably within API limits; otherwise use the same queued job
pattern as training. The evaluation trajectory is returned as data and replayed in
the browser, avoiding a network request for every game frame.

## 8. Data model (logical)

- **Project:** `id`, `name`, `created_at`, `updated_at`.
- **Dataset:** `id`, `project_id`, `name`, `schema_version`, `row_count`,
  `episode_count`, `session_seed`, `fingerprint`, `object_key`, `created_at`.
- **TrainingRun:** `id`, `project_id`, `dataset_id`, `status`, `preset`, `config_json`,
  `progress_json`, `dataset_fingerprint`, `weights_object_key`,
  `metadata_object_key`, `error_code`, `created_at`, `started_at`, `completed_at`.
- **Evaluation:** `id`, `training_run_id`, `status`, `config_json`, `metrics_json`,
  `trajectory_object_key`, `created_at`, `completed_at`.

Dataset rows use the existing schema-v2 column contract from `game/util/data.py`:
`schema_version`, `episode_id`, `step`, `elapsed_ms`, `blue_x`, `blue_y`,
`target_x`, `target_y`, `action_x`, `action_y`, and `outcome`.

Store timestamps in UTC. IDs should be opaque UUIDs. Metadata objects should include
a record type and schema version for future migrations. Validate project and dataset
references in application code. For this single-user MVP, access control is
deployment-level; the API must still validate every referenced ID and never accept
an S3 object key directly from the client.

## 9. Initial API contract

All routes use `/api/v1`. JSON error responses use a stable shape such as
`{"error":{"code":"insufficient_episodes","message":"...","request_id":"..."}}`.

| Method and route | Purpose |
|---|---|
| `GET /health` | Liveness/readiness status for the API. |
| `GET /api/v1/projects` | List projects. |
| `POST /api/v1/projects` | Create project from `{name}`. |
| `GET /api/v1/projects/{project_id}` | Project and summary counts. |
| `POST /api/v1/projects/{project_id}/datasets` | Create dataset metadata and return upload instructions or accept a bounded CSV upload. |
| `GET /api/v1/datasets/{dataset_id}` | Dataset summary and validation results. |
| `GET /api/v1/datasets/{dataset_id}/download` | Download schema-v2 CSV. |
| `POST /api/v1/datasets/{dataset_id}/training-runs` | Validate config and enqueue training. |
| `GET /api/v1/training-runs/{run_id}` | Get status, config, progress, and artifact availability. |
| `POST /api/v1/training-runs/{run_id}/cancel` | Request cancellation. |
| `POST /api/v1/training-runs/{run_id}/evaluations` | Create seeded evaluation. |
| `GET /api/v1/evaluations/{evaluation_id}` | Get status, metrics, and replay availability. |
| `GET /api/v1/evaluations/{evaluation_id}/replay` | Get trajectory frames for browser playback. |

Use polling for training and evaluation status in the MVP, initially every 2–3
seconds while active and less often when queued for a long time. Keep response
payloads bounded; large CSV and replay objects should be downloaded separately.

## 10. Non-functional requirements

- **Reliability:** persisted metadata is authoritative; S3 objects are private;
  background jobs have explicit states and retry/error handling.
- **Security:** HTTPS in production, least-privilege IAM roles, server-side config
  allowlists, input size/row limits, CSV validation, and no client-controlled file
  paths or object keys. Keep secrets out of source control and browser bundles.
- **Performance:** game input and rendering remain local and responsive; API calls
  never occur per frame. Set an initial upload size limit (suggested 10 MB) and
  configurable per-run bounds. Profile before promising numerical latency targets.
- **Accessibility:** keyboard gameplay has visible instructions, clear focus states,
  status announcements, and non-color-only outcome labels. Provide controls for
  replay pause, restart, and speed.
- **Observability:** structured logs include request/job IDs; capture API errors,
  queue depth, job duration, worker failures, and storage errors.
- **Portability:** preserve a local development path using local JSON/filesystem
  storage and a local queue adapter where practical. Keep AWS
  integrations behind small interfaces so core domain/training logic is not tied to
  cloud SDK calls.

## 11. Milestones and implementation sequence

### Milestone 1 — Browser game and data contract

- Build Canvas game using explicit constants shared/documented with the Python game.
- Record complete episodes in the browser and export schema-v2 CSV.
- Add local-only project/dataset workflow to validate the experience before cloud
  persistence.
- **Exit criteria:** movement, collision, outcomes, pause, and export work; exported
  data loads through the current Python dataset loader.

### Milestone 2 — API and durable datasets

- Introduce FastAPI service, S3 metadata and artifact storage adapters, project and
  dataset routes, and metadata schema versioning.
- Validate uploaded dataset and return the same inspection signals used in the UI.
- **Exit criteria:** create/retrieve project and dataset, upload/download CSV, and
  retain records across API restarts.

### Milestone 3 — Asynchronous training

- Add SQS queue, worker Lambda container, run state transitions, progress, artifacts,
  and cancellation at safe boundaries.
- Reuse/refactor existing training and artifact functions behind service functions.
- **Exit criteria:** start a run from UI; observe progress and retrieve matching
  weights and JSON metadata after worker completion.

### Milestone 4 — Evaluation, replay, and AWS deployment

- **Local MVP complete:** add seeded evaluation and trajectory generation;
  implement browser replay and a metrics view. The API stores evaluation JSON and
  trajectory artifacts through the filesystem object-store adapter.
- **AWS pilot in progress:** provision static frontend, API, worker, bucket, queue,
  and Cognito user pool with administrator-created users using CDK. The pilot uses
  CloudFront/S3 for the frontend, API Gateway HTTP API with JWT authorization and
  Lambda for the API, SQS and a Lambda container for training, private S3 for data,
  and one-week CloudWatch log retention. CI deployment and operational alarms remain
  follow-up work.
- **Deployment exit criteria:** deployed end-to-end flow passes the MVP success
  measures with repeatable seeded evaluation and recoverable job status.

## 12. Key risks and mitigations

- **Browser/Python game drift:** share a documented game-constants contract and
  compare browser output against the Python domain rules during implementation.
- **Current runtime coupling:** Pygame owns input/rendering/timing, and CLI scripts
  use paths that may assume a particular working directory. Keep web orchestration
  separate and refactor reusable game/training logic behind stable functions.
- **Training reliability:** retries can duplicate work or artifacts. Make job IDs
  idempotent, use unique artifact paths, and persist state transitions.
- **Upload abuse/corruption:** enforce size/row limits, validate schema and finite
  numeric values, use private storage, and generate object keys server-side.
- **Scope expansion:** keep multi-tenant identity, sharing, arbitrary plugins, and
  GPU compute out of MVP until the invited-user workflow is proven.

## 13. Decisions to revisit after MVP

- Add per-user project isolation before expanding beyond the trusted pilot group.
- Decide whether evaluation should be synchronous or queued based on observed runtime.
- Review dataset retention, deletion, backups, and operating costs before inviting a
  broad audience.
- Consider charts comparing multiple models and corrective demonstrations after
  the core workflow is stable.

## 14. Definition of done

The MVP is ready when a learner can complete the full browser workflow from a clean
deployment; all saved data survives service restarts; datasets remain compatible
with the existing schema-v2 loader; seeded evaluation is repeatable; job failures
are visible and diagnosable; and the AWS deployment can be recreated from checked-in
infrastructure definitions.
