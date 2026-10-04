"""Web workflow and orchestration for a small presentation experiment."""
from collections import Counter
from datetime import datetime, timezone
from io import BytesIO
import json
import logging
import secrets
import threading
import time
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import joblib
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from app.config import ROOT, Settings, load_experiment
from app.ml import ENCODER, PREPROCESS, ResNetEncoder, fit_classifier, normalize_image
from app.storage import BusyError, DynamoRepository, LocalObjects, LocalRepository, S3Objects, locked

log = logging.getLogger("origami")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Join(BaseModel):
    display_name: str = Field(min_length=1, max_length=60)
    event_code: str = Field(max_length=200)


class Login(BaseModel):
    password: str = Field(max_length=200)


class SampleInput(BaseModel):
    run_id: str = Field(max_length=40)
    step_index: int = Field(ge=0, le=19)
    content_type: str


class TrainInput(BaseModel):
    holdout: list[str] | None = None


class Confirm(BaseModel):
    experiment_id: str


def create_app(settings: Settings | None = None, encoder=None) -> FastAPI:
    settings = settings or Settings.from_env()
    experiment = load_experiment(settings.config_path)
    repo = (DynamoRepository(settings.table, experiment["id"], settings.region)
            if settings.backend == "aws" else LocalRepository(settings.data_dir, experiment["id"]))
    objects = (S3Objects(settings.bucket, settings.region) if settings.backend == "aws"
               else LocalObjects(settings.data_dir))
    encoder = encoder or ResNetEncoder()
    app = FastAPI(title="Origami Behaviour Cloning")
    app.state.repo, app.state.objects = repo, objects
    app.add_middleware(SessionMiddleware, secret_key=settings.secret, https_only=settings.secure_cookie,
                       same_site="strict", max_age=12 * 3600)
    app.mount("/static", StaticFiles(directory=ROOT / "app/static"), name="static")
    templates = Jinja2Templates(directory=ROOT / "app/templates")
    prefix = f"experiments/{experiment['id']}/"
    cache = {}
    cache_lock = threading.Lock()

    @app.middleware("http")
    async def browser_boundary(request: Request, call_next):
        # A custom header forces cross-origin browsers to preflight; no CORS is enabled.
        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.headers.get("x-origami-request") != "1":
            return JSONResponse({"detail": "Missing request header"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' blob:; connect-src 'self' https://*.amazonaws.com; style-src 'self'; script-src 'self'; frame-ancestors 'none'"
        return response

    @app.exception_handler(BusyError)
    async def busy_handler(request, error):
        return JSONResponse({"detail": str(error)}, status_code=409)

    @app.exception_handler(ValueError)
    async def value_handler(request, error):
        return JSONResponse({"detail": str(error)}, status_code=400)

    def admin(request: Request) -> None:
        if not request.session.get("admin"):
            raise HTTPException(403, "Presenter login required")

    def participant(request: Request) -> dict:
        value = repo.get("participant#" + request.session.get("participant", ""))
        if not value:
            raise HTTPException(401, "Join the experiment first")
        return value

    def collecting() -> None:
        if (repo.get("control") or {}).get("closed"):
            raise HTTPException(409, "Collection is closed")

    def owned_run(request: Request, run_id: str) -> dict:
        owner = participant(request)
        run = repo.get("run#" + run_id)
        if not run or run["participant_id"] != owner["id"]:
            raise HTTPException(404, "Run not found")
        if run["fingerprint"] != experiment["fingerprint"]:
            raise HTTPException(409, "Instructions changed; start a new run")
        return run

    def owned_sample(request: Request, sample_id: str) -> dict:
        sample = repo.get("sample#" + sample_id)
        if not sample:
            raise HTTPException(404, "Sample not found")
        owned_run(request, sample["run_id"])
        return sample

    def run_stage(run: dict) -> str:
        if run.get("stage"):
            return run["stage"]
        sample = repo.get(f"sample#{run['id']}-{run['step_index']}")
        return "ACTION" if sample and sample["status"] == "READY" else "CURRENT_PHOTO"

    async def read_image(request: Request) -> bytes:
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > settings.max_upload:
                raise HTTPException(413, "Image exceeds 10 MiB; choose a smaller image")
            chunks.append(chunk)
        return b"".join(chunks)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    @app.get("/instructions", response_class=HTMLResponse)
    @app.get("/collect", response_class=HTMLResponse)
    @app.get("/complete", response_class=HTMLResponse)
    @app.get("/admin", response_class=HTMLResponse)
    @app.get("/admin/dataset", response_class=HTMLResponse)
    @app.get("/admin/train", response_class=HTMLResponse)
    @app.get("/admin/demo", response_class=HTMLResponse)
    def page(request: Request):
        return templates.TemplateResponse(request=request, name="index.html", context={"experiment": experiment})

    @app.get("/api/experiment")
    def get_experiment():
        return experiment

    @app.post("/api/session/join")
    def join(data: Join, request: Request):
        if not secrets.compare_digest(data.event_code.encode(), settings.event_code.encode()):
            raise HTTPException(403, "Incorrect event code")
        name = data.display_name.strip()
        if not name:
            raise ValueError("Enter a display name")
        with locked(repo, "dataset"):
            collecting()
            existing = repo.get("participant#" + request.session.get("participant", ""))
            value = existing or {"id": uuid4().hex, "display_name": name, "created_at": now()}
            repo.put("participant#" + value["id"], value)
            request.session["participant"] = value["id"]
        return value

    @app.post("/api/session/leave")
    def leave(request: Request):
        request.session.clear()
        return {"ok": True}

    @app.post("/api/admin/login")
    def login(data: Login, request: Request):
        if not secrets.compare_digest(data.password.encode(), settings.admin_password.encode()):
            raise HTTPException(403, "Incorrect password")
        request.session["admin"] = True
        return {"ok": True}

    @app.get("/api/session")
    def session(request: Request):
        return {"participant": repo.get("participant#" + request.session.get("participant", "")),
                "admin": bool(request.session.get("admin"))}

    @app.post("/api/runs")
    def start_run(request: Request):
        with locked(repo, "dataset"):
            collecting()
            owner = participant(request)
            # Resume an interrupted run, including after refreshing the browser.
            existing = [r for r in repo.list("run#") if r["participant_id"] == owner["id"]
                        and r["status"] == "ACTIVE" and r["fingerprint"] == experiment["fingerprint"]]
            if existing:
                return existing[0]
            run = {"id": uuid4().hex, "participant_id": owner["id"], "status": "ACTIVE",
                   "step_index": 0, "stage": "CURRENT_PHOTO", "created_at": now(),
                   "fingerprint": experiment["fingerprint"]}
            repo.put("run#" + run["id"], run)
            return run

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str, request: Request):
        run = owned_run(request, run_id)
        index = run["step_index"]
        return {**run, "stage": run_stage(run), "sample": repo.get(f"sample#{run_id}-{index}"),
                "next_sample": repo.get(f"sample#{run_id}-{index + 1}") if index + 1 < len(experiment["steps"]) else None}

    @app.post("/api/samples")
    def sample_create(data: SampleInput, request: Request):
        with locked(repo, "dataset"):
            collecting()
            run = owned_run(request, data.run_id)
            if run["status"] != "ACTIVE" or data.step_index < 0 or data.step_index >= len(experiment["steps"]):
                raise HTTPException(409, "There is no paper state to upload at this step")
            identifier = f"{run['id']}-{data.step_index}"
            sample = repo.get("sample#" + identifier)
            if sample and sample["status"] == "READY":
                return {"sample": sample, "upload": None}
            stage = run_stage(run)
            current_photo = data.step_index == run["step_index"] and stage == "CURRENT_PHOTO"
            next_photo = data.step_index == run["step_index"] + 1 and stage == "NEXT_PHOTO"
            if not (current_photo or next_photo):
                raise HTTPException(409, "Upload must match the current step")
            if data.content_type not in {"image/jpeg", "image/png"}:
                raise ValueError("Choose JPEG or PNG; convert HEIC before uploading")
            sample = {"id": identifier, "participant_id": run["participant_id"], "run_id": run["id"],
                      "step_index": data.step_index, "action_id": experiment["steps"][data.step_index]["action_id"],
                      "status": "PENDING_UPLOAD", "excluded": False, "created_at": now(),
                      "fingerprint": experiment["fingerprint"], "content_type": data.content_type,
                      "raw_key": prefix + "uploads/" + identifier,
                      "image_key": prefix + "samples/" + identifier + ".jpg"}
            repo.put("sample#" + identifier, sample)
            upload = (objects.upload(sample["raw_key"], data.content_type, settings.max_upload)
                      if settings.backend == "aws" else {"url": f"/api/samples/{identifier}/upload"})
            return {"sample": sample, "upload": upload}

    @app.put("/api/samples/{sample_id}/upload")
    async def local_upload(sample_id: str, request: Request):
        if settings.backend != "local":
            raise HTTPException(404)
        data = await read_image(request)
        with locked(repo, "dataset"):
            collecting()
            sample = owned_sample(request, sample_id)
            if sample["status"] == "READY":
                raise HTTPException(409, "Photo already confirmed")
            objects.put(sample["raw_key"], data)
        return {"ok": True}

    @app.post("/api/samples/{sample_id}/complete")
    def sample_complete(sample_id: str, request: Request):
        with locked(repo, "dataset"):
            collecting()
            sample = owned_sample(request, sample_id)
            if sample["status"] == "READY":
                return sample
            try:
                data = normalize_image(objects.get(sample["raw_key"], settings.max_upload))
            except Exception as error:
                sample["status"] = "FAILED"
                repo.put("sample#" + sample_id, sample)
                log.warning(json.dumps({"event": "upload_failed", "sample": sample_id}))
                raise ValueError("Upload missing or invalid; please retry with a JPEG/PNG under 10 MiB") from error
            objects.put(sample["image_key"], data, "image/jpeg")
            sample["status"] = "READY"
            repo.put("sample#" + sample_id, sample)
            objects.delete(sample["raw_key"])
            run = repo.get("run#" + sample["run_id"])
            if sample["step_index"] == run["step_index"] and run_stage(run) == "CURRENT_PHOTO":
                run["stage"] = "ACTION"
                repo.put("run#" + run["id"], run)
            return sample

    @app.post("/api/runs/{run_id}/confirm/{step_index}")
    def confirm_action(run_id: str, step_index: int, request: Request):
        with locked(repo, "dataset"):
            collecting()
            run = owned_run(request, run_id)
            if step_index < run["step_index"] or (run["status"] == "COMPLETE" and step_index == run["step_index"]):
                return run
            sample = repo.get(f"sample#{run_id}-{step_index}")
            if step_index != run["step_index"] or not sample or sample["status"] != "READY":
                raise HTTPException(409, "Upload the current paper state before performing this fold")
            if run_stage(run) not in {"ACTION", "NEXT_PHOTO"}:
                raise HTTPException(409, "Complete the current run step first")
            if step_index == len(experiment["steps"]) - 1:
                run.update(status="COMPLETE", completed_at=now())
            else:
                run["stage"] = "NEXT_PHOTO"
            repo.put("run#" + run_id, run)
            return run

    @app.post("/api/runs/{run_id}/advance/{step_index}")
    def advance(run_id: str, step_index: int, request: Request):
        with locked(repo, "dataset"):
            collecting()
            run = owned_run(request, run_id)
            if step_index < run["step_index"]:  # Safe retry after a lost response.
                return run
            sample = repo.get(f"sample#{run_id}-{step_index + 1}")
            if (step_index != run["step_index"] or run_stage(run) != "NEXT_PHOTO"
                    or not sample or sample["status"] != "READY"):
                raise HTTPException(409, "Upload the folded paper state before moving to the next fold")
            run["step_index"] += 1
            run["stage"] = "ACTION"
            repo.put("run#" + run_id, run)
            return run

    @app.get("/api/dataset/stats")
    def stats(request: Request):
        admin(request)
        samples = repo.list("sample#")
        ready = [s for s in samples if s["status"] == "READY" and not s["excluded"]]
        return {"participants": repo.list("participant#"), "runs": len(repo.list("run#")),
                "completed_runs": sum(r["status"] == "COMPLETE" for r in repo.list("run#")),
                "samples": len(ready), "counts": dict(Counter(s["action_id"] for s in ready)),
                "excluded": sum(s["excluded"] for s in samples), "control": repo.get("control") or {},
                "active": repo.get("active"), "fallback": repo.get("fallback")}

    @app.get("/api/samples")
    def samples(request: Request):
        admin(request)
        return repo.list("sample#")

    @app.get("/api/samples/{sample_id}/image")
    def sample_image(sample_id: str, request: Request):
        if request.session.get("admin"):
            sample = repo.get("sample#" + sample_id)
        else:
            sample = owned_sample(request, sample_id)
        if not sample or sample["status"] != "READY":
            raise HTTPException(404)
        return Response(objects.get(sample["image_key"]), media_type="image/jpeg")

    @app.post("/api/samples/{sample_id}/exclude")
    def exclude(sample_id: str, request: Request):
        admin(request)
        with locked(repo, "dataset"):
            sample = repo.get("sample#" + sample_id)
            if not sample:
                raise HTTPException(404)
            sample["excluded"] = not sample["excluded"]
            repo.put("sample#" + sample_id, sample)
        return sample

    def train_job(token: str, data: TrainInput, eligible: list[dict]):
        version = uuid4().hex
        def progress(done, total):
            if not repo.owns("operation", token):
                raise RuntimeError("Training lease expired; start training again")
            repo.put("training", {"status": "RUNNING", "done": done, "total": total,
                                  "token": token, "started_at": started, "expires": expires})
        started, expires = now(), time.time() + 900
        try:
            progress(0, len(eligible))
            artifact, metadata = fit_classifier(eligible, [s["action_id"] for s in experiment["steps"]],
                                               objects, encoder, data.holdout, settings.min_per_class, progress)
            metadata.update(id=version, created_at=now(), fingerprint=experiment["fingerprint"],
                            artifact_key=prefix + f"models/{version}.joblib")
            objects.put(metadata["artifact_key"], artifact)
            objects.put(prefix + f"models/{version}.json", json.dumps(metadata).encode(), "application/json")
            # Verify before publication; only our own private artifacts are deserialized.
            joblib.load(BytesIO(objects.get(metadata["artifact_key"])))
            if not repo.owns("operation", token):
                raise RuntimeError("Training lease expired before activation")
            repo.put("model#" + version, metadata)
            repo.put("active", {"id": version, "source": "live"})
            repo.put("training", {"status": "READY", "model": metadata})
            log.info(json.dumps({"event": "model_activated", "version": version}))
        except Exception as error:
            log.exception("Training failed")
            if repo.owns("operation", token):
                repo.put("training", {"status": "FAILED", "error": str(error)})
        finally:
            repo.release("operation", token)

    @app.post("/api/train", status_code=202)
    def train(data: TrainInput, request: Request, background: BackgroundTasks):
        admin(request)
        token = repo.acquire("operation")
        try:
            eligible = [s for s in repo.list("sample#") if s["status"] == "READY" and not s["excluded"]
                        and s["fingerprint"] == experiment["fingerprint"]]
            repo.put("training", {"status": "QUEUED", "token": token, "expires": time.time() + 900})
            background.add_task(train_job, token, data, eligible)
        except Exception:
            repo.release("operation", token)
            raise
        return {"status": "QUEUED"}

    @app.get("/api/train/status")
    def train_status(request: Request):
        admin(request)
        status = repo.get("training") or {"status": "IDLE"}
        if status["status"] in {"RUNNING", "QUEUED"} and not repo.owns("operation", status["token"]):
            return {"status": "FAILED", "error": "Training interrupted or exceeded 15 minutes; retry. Previous model retained."}
        return status

    @app.get("/api/models")
    def models(request: Request):
        admin(request)
        return repo.list("model#")

    @app.post("/api/models/{version}/{action}")
    def model_action(version: str, action: str, request: Request):
        admin(request)
        if action not in {"fallback", "activate"}:
            raise HTTPException(404)
        with locked(repo, "operation"):
            metadata = repo.get("model#" + version)
            if not metadata or metadata["fingerprint"] != experiment["fingerprint"]:
                raise ValueError("Model missing or incompatible with this experiment")
            joblib.load(BytesIO(objects.get(metadata["artifact_key"])))
            if action == "fallback":
                repo.put("fallback", {"id": version})
            else:
                source = "fallback" if (repo.get("fallback") or {}).get("id") == version else "live"
                repo.put("active", {"id": version, "source": source})
        return {"ok": True}

    @app.post("/api/predict")
    async def predict(request: Request):
        if not request.session.get("admin"):
            participant(request)
        data = normalize_image(await read_image(request))
        # Run CPU inference off the event loop to keep collection/health responsive.
        from starlette.concurrency import run_in_threadpool
        return await run_in_threadpool(predict_sync, data)

    def predict_sync(data: bytes) -> dict:
        pointer = repo.get("active")
        if not pointer:
            raise HTTPException(409, "Train or activate a model first")
        metadata = repo.get("model#" + pointer["id"])
        if not metadata or metadata["fingerprint"] != experiment["fingerprint"] or metadata["encoder"] != ENCODER or metadata["preprocessing"] != PREPROCESS:
            raise HTTPException(409, "Active model is incompatible; train again")
        with cache_lock:
            if cache.get("id") != pointer["id"]:
                cache.update(id=pointer["id"], classifier=joblib.load(BytesIO(objects.get(metadata["artifact_key"]))))
            classifier = cache["classifier"]
        probabilities = classifier.predict_proba([encoder(data)])[0]
        results = sorted([{"action_id": action, "probability": float(probability)}
                          for action, probability in zip(classifier.classes_, probabilities)],
                         key=lambda value: value["probability"], reverse=True)
        return {"model_version": pointer["id"], "source": pointer["source"], "prediction": results[0], "probabilities": results}

    @app.post("/api/admin/cleanup")
    def cleanup(data: Confirm, request: Request):
        admin(request)
        if data.experiment_id != experiment["id"]:
            raise ValueError("Type the experiment ID to confirm deletion")
        with locked(repo, "operation"), locked(repo, "dataset"):
            repo.put("control", {"closed": True})
            # Close collection first. Outstanding 5-minute upload grants can still write
            # to uploads/; repeat cleanup after expiry to remove any late objects.
            objects.delete_prefix(prefix + "samples/")
            objects.delete_prefix(prefix + "uploads/")
            for kind in ("sample", "run", "participant"):
                for record in repo.list(kind + "#"):
                    repo.delete(kind + "#" + record["id"])
        return {"ok": True, "message": "Collection closed and dataset deleted. Models retained. Repeat after 5 minutes to remove any late uploads."}

    @app.post("/api/admin/reopen")
    def reopen(request: Request):
        admin(request)
        with locked(repo, "dataset"):
            repo.put("control", {"closed": False})
        return {"ok": True}

    return app
