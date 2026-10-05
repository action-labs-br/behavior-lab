"""Small local-first API for projects and schema-v2 demonstration datasets.

The storage operations live behind ``LocalObjectStore`` so they can be replaced
with S3 without changing the HTTP or domain contract.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import sys
import tempfile
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, FiniteFloat, field_validator

SCHEMA_VERSION = 2
CSV_COLUMNS = (
    "schema_version", "episode_id", "step", "elapsed_ms", "blue_x", "blue_y",
    "target_x", "target_y", "action_x", "action_y", "outcome",
)
OUTCOMES = {"success", "out_of_bounds", "stalled", "quit"}
DATA_ROOT = Path(os.environ.get("BEHAVIOR_LAB_DATA_DIR", ".local-data"))
LOGGER = logging.getLogger("behavior_lab.training")
GAME_ROOT = Path(__file__).resolve().parents[2] / "game"
if str(GAME_ROOT) not in sys.path:
    sys.path.insert(0, str(GAME_ROOT))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LocalObjectStore:
    """Filesystem implementation of the metadata/artifact storage contract."""

    def __init__(self, root: Path):
        self.root = root

    def put_json(self, key: str, value: dict[str, Any]) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")
        temporary.replace(path)

    def get_json(self, key: str) -> dict[str, Any] | None:
        path = self._path(key)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def put_bytes(self, key: str, value: bytes, content_type: str = "application/octet-stream") -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)

    def get_bytes(self, key: str) -> bytes | None:
        path = self._path(key)
        return path.read_bytes() if path.is_file() else None

    def list_json(self, prefix: str) -> list[dict[str, Any]]:
        directory = self._path(prefix)
        if not directory.is_dir():
            return []
        records = []
        for path in directory.rglob("*.json"):
            try:
                records.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return records

    def _path(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        if not candidate.is_relative_to(self.root.resolve()):
            raise ValueError("Invalid object key")
        return candidate


class S3ObjectStore:
    """S3 implementation of the metadata and artifact storage contract."""

    def __init__(self, bucket: str, region: str | None = None):
        import boto3
        from botocore.config import Config

        self.bucket = bucket
        self.client = boto3.Session(region_name=region).client(
            "s3",
            config=Config(retries={"total_max_attempts": 3, "mode": "standard"}),
        )

    def put_json(self, key: str, value: dict[str, Any]) -> None:
        self.put_bytes(key, json.dumps(value, separators=(",", ":")).encode("utf-8"), "application/json")

    def get_json(self, key: str) -> dict[str, Any] | None:
        content = self.get_bytes(key)
        return json.loads(content) if content is not None else None

    def put_bytes(self, key: str, value: bytes, content_type: str = "application/octet-stream") -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=value, ContentType=content_type)

    def get_bytes(self, key: str) -> bytes | None:
        from botocore.exceptions import ClientError

        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in {"NoSuchKey", "404", "NotFound"}:
                return None
            raise
        with response["Body"] as body:
            return body.read()

    def list_json(self, prefix: str) -> list[dict[str, Any]]:
        records = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix.rstrip("/") + "/"):
            for item in page.get("Contents", []):
                key = item["Key"]
                if not key.endswith(".json"):
                    continue
                try:
                    document = self.get_json(key)
                    if document is not None:
                        records.append(document)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    LOGGER.exception("Skipping invalid JSON object %s", key)
        return records


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        result = value.strip()
        if not result:
            raise ValueError("Project name cannot be blank")
        return result


class Sample(BaseModel):
    schema_version: int = Field(ge=2, le=2)
    episode_id: int = Field(ge=1)
    step: int = Field(ge=0)
    elapsed_ms: int = Field(ge=0)
    blue_x: FiniteFloat
    blue_y: FiniteFloat
    target_x: FiniteFloat
    target_y: FiniteFloat
    action_x: FiniteFloat
    action_y: FiniteFloat
    outcome: str

    @field_validator("outcome")
    @classmethod
    def known_outcome(cls, value: str) -> str:
        if value not in OUTCOMES:
            raise ValueError("Outcome must be success, out_of_bounds, stalled, or quit")
        return value


class DatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    session_seed: int | None = None
    rows: list[Sample] = Field(min_length=1, max_length=100_000)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        result = value.strip()
        if not result:
            raise ValueError("Dataset name cannot be blank")
        return result


class TrainingRunCreate(BaseModel):
    preset: Literal["quick", "balanced", "explore"] = "quick"
    feature_transform: Literal[
        "absolute", "relative-center", "relative-containment"
    ] = "absolute"
    seed: int = Field(default=42, ge=0, le=2_147_483_647)
    drop_noop: bool = False


class EvaluationCreate(BaseModel):
    episodes: int = Field(default=20, ge=1, le=50)
    max_steps: int = Field(default=500, ge=1, le=2_000)
    seed: int = Field(default=42, ge=0, le=2_147_483_647)


class TrainingCancelled(Exception):
    """Raised at an epoch boundary after a cancellation request."""


S3_BUCKET = os.environ.get("BEHAVIOR_LAB_S3_BUCKET")
SERVICE_ENABLED = os.environ.get("BEHAVIOR_LAB_SERVICE_ENABLED", "true").lower() == "true"
COGNITO_USER_POOL_ID = os.environ.get("BEHAVIOR_LAB_COGNITO_USER_POOL_ID")
COGNITO_CLIENT_ID = os.environ.get("BEHAVIOR_LAB_COGNITO_CLIENT_ID")
COGNITO_DOMAIN = os.environ.get("BEHAVIOR_LAB_COGNITO_DOMAIN")
store = S3ObjectStore(S3_BUCKET, os.environ.get("AWS_REGION")) if S3_BUCKET else LocalObjectStore(DATA_ROOT)
job_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="behavior-training")
job_futures: dict[str, Future[None]] = {}
job_cancellations: dict[str, threading.Event] = {}
app = FastAPI(title="Behavior Lab API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def service_pause(request: Request, call_next: Any) -> Response:
    """Leave health and public bootstrap available while the pilot is paused."""
    if not SERVICE_ENABLED and request.url.path not in {"/health", "/api/v1/auth/config"}:
        return JSONResponse({"detail": "Behavior Lab is temporarily paused."}, status_code=503)
    return await call_next(request)


@app.on_event("startup")
def mark_interrupted_training_runs() -> None:
    """Make local jobs interrupted by an API restart visible to the learner."""
    if S3_BUCKET or os.environ.get("BEHAVIOR_LAB_TRAINING_QUEUE_URL"):
        return
    for record in store.list_json("projects"):
        if (
            record.get("record_type") == "training_run"
            and record.get("status") in {"queued", "running", "cancel_requested"}
        ):
            record["status"] = "failed"
            record["error_code"] = "worker_interrupted"
            record["error_message"] = "The local training worker stopped before this run completed. Retry the run."
            record["completed_at"] = utc_now()
            persist_run(record)


def project_key(project_id: str) -> str:
    if not re.fullmatch(r"[0-9a-f-]{36}", project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return f"projects/{project_id}/project.json"


def dataset_key(project_id: str, dataset_id: str) -> str:
    if not re.fullmatch(r"[0-9a-f-]{36}", dataset_id):
        raise HTTPException(status_code=404, detail="Dataset not found")
    return f"projects/{project_id}/datasets/{dataset_id}.json"


def find_record(record_type: str, record_id: str) -> tuple[str, dict[str, Any]] | None:
    directory_names = {
        "dataset": "datasets",
        "training_run": "training-runs",
        "evaluation": "evaluations",
    }
    if not re.fullmatch(r"[0-9a-f-]{36}", record_id):
        return None
    if isinstance(store, S3ObjectStore):
        directory = directory_names.get(record_type)
        if directory is None:
            return None
        index = store.get_json(f"indexes/{directory}/{record_id}.json")
        if index is None:
            return None
        metadata = store.get_json(index["object_key"])
        return (index["object_key"], metadata) if metadata else None
    directory = directory_names.get(record_type)
    if directory is None:
        return None
    for project in store.list_json("projects"):
        if project.get("record_type") != "project":
            continue
        prefix = f"projects/{project['id']}/{directory}"
        for record in store.list_json(prefix):
            if record.get("record_type") == record_type and record.get("id") == record_id:
                if record_type == "dataset":
                    return dataset_key(record["project_id"], record_id), record
                if record_type == "training_run":
                    return run_key(record["project_id"], record_id), record
                if record_type == "evaluation":
                    return evaluation_key(record["project_id"], record_id), record
    return None


def write_index(record_type: str, record_id: str, object_key: str) -> None:
    directories = {
        "project": "projects",
        "dataset": "datasets",
        "training_run": "training-runs",
        "evaluation": "evaluations",
    }
    directory = directories[record_type]
    store.put_json(
        f"indexes/{directory}/{record_id}.json",
        {"record_type": "index", "record_id": record_id, "object_key": object_key},
    )


def run_key(project_id: str, run_id: str) -> str:
    if not re.fullmatch(r"[0-9a-f-]{36}", run_id):
        raise HTTPException(status_code=404, detail="Training run not found")
    return f"projects/{project_id}/training-runs/{run_id}.json"


def evaluation_key(project_id: str, evaluation_id: str) -> str:
    if not re.fullmatch(r"[0-9a-f-]{36}", evaluation_id):
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return f"projects/{project_id}/evaluations/{evaluation_id}.json"


def persist_run(record: dict[str, Any]) -> None:
    record["updated_at"] = utc_now()
    store.put_json(run_key(record["project_id"], record["id"]), record)


def train_in_background(run_id: str, dataset: dict[str, Any], config: dict[str, Any]) -> None:
    """Run one CPU training job and persist status/progress as JSON metadata."""
    from util.data import DatasetError, load_demonstrations
    from util.training import save_artifact, train_policy, training_preset

    record = store.get_json(run_key(dataset["project_id"], run_id))
    if record is None or record.get("status") in {"completed", "failed", "cancelled"}:
        return
    cancellation = job_cancellations.setdefault(run_id, threading.Event())
    if cancellation.is_set() or record.get("status") == "cancel_requested":
        record["status"] = "cancelled"
        record["completed_at"] = utc_now()
        persist_run(record)
        return
    record["status"] = "running"
    record["started_at"] = utc_now()
    persist_run(record)

    try:
        csv_bytes = store.get_bytes(dataset["object_key"])
        if csv_bytes is None:
            raise DatasetError("The dataset CSV file is missing")
        with tempfile.TemporaryDirectory(prefix="behavior-lab-train-") as working_directory:
            working_path = Path(working_directory)
            dataset_path = working_path / "dataset.csv"
            dataset_path.write_bytes(csv_bytes)
            rows, _legacy = load_demonstrations(dataset_path)
            base = training_preset(config["preset"])
            training_config = replace(
                base,
                feature_transform=config["feature_transform"],
                seed=config["seed"],
            )
            record["progress"] = {
                "epoch": 0,
                "epochs_total": training_config.epochs,
                "train_loss": [],
                "validation_loss": [],
            }
            persist_run(record)

            def report_progress(epoch: int, train_loss: float, validation_loss: float) -> None:
                if cancellation.is_set():
                    raise TrainingCancelled
                latest = store.get_json(run_key(dataset["project_id"], run_id))
                if latest and latest.get("status") in {"cancel_requested", "cancelled"}:
                    raise TrainingCancelled
                record["progress"]["epoch"] = epoch
                record["progress"]["train_loss"].append(train_loss)
                record["progress"]["validation_loss"].append(validation_loss)
                persist_run(record)

            downsampler = None
            if config.get("drop_noop", False):
                from util.downsampling import load_downsampler

                downsampler = load_downsampler("drop-noop")
            result = train_policy(
                rows,
                training_config,
                progress=report_progress,
                downsampler=downsampler,
            )
            latest = store.get_json(run_key(dataset["project_id"], run_id))
            if cancellation.is_set() or (latest and latest.get("status") in {"cancel_requested", "cancelled"}):
                raise TrainingCancelled
            weights_path, metadata_path = save_artifact(result, working_path / "artifacts")
            weights_key = f"projects/{dataset['project_id']}/artifacts/{run_id}/{weights_path.name}"
            metadata_key = f"projects/{dataset['project_id']}/artifacts/{run_id}/{metadata_path.name}"
            store.put_bytes(weights_key, weights_path.read_bytes())
            store.put_bytes(metadata_key, metadata_path.read_bytes())
            record["status"] = "completed"
            record["weights_object_key"] = weights_key
            record["metadata_object_key"] = metadata_key
            record["experiment"] = json.loads(metadata_path.read_text(encoding="utf-8"))
            record["completed_at"] = utc_now()
            persist_run(record)
    except TrainingCancelled:
        latest = store.get_json(run_key(dataset["project_id"], run_id)) or record
        latest["status"] = "cancelled"
        latest["completed_at"] = utc_now()
        persist_run(latest)
    except Exception as error:
        LOGGER.exception("Training run %s failed", run_id)
        latest = store.get_json(run_key(dataset["project_id"], run_id)) or record
        latest["status"] = "failed"
        latest["error_code"] = "training_failed"
        latest["error_message"] = str(error)[:500]
        latest["completed_at"] = utc_now()
        persist_run(latest)
    finally:
        job_cancellations.pop(run_id, None)
        job_futures.pop(run_id, None)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/auth/config")
def auth_config() -> dict[str, Any]:
    """Return public Cognito client settings used by the browser bootstrap."""
    authentication_enabled = bool(
        COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID and COGNITO_DOMAIN
    )
    return {
        "authentication_enabled": authentication_enabled,
        "service_enabled": SERVICE_ENABLED,
        "user_pool_id": COGNITO_USER_POOL_ID,
        "client_id": COGNITO_CLIENT_ID,
        "domain": COGNITO_DOMAIN,
    }


@app.get("/api/v1/projects")
def list_projects() -> list[dict[str, Any]]:
    if isinstance(store, S3ObjectStore):
        projects = [
            project for index in store.list_json("indexes/projects")
            if (project := store.get_json(index["object_key"])) is not None
        ]
    else:
        projects = [record for record in store.list_json("projects") if record.get("record_type") == "project"]
    for project in projects:
        project["dataset_count"] = len(store.list_json(f"projects/{project['id']}/datasets"))
    return sorted(projects, key=lambda item: item["created_at"], reverse=True)


def enqueue_training_message(run_id: str) -> None:
    queue_url = os.environ.get("BEHAVIOR_LAB_TRAINING_QUEUE_URL")
    if not queue_url:
        raise RuntimeError("Training queue is not configured")
    import boto3

    boto3.client("sqs", region_name=os.environ.get("AWS_REGION")).send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps({"run_id": run_id}),
    )


@app.post("/api/v1/projects", status_code=201)
def create_project(payload: ProjectCreate) -> dict[str, Any]:
    project_id = str(uuid4())
    project = {
        "record_type": "project", "record_version": 1, "id": project_id,
        "name": payload.name, "created_at": utc_now(), "updated_at": utc_now(),
        "dataset_count": 0,
    }
    store.put_json(project_key(project_id), project)
    write_index("project", project_id, project_key(project_id))
    return project


@app.get("/api/v1/projects/{project_id}/datasets")
def list_datasets(project_id: str) -> list[dict[str, Any]]:
    project = store.get_json(project_key(project_id))
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    datasets = [record for record in store.list_json(f"projects/{project_id}/datasets") if record.get("record_type") == "dataset"]
    return sorted(datasets, key=lambda item: item["created_at"], reverse=True)


@app.post("/api/v1/projects/{project_id}/datasets", status_code=201)
def create_dataset(project_id: str, payload: DatasetCreate) -> dict[str, Any]:
    project = store.get_json(project_key(project_id))
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    episode_outcomes: dict[int, str] = {}
    no_ops = 0
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for row in payload.rows:
        if row.outcome != "quit":
            previous = episode_outcomes.setdefault(row.episode_id, row.outcome)
            if previous != row.outcome:
                raise HTTPException(status_code=422, detail="Rows from one episode must share an outcome")
        if row.action_x == 0 and row.action_y == 0:
            no_ops += 1
        writer.writerow(row.model_dump())
    if len(episode_outcomes) < 1:
        raise HTTPException(status_code=422, detail="Dataset must contain at least one completed episode")

    dataset_id = str(uuid4())
    object_prefix = f"projects/{project_id}/datasets/{dataset_id}"
    csv_key = f"{object_prefix}.csv"
    outcome_counts: dict[str, int] = {}
    for outcome in episode_outcomes.values():
        outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
    record = {
        "record_type": "dataset", "record_version": 1, "id": dataset_id,
        "project_id": project_id, "name": payload.name, "schema_version": SCHEMA_VERSION,
        "session_seed": payload.session_seed,
        "row_count": len(payload.rows), "episode_count": len(episode_outcomes),
        "outcomes": outcome_counts, "no_op_ratio": no_ops / len(payload.rows),
        "fingerprint": __import__("hashlib").sha256(buffer.getvalue().encode()).hexdigest(),
        "object_key": csv_key, "created_at": utc_now(),
    }
    store.put_bytes(csv_key, buffer.getvalue().encode("utf-8"), "text/csv; charset=utf-8")
    metadata_key = dataset_key(project_id, dataset_id)
    store.put_json(metadata_key, record)
    write_index("dataset", dataset_id, metadata_key)
    project["updated_at"] = utc_now()
    store.put_json(project_key(project_id), project)
    return record


def public_training_run(record: dict[str, Any]) -> dict[str, Any]:
    experiment = record.get("experiment") or {}
    metrics = experiment.get("metrics") or {}
    return {
        key: record.get(key)
        for key in (
            "id", "project_id", "dataset_id", "status", "preset", "config",
            "progress", "error_code", "error_message", "created_at", "started_at",
            "completed_at", "updated_at",
        )
    } | {
        "metrics": {
            "best_epoch": metrics.get("best_epoch"),
            "final_validation_loss": (
                metrics.get("validation_loss", [])[-1]
                if metrics.get("validation_loss") else None
            ),
        } if metrics else None,
    }


@app.get("/api/v1/projects/{project_id}/training-runs")
def list_training_runs(project_id: str) -> list[dict[str, Any]]:
    if store.get_json(project_key(project_id)) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    records = store.list_json(f"projects/{project_id}/training-runs")
    runs = [record for record in records if record.get("record_type") == "training_run"]
    return [public_training_run(record) for record in sorted(
        runs, key=lambda item: item["created_at"], reverse=True
    )]


@app.post("/api/v1/datasets/{dataset_id}/training-runs", status_code=202)
def create_training_run(dataset_id: str, payload: TrainingRunCreate) -> dict[str, Any]:
    found = find_record("dataset", dataset_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    _metadata_key, dataset = found
    csv_bytes = store.get_bytes(dataset["object_key"])
    if csv_bytes is None:
        raise HTTPException(status_code=404, detail="Dataset file not found")

    from util.data import DatasetError, load_demonstrations
    from util.domain import TrainingConfig

    try:
        with tempfile.TemporaryDirectory(prefix="behavior-lab-check-") as temporary_directory:
            dataset_path = Path(temporary_directory) / "dataset.csv"
            dataset_path.write_bytes(csv_bytes)
            rows, _legacy = load_demonstrations(dataset_path)
        episode_count = len({row.episode_id for row in rows})
        if episode_count < 2:
            raise HTTPException(
                status_code=422,
                detail="Training needs at least two completed episodes. Collect another episode and try again.",
            )
        from util.training import training_preset

        config = replace(
            training_preset(payload.preset),
            feature_transform=payload.feature_transform,
            seed=payload.seed,
        )
        config.validate()
    except DatasetError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    active_count = sum(
        run.get("status") in {"queued", "running", "cancel_requested"}
        for run in store.list_json("projects")
        if run.get("record_type") == "training_run"
    )
    if active_count >= 3:
        raise HTTPException(status_code=429, detail="The local training queue is full. Try again when a run finishes.")

    run_id = str(uuid4())
    run = {
        "record_type": "training_run", "record_version": 1,
        "id": run_id, "project_id": dataset["project_id"], "dataset_id": dataset_id,
        "status": "queued", "preset": payload.preset,
        "config": {
            "preset": payload.preset,
            "feature_transform": payload.feature_transform,
            "seed": payload.seed,
            "drop_noop": payload.drop_noop,
            "epochs": config.epochs,
        },
        "progress": {"epoch": 0, "epochs_total": config.epochs, "train_loss": [], "validation_loss": []},
        "created_at": utc_now(), "updated_at": utc_now(),
    }
    persist_run(run)
    write_index("training_run", run_id, run_key(run["project_id"], run_id))
    config = {
        "preset": payload.preset,
        "feature_transform": payload.feature_transform,
        "seed": payload.seed,
        "drop_noop": payload.drop_noop,
    }
    if os.environ.get("BEHAVIOR_LAB_TRAINING_QUEUE_URL"):
        try:
            enqueue_training_message(run_id)
        except Exception as error:
            LOGGER.exception("Could not enqueue training run %s", run_id)
            run["status"] = "failed"
            run["error_code"] = "queue_unavailable"
            run["error_message"] = "The training queue is unavailable. Please retry."
            run["completed_at"] = utc_now()
            persist_run(run)
            raise HTTPException(status_code=503, detail=run["error_message"]) from error
    else:
        job_cancellations[run_id] = threading.Event()
        job_futures[run_id] = job_executor.submit(train_in_background, run_id, dataset, config)
    return public_training_run(run)


@app.get("/api/v1/training-runs/{run_id}")
def get_training_run(run_id: str) -> dict[str, Any]:
    found = find_record("training_run", run_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Training run not found")
    return public_training_run(found[1])


@app.post("/api/v1/training-runs/{run_id}/cancel")
def cancel_training_run(run_id: str) -> dict[str, Any]:
    found = find_record("training_run", run_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Training run not found")
    key, record = found
    if record["status"] in {"queued", "running"} and os.environ.get("BEHAVIOR_LAB_TRAINING_QUEUE_URL"):
        record["status"] = "cancelled" if record["status"] == "queued" else "cancel_requested"
        if record["status"] == "cancelled":
            record["completed_at"] = utc_now()
        persist_run(record)
    elif record["status"] in {"queued", "running"}:
        cancellation = job_cancellations.get(run_id)
        if cancellation is not None:
            cancellation.set()
        future = job_futures.get(run_id)
        if future is not None and future.cancel():
            record["status"] = "cancelled"
            record["completed_at"] = utc_now()
            job_cancellations.pop(run_id, None)
        else:
            record["status"] = "cancel_requested"
        store.put_json(key, record)
    return public_training_run(record)


@app.get("/api/v1/projects/{project_id}/evaluations")
def list_evaluations(project_id: str) -> list[dict[str, Any]]:
    if store.get_json(project_key(project_id)) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    records = store.list_json(f"projects/{project_id}/evaluations")
    evaluations = [record for record in records if record.get("record_type") == "evaluation"]
    return [public_evaluation(item) for item in sorted(
        evaluations, key=lambda item: item["created_at"], reverse=True
    )]


@app.post("/api/v1/training-runs/{run_id}/evaluations", status_code=201)
def create_evaluation(run_id: str, payload: EvaluationCreate) -> dict[str, Any]:
    found = find_record("training_run", run_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Training run not found")
    run = found[1]
    if run.get("status") != "completed":
        raise HTTPException(status_code=409, detail="Evaluate a completed training run")
    metadata_key = run.get("metadata_object_key")
    weights_key = run.get("weights_object_key")
    metadata_bytes = store.get_bytes(metadata_key) if metadata_key else None
    weights_bytes = store.get_bytes(weights_key) if weights_key else None
    if metadata_bytes is None or weights_bytes is None:
        raise HTTPException(status_code=422, detail="The trained model artifact is unavailable")

    from util.domain import EvaluationConfig
    from util.evaluation import evaluate_policy, torch_policy
    from util.training import load_artifact

    evaluation_id = str(uuid4())
    trajectory_key = f"projects/{run['project_id']}/evaluation-artifacts/{evaluation_id}/trajectories.json"
    try:
        metadata = json.loads(metadata_bytes)
        weights_name = Path(str(metadata.get("weights_file", "weights.pth"))).name
        with tempfile.TemporaryDirectory(prefix="behavior-lab-evaluate-") as temporary_directory:
            metadata_path = Path(temporary_directory) / "metadata.json"
            metadata["weights_file"] = weights_name
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            (Path(temporary_directory) / weights_name).write_bytes(weights_bytes)
            artifact = load_artifact(metadata_path)
            result = evaluate_policy(
                torch_policy(artifact.model, artifact.feature_transform),
                EvaluationConfig(episodes=payload.episodes, max_steps=payload.max_steps, seed=payload.seed),
                policy_name=weights_name, experiment=run_id, capture_trajectory=True,
            )
    except (ValueError, KeyError, json.JSONDecodeError) as error:
        LOGGER.exception("Could not evaluate training run %s", run_id)
        raise HTTPException(status_code=422, detail="Could not load this model for evaluation") from error
    except Exception as error:
        LOGGER.exception("Evaluation failed for training run %s", run_id)
        raise HTTPException(status_code=500, detail="Evaluation failed. Please retry.") from error

    trajectories = {
        str(episode.episode_id): [
            {"blue_x": state.blue_x, "blue_y": state.blue_y,
             "target_x": state.target_x, "target_y": state.target_y}
            for state in episode.trajectory
        ]
        for episode in result.episodes
    }
    store.put_json(trajectory_key, trajectories)
    record = {
        "record_type": "evaluation", "record_version": 1, "id": evaluation_id,
        "project_id": run["project_id"], "training_run_id": run_id,
        "config": {"episodes": payload.episodes, "max_steps": payload.max_steps, "seed": payload.seed},
        "metrics": {
            "episodes": result.metrics.episodes, "successes": result.metrics.successes,
            "success_rate": result.metrics.success_rate,
            "mean_successful_steps": result.metrics.mean_successful_steps,
            "median_successful_steps": result.metrics.median_successful_steps,
            "stalled": result.metrics.stalled, "out_of_bounds": result.metrics.out_of_bounds,
        },
        "episodes": [
            {"episode_id": episode.episode_id, "outcome": episode.outcome.value, "steps": episode.steps}
            for episode in result.episodes
        ],
        "trajectory_object_key": trajectory_key, "created_at": utc_now(),
    }
    metadata_key = evaluation_key(run["project_id"], evaluation_id)
    store.put_json(metadata_key, record)
    write_index("evaluation", evaluation_id, metadata_key)
    return public_evaluation(record)


def public_evaluation(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key != "trajectory_object_key"}


@app.get("/api/v1/evaluations/{evaluation_id}")
def get_evaluation(evaluation_id: str) -> dict[str, Any]:
    found = find_record("evaluation", evaluation_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return public_evaluation(found[1])


@app.get("/api/v1/evaluations/{evaluation_id}/download")
def download_evaluation(evaluation_id: str) -> Response:
    found = find_record("evaluation", evaluation_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    content = json.dumps(public_evaluation(found[1]), indent=2).encode("utf-8")
    return Response(
        content, media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="evaluation-{evaluation_id}.json"'},
    )


@app.get("/api/v1/evaluations/{evaluation_id}/replay")
def get_evaluation_replay(evaluation_id: str, episode_id: int = 1) -> dict[str, Any]:
    found = find_record("evaluation", evaluation_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    record = found[1]
    episode = next((item for item in record["episodes"] if item["episode_id"] == episode_id), None)
    if episode is None:
        raise HTTPException(status_code=404, detail="Evaluation episode not found")
    trajectories = store.get_json(record["trajectory_object_key"])
    if trajectories is None or str(episode_id) not in trajectories:
        raise HTTPException(status_code=404, detail="Evaluation replay not found")
    return {"episode": episode, "frames": trajectories[str(episode_id)]}


@app.get("/api/v1/datasets/{dataset_id}/download")
def download_dataset(dataset_id: str) -> Response:
    found = find_record("dataset", dataset_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    record = found[1]
    content = store.get_bytes(record["object_key"])
    if content is None:
        raise HTTPException(status_code=404, detail="Dataset file not found")
    filename = re.sub(r"[^a-zA-Z0-9_-]+", "-", record["name"]).strip("-") or dataset_id
    return StreamingResponse(
        io.BytesIO(content), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
    )


@app.get("/api/v1/datasets/{dataset_id}/metrics")
def get_dataset_metrics(dataset_id: str) -> dict[str, Any]:
    found = find_record("dataset", dataset_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    content = store.get_bytes(found[1]["object_key"])
    if content is None:
        raise HTTPException(status_code=404, detail="Dataset file not found")

    action_counts: dict[str, int] = {}
    no_op_count = 0
    episode_outcomes: dict[str, str] = {}
    sample_count = 0
    for row in csv.DictReader(io.StringIO(content.decode("utf-8"))):
        sample_count += 1
        action_x = float(row["action_x"])
        action_y = float(row["action_y"])
        action = f"({action_x:g}, {action_y:g})"
        action_counts[action] = action_counts.get(action, 0) + 1
        if action_x == 0 and action_y == 0:
            no_op_count += 1
        episode_outcomes[row["episode_id"]] = row["outcome"]

    outcomes: dict[str, int] = {}
    for outcome in episode_outcomes.values():
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
    return {
        "samples": sample_count,
        "episodes": len(episode_outcomes),
        "no_op_ratio": no_op_count / sample_count if sample_count else 0,
        "outcomes": outcomes,
        "action_histogram": [
            {"action": action, "count": count}
            for action, count in sorted(action_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
    }
