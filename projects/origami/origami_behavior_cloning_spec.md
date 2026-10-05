# Origami Behaviour Cloning Demo
## Product, Application, and Infrastructure Specification

**Status:** Implementation draft  
**Audience:** AI coding agent / software engineer  
**Primary goal:** Build a small, internet-accessible system that demonstrates machine learning and behaviour cloning through an origami activity during a remote presentation.

### Implementation notes (2026-10-03)

The first implementation is in `app/`, with an eight-action airplane configuration
in `config/experiment.yaml`. See `README.md` for local setup and `docs/aws/` for
separate AWS CLI provisioning, deployment, and teardown guides.

The following refinements supersede the corresponding recommendations below:

- AWS closed App Runner to new customers on April 30, 2026. Gus requested an
  alternative because account eligibility is unknown. The cloud guides provide
  ECS Express Mode plus an optional App Runner path for existing customers.
  [AWS availability notice](https://docs.aws.amazon.com/apprunner/latest/dg/apprunner-availability-change.html).
- Local persistence uses SQLite and local object files. AWS uses one DynamoDB
  table and private S3 objects. No relational database infrastructure is deployed.
- Direct S3 uploads use presigned POST with a size constraint. Completion validates
  and normalizes the image before making it eligible for training.
- Training runs in a background thread with persistent status and a 15-minute
  operation lease. Interrupted jobs can be retried after expiry; the previous model
  remains active. This is not a durable job queue.
- Training requires every configured action to meet the minimum sample count
  after splitting, so inference can report probabilities for every action.
- Admin cleanup closes collection and deletes images and participant/run/sample
  records. Model artifacts and evaluation metadata are retained; full cloud
  teardown removes them as well.

Real folding, mobile cameras, accuracy, 20-participant load, and AWS deployment
still require rehearsal. A known-good fallback must be prepared from real photos;
the repository does not include one.

---

## 1. Overview

This project is an educational demonstration of **behaviour cloning** using origami.

Participants follow a sequence of origami-folding instructions. Before executing each fold, they capture a photo of the current paper state. Each photo is paired with the action the participant is about to perform.

The collected dataset therefore consists of state/action pairs:

```text
(current paper image) -> (next folding action)
```

This can be represented as:

```text
D = {(s_i, a_i)}
```

where:

- `s_i` is an image of the current origami state.
- `a_i` is the human-demonstrated next action.

A machine-learning model is trained from those demonstrations to approximate a policy:

```text
pi(state) -> action
```

During inference, a participant or presenter captures an image of a partially folded origami object. The system predicts the action that a human demonstrator would most likely perform next.

The demonstration should make the following concepts tangible to a mixed technical and non-technical audience:

- supervised learning;
- demonstrations as training data;
- state/action pairs;
- behaviour cloning;
- training vs. testing;
- generalization;
- data diversity;
- confidence vs. correctness;
- distribution shift;
- compounding errors;
- the importance of dataset design.

The system is intended for a **remote presentation**, so all participant-facing functionality must be internet-accessible through a normal browser on phones and laptops.

---

## 2. Educational Narrative

The application is not merely a classifier demo. The user journey should reinforce the ML concepts.

The intended narrative is:

1. Humans receive folding instructions.
2. Humans learn and demonstrate the task.
3. Their demonstrations become a labelled dataset.
4. The presenter shows the dataset being assembled.
5. The presenter trains the model.
6. The trained model predicts the next action from unseen origami states.
7. The presenter deliberately introduces unusual states or visual variation.
8. The audience observes where the model generalizes and where it fails.

A useful phrase for the presentation is:

> You were not only learning origami. You were generating demonstrations for the machine.

The system should therefore expose enough of the ML process to make learning visible rather than hiding everything behind a black box.

---

## 3. Scope

### 3.1 In scope

The MVP must provide:

- a public web application;
- participant identification;
- an origami instruction workflow;
- mobile-friendly image capture;
- image upload;
- association of each image with the correct action label;
- persistent storage of images;
- persistent storage of sample metadata;
- a dataset summary/admin view;
- model training;
- evaluation metrics;
- persistence of the trained classifier;
- inference from newly captured images;
- class probabilities/confidence display;
- presenter/admin controls;
- deployment on AWS;
- a simple mechanism to prevent arbitrary public access.

### 3.2 Out of scope for MVP

Do **not** build the following unless required later:

- React or another frontend SPA framework;
- Kubernetes;
- SageMaker pipelines;
- distributed model training;
- GPU infrastructure;
- fine-tuning a large vision model;
- a production-grade identity platform unless explicitly selected;
- complex RBAC;
- relational database infrastructure;
- real-time WebSocket orchestration;
- image annotation tooling;
- automatic action recognition from video;
- robotics control;
- multi-tenant SaaS capabilities.

The design should remain intentionally small and understandable.

---

## 4. Core Design Principle

Use a **pretrained vision encoder** and train only a lightweight classifier.

Recommended pipeline:

```text
image
  |
  v
pretrained vision encoder
  |
  v
embedding vector
  |
  v
small supervised classifier
  |
  v
predicted folding action
```

Recommended implementation:

- Python
- PyTorch
- torchvision
- pretrained ResNet18 or MobileNetV3
- encoder weights frozen
- scikit-learn `LogisticRegression` classifier
- `joblib` for classifier persistence

This is preferable to training a CNN from scratch because:

- very little data will be available;
- training must be quick enough for a live presentation;
- CPU-only execution should be feasible;
- the educational story remains simple;
- the pretrained encoder lets the demo focus on behaviour cloning instead of low-level visual feature learning.

---

## 5. Origami Task Design

Choose one origami object with approximately **6-10 distinct actions**.

**Selected MVP figure:** basic dart paper airplane using rectangular paper.
Target 5-10 minutes for the participant activity, including folding and photo
capture. Rehearse the final action sequence against this time budget.
The dog face is a follow-up experiment once the system is running; keep figure
instructions configurable and datasets/models scoped to their experiment.

The folding sequence must avoid ambiguous or visually indistinguishable steps where possible.

Example action classes:

```text
fold_in_half
fold_left_corner_inward
fold_right_corner_inward
fold_bottom_flap_up
flip_over
fold_sides_in
open_center
flatten
```

The exact origami object and action vocabulary should be configurable rather than hard-coded throughout the application.

Store the instructions in a configuration file such as:

```yaml
experiment:
  id: origami_demo_01
  name: Origami Behaviour Cloning Demo

steps:
  - index: 0
    action_id: fold_in_half
    title: Fold in half
    instruction: Fold the square horizontally in half.

  - index: 1
    action_id: fold_left_corner_inward
    title: Fold left corner inward
    instruction: Fold the top-left corner toward the centre line.
```

The application should render the current human instruction but persist only stable identifiers such as `action_id`.

---

## 6. Critical Data Collection Semantics

This is one of the most important implementation details.

The image must represent the state **before the demonstrated action is performed**.

Correct sequence:

```text
paper is in state S_t
        |
        v
participant takes photo
        |
        v
system associates photo with action A_t
        |
        v
participant performs A_t
        |
        v
paper reaches S_(t+1)
```

Therefore each sample means:

```text
state_before_action -> next_action
```

Do not capture the image after the fold and label it with the fold that has already happened.

This must be clear in the participant UI.

Recommended participant wording:

> Take a photo of the paper as it looks now, before performing the next fold.

Then show the action instruction.

---

## 7. Participant Experience

### 7.1 Entry page

The participant visits a public HTTPS URL.

Example:

```text
https://origami.example.com
```

The entry page should explain:

- this is a behaviour-cloning demonstration;
- participants will fold origami;
- a photo is captured before each action;
- photos are used temporarily for the ML demo.

Minimal fields:

```text
Display name: [ Alice ]
Event code:   [ ORIGAMI42 ]

[ Join experiment ]
```

### 7.2 Authentication / access control

For the MVP, the preferred approach is:

- event code;
- participant-provided display name;
- server-generated random participant/session identifier;
- signed session cookie.

This is intentionally lighter than Cognito.

Reasons:

- lower friction during a live presentation;
- no email verification;
- no password-reset flow;
- fewer AWS moving parts;
- security requirements are modest.

The implementation should, however, keep the authentication boundary modular enough that Cognito can replace this later.

If Cognito is used instead, configure:

- username/password authentication;
- no MFA;
- minimal required attributes;
- self-service signup or pre-created users;
- no unnecessary profile data.

### 7.3 Folding workflow

Participant flow:

```text
Join experiment
      |
      v
Read short instructions
      |
      v
Start run
      |
      v
Step 1
  - see instruction
  - capture current state photo
  - confirm upload
  - perform fold
      |
      v
Step 2
      |
      v
...
      |
      v
Run complete
```

The UI must be mobile-first.

Use standard browser camera capture where possible:

```html
<input
  type="file"
  accept="image/*"
  capture="environment">
```

Do not build custom WebRTC capture for the MVP unless browser compatibility requires it.

### 7.4 Multiple demonstrations

Participants should be able to perform multiple complete runs.

Each run gets a unique `run_id`.

This enables experiments such as:

- one demonstration per participant;
- multiple demonstrations from the same participant;
- comparison of low-diversity and high-diversity datasets.

---

## 8. Presenter/Admin Experience

The presenter needs a separate admin interface.

Recommended routes:

```text
/admin
/admin/dataset
/admin/train
/admin/demo
```

### 8.1 Admin dashboard

Show:

- experiment name;
- experiment state;
- number of participants;
- number of runs;
- total images;
- samples per action;
- participants selected for training;
- participants selected for testing;
- current model version;
- latest training result.

Example:

```text
Origami Behaviour Cloning

Participants:          14
Completed runs:        22
Training samples:     144
Held-out samples:      32
Actions:                8

Model status: READY
Model version: 2026-10-03T20:42:11Z

Training accuracy:     96%
Held-out accuracy:     74%

[ Train Model ]
[ Open Live Demo ]
```

### 8.2 Dataset browser

Provide a simple thumbnail grid.

Each sample should display:

- participant display name;
- run;
- step;
- action label;
- thumbnail.

Optional but valuable:

- filter by participant;
- filter by action;
- mark sample excluded;
- delete obviously broken uploads.

### 8.3 Training controls

Minimum:

```text
[ Train Model ]
```

The presenter should see progress and the final metrics.

Training is manually triggered by the presenter; do not automatically retrain
as samples arrive. Prepare a known-good fallback model before the presentation
and allow the presenter to explicitly activate it. Display the active model's
version and whether it is the live-trained model or the prepared fallback.
Fallback readiness is a rehearsal requirement, not an artifact already supplied
by this specification.

Useful dataset information:

```text
Generating embeddings...
118 / 160

Training classifier...

Model ready.
```

Training does not need distributed execution.

### 8.4 Live demo page

The presenter can:

- capture a photo;
- upload a photo;
- request inference;
- see the top prediction;
- see all class probabilities.

Example:

```text
Prediction:
Fold bottom flap upward

Confidence:
74%

All actions:

fold_bottom_flap_up      74%
fold_sides_in            13%
open_center               7%
flatten                   3%
other                     3%
```

Probability display is a key teaching feature.

---

## 9. Recommended AWS Architecture

Use AWS primarily to provide:

- public internet access;
- HTTPS;
- persistent object storage;
- persistent metadata;
- a small web/API runtime.

Recommended architecture:

```text
                    Internet
                       |
                       v
               +---------------+
               |   App Runner  |
               |               |
               | FastAPI       |
               | HTML/CSS/JS   |
               | ML training   |
               | ML inference  |
               +-------+-------+
                       |
          +------------+-------------+
          |                          |
          v                          v
     +---------+                +----------+
     |   S3    |                | DynamoDB |
     |         |                |          |
     | images  |                | metadata |
     | models  |                | samples  |
     +---------+                +----------+
```

Optional:

```text
Cognito
```

only if username/password authentication is preferred over the event-code approach.

---

## 10. AWS Components

### 10.1 Amazon ECR

Store the application container.

Example repository:

```text
origami-behaviour-cloning
```

Application deployment flow:

```text
source
  |
  v
docker build
  |
  v
ECR
  |
  v
App Runner
```

### 10.2 AWS App Runner

Run the FastAPI application.

Responsibilities:

- serve HTML/CSS/JS;
- serve REST endpoints;
- issue S3 presigned upload URLs;
- read/write DynamoDB metadata;
- run the pretrained encoder;
- train classifier;
- run inference;
- fetch/save model artifacts.

The application should be designed as stateless.

Do not rely on local disk for persistent user data or the active model.

### 10.3 Amazon S3

Use S3 for:

- training images;
- optional evaluation images;
- trained classifiers;
- model metadata;
- optional exported datasets.

Suggested object layout:

```text
s3://<bucket>/
  experiments/
    <experiment_id>/
      samples/
        <participant_id>/
          <run_id>/
            step-000.jpg
            step-001.jpg
            step-002.jpg

      models/
        model-<timestamp>.joblib
        model-<timestamp>.json
        current.json
```

Do not expose the bucket publicly.

Uploads should use presigned URLs.

### 10.4 DynamoDB

Use DynamoDB for structured metadata.

Recommended tables or logical entities:

- experiments;
- participants;
- runs;
- samples;
- model versions.

This may be one table with typed items or several simple tables.

For MVP clarity, separate tables are acceptable.

---

## 11. Why Direct-to-S3 Uploads

Training samples should not be proxied through FastAPI unless necessary.

Preferred flow:

```text
browser
   |
   | POST /api/samples
   v
FastAPI
   |
   | create metadata record
   | generate presigned S3 PUT URL
   v
browser
   |
   | PUT image
   v
S3
   |
   | upload complete
   v
browser
   |
   | POST /api/samples/{id}/complete
   v
FastAPI
```

Benefits:

- App Runner does not process large image bodies;
- less server bandwidth;
- simpler scaling;
- S3 becomes the authoritative binary store.

Inference images may be posted directly to FastAPI because they are transient and low volume.

---

## 12. Suggested Data Model

### 12.1 Experiment

```json
{
  "experiment_id": "origami_demo_01",
  "name": "Origami Behaviour Cloning Demo",
  "status": "COLLECTING",
  "created_at": "...",
  "event_code_hash": "...",
  "active_model_version": "..."
}
```

Possible statuses:

```text
SETUP
COLLECTING
TRAINING
READY
CLOSED
```

### 12.2 Participant

```json
{
  "participant_id": "uuid",
  "experiment_id": "origami_demo_01",
  "display_name": "Alice",
  "created_at": "..."
}
```

### 12.3 Run

```json
{
  "run_id": "uuid",
  "experiment_id": "origami_demo_01",
  "participant_id": "uuid",
  "status": "COMPLETE",
  "started_at": "...",
  "completed_at": "..."
}
```

### 12.4 Sample

```json
{
  "sample_id": "uuid",
  "experiment_id": "origami_demo_01",
  "participant_id": "uuid",
  "run_id": "uuid",
  "step_index": 3,
  "action_id": "fold_bottom_flap_up",
  "s3_key": "experiments/origami_demo_01/samples/...",
  "status": "READY",
  "excluded": false,
  "created_at": "..."
}
```

Possible sample statuses:

```text
PENDING_UPLOAD
READY
FAILED
EXCLUDED
```

### 12.5 Model version

```json
{
  "model_version": "2026-10-03T20:42:11Z",
  "experiment_id": "origami_demo_01",
  "artifact_s3_key": "...",
  "created_at": "...",
  "encoder": "resnet18-imagenet",
  "classifier": "logistic_regression",
  "training_participants": ["..."],
  "test_participants": ["..."],
  "training_samples": 144,
  "test_samples": 32,
  "training_accuracy": 0.96,
  "test_accuracy": 0.74
}
```

---

## 13. API Design

Suggested endpoints.

### Experiment

```text
GET  /api/experiment
```

### Participant/session

```text
POST /api/session/join
POST /api/session/leave
```

### Runs

```text
POST /api/runs
GET  /api/runs/{run_id}
POST /api/runs/{run_id}/complete
```

### Instructions

```text
GET /api/steps
GET /api/steps/{index}
```

### Samples

```text
POST /api/samples
POST /api/samples/{sample_id}/complete
GET  /api/samples
POST /api/samples/{sample_id}/exclude
```

### Dataset stats

```text
GET /api/dataset/stats
```

### Training

```text
POST /api/train
GET  /api/train/status
GET  /api/models
```

### Inference

```text
POST /api/predict
```

### Admin

Admin functionality may reuse the same API with an admin session.

---

## 14. Training Pipeline

### 14.1 Dataset construction

Retrieve all eligible samples.

Exclude:

- incomplete uploads;
- explicitly excluded samples;
- unsupported image formats;
- corrupted images.

### 14.2 Split strategy

Do **not** default to random image-level splitting.

Preferred evaluation:

```text
participants A-E -> training
participant F    -> held-out test
```

The held-out participant's images must not appear in training.

This makes the evaluation measure generalization to another person's folding style and image-taking conditions.

Optionally expose two metrics:

- random image split;
- participant-level split.

This can illustrate how an easy split may overestimate performance.

### 14.3 Feature extraction

For each image:

1. load from S3;
2. decode with Pillow;
3. resize/crop using the pretrained model's expected transform;
4. run through the frozen encoder;
5. extract embedding;
6. pair embedding with action label.

Conceptual code:

```python
for sample in samples:
    image = load_from_s3(sample.s3_key)
    tensor = preprocess(image)
    embedding = encoder(tensor)
    X.append(embedding)
    y.append(sample.action_id)
```

### 14.4 Classifier

Use:

```python
sklearn.linear_model.LogisticRegression
```

Recommended settings should accommodate multiclass classification.

### 14.5 Training output

Persist:

- classifier;
- class list/order;
- encoder identifier;
- preprocessing version;
- training/test participant IDs;
- training metrics;
- confusion matrix if convenient.

Artifacts:

```text
classifier.joblib
model_metadata.json
```

Upload both to S3.

### 14.6 Current model pointer

Persist a small model pointer such as:

```json
{
  "model_version": "2026-10-03T20:42:11Z",
  "artifact": "experiments/.../models/model-....joblib"
}
```

Workers must be able to resolve the active model from persistent storage.

Do not make process memory the source of truth.

---

## 15. Model Loading and App Runner Scaling

App Runner may replace or scale instances.

Therefore:

- training output must be persisted to S3;
- active model version must be persisted;
- each worker must be able to load the current model independently.

Recommended inference behavior:

```text
request arrives
   |
   v
check active model version
   |
   +-- same as local cache --> use cached classifier
   |
   +-- newer version -------> download from S3
                              load classifier
                              replace cache
```

The pretrained encoder can be packaged in the image or initialized at process startup.

Prefer packaging/caching model weights so deployment does not depend on internet downloads at runtime.

---

## 16. Inference Pipeline

Input:

- uploaded JPEG/PNG image.

Processing:

```text
image
  |
  v
preprocess
  |
  v
frozen encoder
  |
  v
embedding
  |
  v
classifier.predict_proba
  |
  v
action probabilities
```

Response example:

```json
{
  "model_version": "2026-10-03T20:42:11Z",
  "prediction": {
    "action_id": "fold_bottom_flap_up",
    "probability": 0.74
  },
  "probabilities": [
    {
      "action_id": "fold_bottom_flap_up",
      "probability": 0.74
    },
    {
      "action_id": "fold_sides_in",
      "probability": 0.13
    }
  ]
}
```

The UI should display all class probabilities, preferably as bars.

---

## 17. Frontend Requirements

Use:

- server-rendered HTML;
- CSS;
- small amounts of vanilla JavaScript.

Do not add a SPA framework unless a concrete need appears.

### Required views

```text
/
  Join page

/instructions
  Intro / how to participate

/collect
  Folding workflow

/complete
  Run completed

/admin
  Dashboard

/admin/dataset
  Dataset browser

/admin/train
  Training controls/status

/admin/demo
  Live inference page
```

### Mobile requirements

The collection workflow must work comfortably on:

- iPhone Safari;
- Android Chrome;
- desktop Chrome/Firefox.

Image capture should degrade gracefully to normal file upload.

---

## 18. Image Handling

Recommended safeguards:

- accept JPEG and PNG;
- reject unreasonable file sizes;
- resize very large photos before training or during preprocessing;
- optionally normalize image orientation from EXIF;
- strip unnecessary metadata if easy;
- preserve enough resolution for the fold geometry.

Do not assume all participants hold phones in the same orientation.

This variation is educationally useful.

---

## 19. Security Assumptions

This is a demonstration system, not a production user platform.

Threat model is modest.

Minimum security:

- HTTPS only;
- S3 bucket private;
- presigned upload URLs;
- event code or basic login;
- admin area protected separately;
- App Runner IAM role has only required S3/DynamoDB permissions;
- do not expose AWS credentials to browser clients;
- validate uploaded content type and file size;
- rate-limit obvious abuse if trivial to implement.

No need for:

- enterprise SSO;
- advanced MFA;
- complex IAM per participant;
- long-term personal profiles.

The system should include a simple way to delete the experiment dataset after the presentation.

---

## 20. Privacy Considerations

Photos are intended to show origami paper, but participant hands or surroundings may appear.

The UI should mention that:

- captured images are used for the demonstration;
- images may temporarily contain hands/backgrounds;
- participants should avoid including faces or sensitive information;
- data may be deleted after the event.

**Selected retention policy:** retain the dataset until the presenter manually
deletes it. Provide an admin cleanup action for experiment images and associated
participant, run, and sample metadata. Do not configure automatic dataset expiry.
Participant-facing copy must describe manual retention/deletion and must not
promise automatic deletion after the presentation.

---

## 21. Failure Modes and Recovery

### Upload fails

UI must:

- preserve current step;
- allow retry;
- not advance until upload is confirmed.

### Camera unavailable

Fallback:

```text
Choose image file
```

### Corrupt image

Mark sample failed and ask participant to recapture.

### Training fails

Admin page should show:

- failure message;
- last known good model remains active.

Never replace the active model until the newly trained model is successfully serialized and uploaded.

### Insufficient samples

Training endpoint should validate:

- at least two classes represented;
- configurable minimum samples per class.

Display a useful error instead of training a meaningless model.

### Missing held-out participant

If participant-level evaluation cannot be created, train anyway but explicitly mark evaluation mode.

### AWS instance restart

Application must recover from S3/DynamoDB with no loss of persistent state.

---

## 22. Observability

Keep observability lightweight.

Minimum:

- structured application logs;
- request errors;
- upload failures;
- training start/end/failure;
- model version activation;
- prediction errors.

CloudWatch logs from App Runner are sufficient.

Useful metrics to show in admin UI:

- sample count;
- participants;
- completed runs;
- samples per action;
- excluded samples;
- current model version.

---

## 23. Testing

### Unit tests

Test:

- action config parsing;
- sample metadata creation;
- model serialization/deserialization;
- image preprocessing;
- embedding shape;
- classifier training;
- prediction response;
- dataset split by participant.

### API tests

Test:

- join session;
- create run;
- create sample;
- complete sample;
- dataset stats;
- train endpoint;
- predict endpoint.

### Integration tests

Use a local test setup for:

- S3-compatible or mocked object storage;
- DynamoDB local/mocked access.

### Manual browser tests

Verify:

- iPhone photo upload;
- Android photo upload;
- desktop upload;
- retry behavior;
- admin training;
- model inference.

---

## 24. Local Development

Recommended local stack:

```text
FastAPI
local filesystem or LocalStack for S3
DynamoDB Local or in-memory repository
PyTorch
torchvision
scikit-learn
```

The storage interfaces should be abstracted enough that local development does not require deploying to AWS after every code change.

Example interfaces:

```python
class SampleRepository:
    ...

class ObjectStore:
    ...

class ModelRepository:
    ...
```

Production implementations:

```text
DynamoDBSampleRepository
S3ObjectStore
S3ModelRepository
```

Test/local implementations may use local files or memory.

---

## 25. Suggested Repository Layout

```text
origami-bc/
|
+-- app/
|   +-- main.py
|   |
|   +-- api/
|   |   +-- session.py
|   |   +-- runs.py
|   |   +-- samples.py
|   |   +-- training.py
|   |   +-- inference.py
|   |
|   +-- domain/
|   |   +-- models.py
|   |   +-- experiment.py
|   |
|   +-- storage/
|   |   +-- s3.py
|   |   +-- dynamodb.py
|   |
|   +-- ml/
|   |   +-- encoder.py
|   |   +-- dataset.py
|   |   +-- trainer.py
|   |   +-- inference.py
|   |   +-- artifacts.py
|   |
|   +-- templates/
|   |   +-- join.html
|   |   +-- collect.html
|   |   +-- complete.html
|   |   +-- admin.html
|   |   +-- dataset.html
|   |   +-- demo.html
|   |
|   +-- static/
|       +-- css/
|       +-- js/
|
+-- config/
|   +-- experiment.yaml
|
+-- infra/
|   +-- ...
|
+-- tests/
|
+-- Dockerfile
+-- pyproject.toml
+-- README.md
```

---

## 26. Infrastructure as Code

Prefer infrastructure as code.

Acceptable options:

- AWS CDK;
- Terraform;
- CloudFormation.

If no preference is provided, use whichever results in the smallest, clearest implementation.

Infrastructure should create:

- ECR repository;
- S3 bucket;
- DynamoDB tables;
- IAM role/policies;
- App Runner service;
- environment variables/secrets;
- optional custom domain resources only if needed.

Do not over-engineer networking.

A VPC should not be introduced unless required by a chosen component.

---

## 27. Environment Configuration

Possible variables:

```text
APP_ENV
AWS_REGION
S3_BUCKET
EXPERIMENT_ID
EVENT_CODE_HASH
ADMIN_PASSWORD_HASH
DYNAMODB_PARTICIPANTS_TABLE
DYNAMODB_RUNS_TABLE
DYNAMODB_SAMPLES_TABLE
DYNAMODB_MODELS_TABLE
MODEL_CACHE_DIR
MAX_UPLOAD_BYTES
```

Secrets should not be committed to the repository.

---

## 28. Model Experimentation Features

If time permits, support multiple training modes.

### Mode A: Small / low-diversity training set

Train on one or a few participants.

### Mode B: Diverse training set

Train on many participants.

Then compare performance on an unseen participant.

This supports the teaching point:

> Diverse demonstrations usually improve robustness to new people and conditions.

A second useful comparison:

### Random sample split

Images from the same participants may appear in train and test.

### Participant-level split

Entire participants are held out.

This can illustrate how evaluation methodology affects apparent performance.

---

## 29. Suggested Implementation Phases

### Phase 1: Local vertical slice

Build locally:

```text
join
 -> start run
 -> capture/upload images
 -> persist metadata
 -> train model
 -> predict image
```

Do not start with AWS.

Acceptance:

- one developer can complete a full origami run locally;
- model trains;
- inference returns probabilities.

### Phase 2: AWS persistence

Add:

- S3;
- DynamoDB.

Acceptance:

- data survives process restart.

### Phase 3: AWS deployment

Add:

- ECR;
- App Runner;
- HTTPS endpoint.

Acceptance:

- external phone can join and upload images over the internet.

### Phase 4: Admin/presentation polish

Add:

- dataset stats;
- thumbnail browser;
- training status;
- probability bars;
- held-out evaluation.

### Phase 5: Rehearsal hardening

Test:

- mobile browsers;
- multiple participants;
- failed uploads;
- training with partial data;
- inference after App Runner restart.

---

## 30. Acceptance Criteria

The MVP is complete when all of the following are true:

1. A participant can open a public HTTPS URL from a phone.
2. The participant can join using a display name and event code.
3. The participant can complete a multi-step origami run.
4. A photo is captured before each action.
5. Every photo is associated with the correct `action_id`.
6. Images are stored in S3.
7. Sample metadata is persisted outside the App Runner instance.
8. The admin can see participant/sample counts.
9. The admin can train a model from collected demonstrations.
10. The training process uses a frozen pretrained vision encoder.
11. The classifier is persisted to S3.
12. The trained model survives application restart.
13. A new image can be submitted for inference.
14. The API returns probabilities for all actions.
15. The UI displays the predicted action and confidence.
16. The system can evaluate on a held-out participant.
17. Failed uploads can be retried.
18. A failed training run does not destroy the last good model.
19. The complete workflow can be executed during a remote presentation.

---

## 31. Presentation-Specific Recommendations

The live presentation should ideally follow this sequence:

```text
1. Explain the task.
2. Audience starts folding.
3. Audience generates demonstrations.
4. Show live dataset statistics.
5. Reveal that the photos are state/action pairs.
6. Train model live.
7. Show evaluation result.
8. Perform normal inference.
9. Rotate paper / change background / partially cover state.
10. Observe confidence and errors.
11. Explain generalization and distribution shift.
12. Optionally show a deliberately wrong fold.
13. Explain compounding error in behaviour cloning.
```

The application should support this narrative rather than merely providing CRUD operations.

---

## 32. Design Decisions Currently Assumed

The implementation agent should proceed with these assumptions unless explicitly changed.

### Authentication

**Assumed MVP:** event code + display name + signed session cookie.

Cognito is deferred.

### Backend

**Assumed:** Python + FastAPI.

### Frontend

**Assumed:** server-rendered HTML + vanilla JavaScript.

### Deployment

**Assumed:** AWS App Runner from ECR.

### Image storage

**Assumed:** private S3 bucket with presigned uploads.

### Metadata

**Assumed:** DynamoDB.

### ML

**Assumed:**

```text
torchvision pretrained ResNet18 or MobileNetV3
frozen encoder
scikit-learn LogisticRegression
```

Prefer ResNet18 initially because it is conventional and easy to reason about. MobileNetV3 is acceptable if memory/startup constraints make it more attractive.

### Evaluation

**Assumed:** participant-level holdout whenever enough participants exist.

### Training execution

**Assumed:** training runs inside the App Runner process for MVP.

This is intentionally simple.

If training becomes too slow or App Runner request/runtime limits make synchronous execution unreliable, the next step should be a small asynchronous job mechanism, not SageMaker by default.

---

## 33. Resolved Product Decisions

All eight product decisions were resolved with Gus on 2026-10-03. Confirmed
answers are recorded below. Rehearsal recommendations and the proposed action
sequence remain subject to validation during implementation.

### 1. Origami figure

**Confirmed:** use the basic dart paper airplane for the MVP. Gus would also
like to try the dog face after the system is running.

Research shortlist:

- **Basic dart paper airplane — selected for the MVP.** Uses
  rectangular paper and simple folds. The tutorial's grouped instructions can
  be adapted into approximately eight capture/action pairs by separating left
  and right folds and treating the initial crease-and-unfold as one action.
  This is a proposed action vocabulary, not a validated sequence.
  [Folding reference](https://cdn.foldnfly.com/lounge/how-to-make-a-paper-airplane.php).
- **Traditional paper boat.** A tutorial explicitly supports A4 or Letter
  paper. Opening and flattening stages introduce more handling complexity;
  the final action count depends on grouping.
  [Folding reference](https://www.youtube.com/watch?v=ClLtg0Jyj-E).
- **Dog face.** Simple square-paper alternative, but the referenced sequence
  includes unfolding and flips, which may produce visually similar states.
  Letter paper would need to be prepared as a square before collection.
  [Folding reference](https://www.origamiway.com/easy-origami-dog/).

The ML suitability assessment is a design hypothesis. Rehearse the chosen
sequence and inspect pre-action photos, especially mirrored states, creases,
and flips. Define a consistent capture orientation for the baseline demo.
Do not count paper preparation or final decoration as training actions.

The exact action sequence and instruction text still require rehearsal.

Ideal properties:

- 6-10 actions;
- clearly distinguishable intermediate states;
- easy enough for first-time participants;
- inexpensive paper;
- no scissors/glue;
- minimal fine motor skill required.

### 2. Participant count

**Confirmed planning range:** approximately 6-20 simultaneous participants.
Gus expects to recruit at least six; the upper bound is uncertain.

Use 20 simultaneous participants as the implementation/rehearsal load target,
not as a measured capacity guarantee or an approved hard admission limit.
If a limit becomes necessary, Gus is willing to have people participate in
teams. Team session identity and held-out grouping must then be defined before
collection.

**Confirmed activity budget:** 5-10 minutes for folding and photo capture.

### 3. Account model

**Confirmed:** event code + participant display name, with a server-generated
participant/session identifier and signed session cookie. Cognito is deferred.

### 4. Dataset retention

**Confirmed:** manual deletion by the presenter through an admin cleanup action.
Retain the dataset until that action is taken; no automatic dataset expiry.

### 5. Presenter access

**Confirmed:** separate presenter/admin password and admin session.

### 6. Live training expectation

**Confirmed:** train live and prepare a known-good fallback model before the
presentation. The presenter can explicitly activate the fallback if live training
fails or the collected dataset is insufficient. A hosted fallback still depends
on the application being available; it does not by itself provide offline recovery.

### 7. Training trigger

**Confirmed:** manually triggered by the presenter. Do not automatically retrain
as samples arrive or unexpectedly switch models during the demonstration.

### 8. Paper constraints

**Confirmed:** coloured paper can be arranged for the presentation. Only white
Letter paper is available to Gus during implementation.

Use rectangular paper for the selected airplane; white Letter paper must work
during development. Coloured rectangular paper can be arranged for the event.
For the later dog-face experiment, prepare square sheets before the recorded
workflow begins.

**Rehearsal recommendation:** include presentation paper colours in the rehearsal
dataset and evaluate on held-out participants. Successful inference on white
development paper alone does not establish performance on coloured paper.

---

## 34. Non-Goals and Guardrails for the Implementation Agent

The agent should not introduce complexity merely because it is common in production ML systems.

Specifically, do not add:

- Kubernetes;
- Kafka;
- Celery unless asynchronous training becomes necessary;
- PostgreSQL unless DynamoDB proves unsuitable;
- React;
- Redis;
- SageMaker;
- feature stores;
- MLflow;
- model registries;
- separate microservices.

The value of this project is that the entire behaviour-cloning lifecycle remains understandable.

A compact system is a feature, not a limitation.

---

## 35. Final Architectural Summary

```text
PARTICIPANT
 phone/browser
      |
      | HTTPS
      v
+------------------------+
| AWS App Runner         |
|                        |
| FastAPI                |
| HTML/CSS/JS            |
| Session handling       |
| S3 presign             |
| Training orchestration |
| Frozen vision encoder  |
| Classifier inference   |
+-----------+------------+
            |
       +----+----+
       |         |
       v         v
   +-------+  +----------+
   |  S3   |  | DynamoDB |
   |       |  |          |
   |images |  |samples   |
   |models |  |runs      |
   +-------+  |users     |
              |models    |
              +----------+

TRAINING

S3 images
   |
   v
pretrained frozen encoder
   |
   v
embeddings
   |
   v
LogisticRegression
   |
   v
classifier artifact
   |
   v
S3

INFERENCE

new image
   |
   v
same pretrained encoder
   |
   v
embedding
   |
   v
active classifier
   |
   v
action probabilities
```

The system should optimize for:

- educational clarity;
- fast implementation;
- reliable remote participation;
- visible ML lifecycle;
- simple AWS infrastructure;
- easy teardown after the event.
