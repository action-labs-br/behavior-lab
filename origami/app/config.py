"""Explicit configuration; development and cloud use the same experiment."""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    backend: str = "local"
    data_dir: Path = ROOT / ".local"
    config_path: Path = ROOT / "config/experiment.yaml"
    secret: str = "local-only-change-before-hosting-32-characters"
    event_code: str = "ORIGAMI42"
    admin_password: str = "local-admin"
    secure_cookie: bool = False
    bucket: str = ""
    table: str = ""
    region: str = "us-east-1"
    max_upload: int = 10 * 1024 * 1024
    min_per_class: int = 2

    @classmethod
    def from_env(cls) -> "Settings":
        production = os.getenv("APP_ENV") == "production"
        settings = cls(
            backend=os.getenv("STORAGE_BACKEND", "local"),
            data_dir=Path(os.getenv("DATA_DIR", str(ROOT / ".local"))),
            config_path=Path(os.getenv("EXPERIMENT_CONFIG", str(ROOT / "config/experiment.yaml"))),
            secret=os.getenv("SESSION_SECRET", cls.secret),
            event_code=os.getenv("EVENT_CODE", cls.event_code),
            admin_password=os.getenv("ADMIN_PASSWORD", cls.admin_password),
            secure_cookie=production,
            bucket=os.getenv("S3_BUCKET", ""),
            table=os.getenv("DYNAMODB_TABLE", ""),
            region=os.getenv("AWS_REGION", "us-east-1"),
        )
        if settings.backend not in {"local", "aws"}:
            raise ValueError("STORAGE_BACKEND must be local or aws")
        if production and (
            settings.backend != "aws" or len(settings.secret) < 32
            or settings.secret == cls.secret or settings.event_code == cls.event_code
            or settings.admin_password == cls.admin_password or len(settings.admin_password) < 12
        ):
            raise ValueError("Production requires AWS storage and non-default secrets (admin >=12, session >=32 characters)")
        if settings.backend == "aws" and not (settings.bucket and settings.table):
            raise ValueError("AWS storage requires S3_BUCKET and DYNAMODB_TABLE")
        return settings


def load_experiment(path: Path) -> dict:
    document = yaml.safe_load(path.read_text())
    experiment = document["experiment"]
    steps = document["steps"]
    identifiers = [step["action_id"] for step in steps]
    if not 2 <= len(steps) <= 20 or len(set(identifiers)) != len(steps):
        raise ValueError("Use 2-20 steps with unique action IDs")
    for identifier in [experiment["id"], *identifiers]:
        if not re.fullmatch(r"[a-z0-9_\-]+", identifier):
            raise ValueError("Invalid experiment/action identifier")
    for index, step in enumerate(steps):
        if not step.get("title") or not step.get("instruction"):
            raise ValueError("Every step needs a title and instruction")
        step["index"] = index
    return {**experiment, "steps": steps, "fingerprint": hashlib.sha256(path.read_bytes()).hexdigest()}
