"""SQS-triggered Lambda handler for asynchronous model training."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any

import web.api.app as api

LOGGER = logging.getLogger("behavior_lab.worker")
MAX_TRAINING_SECONDS = 900


def _is_recently_started(run: dict[str, Any]) -> bool:
    started_at = run.get("started_at")
    if not started_at:
        return False
    try:
        started = datetime.fromisoformat(started_at)
    except ValueError:
        return False
    age_seconds = (datetime.now(timezone.utc) - started).total_seconds()
    return 0 <= age_seconds <= MAX_TRAINING_SECONDS


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    """Process each SQS run message and return only retryable message IDs."""
    failures = []
    for message in event.get("Records", []):
        message_id = message.get("messageId", "")
        try:
            body = json.loads(message["body"])
            run_id = body["run_id"]
            found = api.find_record("training_run", run_id)
            if found is None:
                raise ValueError("Training run metadata is missing")
            run = found[1]
            if run.get("status") in {"completed", "failed", "cancelled"}:
                continue
            if run.get("status") == "cancel_requested":
                run["status"] = "cancelled"
                run["completed_at"] = api.utc_now()
                api.persist_run(run)
                continue
            if run.get("status") == "running" and _is_recently_started(run):
                # SQS may deliver a duplicate while the original invocation is active.
                continue
            dataset_record = api.find_record("dataset", run["dataset_id"])
            if dataset_record is None:
                raise ValueError("Training dataset metadata is missing")
            api.job_cancellations[run_id] = threading.Event()
            api.train_in_background(
                run_id,
                dataset_record[1],
                {
                    "preset": run["preset"],
                    "feature_transform": run["config"]["feature_transform"],
                    "seed": run["config"]["seed"],
                    "drop_noop": run["config"].get("drop_noop", False),
                },
            )
        except Exception:
            LOGGER.exception("Training message %s failed", message_id)
            failures.append({"itemIdentifier": message_id})
    return {"batchItemFailures": failures}
