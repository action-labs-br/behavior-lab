# Redeploy after code changes

Run from the application folder. Wait until any training job has finished before replacing the task. The existing HTTPS URL, S3 photos/models, DynamoDB metadata, and Secrets Manager values are retained.

## 1. Test, build, and push

Use a new tag for every build; the ECR repository uses immutable tags. Stop if tests, build, or push fail.

```bash
cd /path/to/origami_bc
export AWS_PROFILE=$(python3 -c 'import json; print(json.load(open(".deploy/deployment.json"))["profile"])')
export AWS_REGION=$(python3 -c 'import json; print(json.load(open(".deploy/deployment.json"))["region"])')
export REGISTRY=$(python3 -c 'import json; s=json.load(open(".deploy/deployment.json")); print(s["account"]+".dkr.ecr."+s["region"]+".amazonaws.com")')
export APP_NAME=$(python3 -c 'import json; print(json.load(open(".deploy/deployment.json"))["name"])')
export IMAGE_URI="$REGISTRY/$APP_NAME:$(date -u +%Y%m%dT%H%M%SZ)"
export SERVICE_ARN=$(python3 -c 'import json; print(json.load(open(".deploy/deployment.json"))["service_arn"])')

.venv/bin/python -m pytest -q
aws ecr get-login-password | docker login --username AWS --password-stdin "$REGISTRY"
docker buildx build --platform linux/amd64 --load -t "$IMAGE_URI" .
docker push "$IMAGE_URI"
```

If your AWS session has expired, sign in again with the profile recorded in `AWS_PROFILE` before continuing.

## 2. Prepare the service update

The generated configuration retains the container port, environment variables, and secret ARNs. No secret values are written to the update file.

```bash
python3 - <<'PY'
import json
import os
from pathlib import Path

config = json.loads(Path('.deploy/ecs-service.json').read_text())
config['primaryContainer']['image'] = os.environ['IMAGE_URI']
Path('.deploy/ecs-update.json').write_text(json.dumps({
    'serviceArn': os.environ['SERVICE_ARN'],
    'primaryContainer': config['primaryContainer'],
}, indent=2))
PY
```

## 3. Deploy and monitor

```bash
aws ecs update-express-gateway-service --cli-input-json file://.deploy/ecs-update.json
aws ecs monitor-express-gateway-service --service-arn "$SERVICE_ARN"
```

Wait for deployment success before proceeding. ECS starts the new task, checks health, shifts traffic, and completes its monitoring period. Allow several minutes.

## 4. Verify and record the successful image

```bash
.venv/bin/python scripts/verify_deployment.py
```

The check verifies HTTPS, participant login, S3 upload/CORS, image normalization, DynamoDB writes, step advance, and admin access. It removes only its own synthetic records and images.

After deployment and verification succeed, update the local deployment records:

```bash
python3 - <<'PY'
import json
import os
from pathlib import Path

image = os.environ['IMAGE_URI']
path = Path('.deploy/deployment.json')
state = json.loads(path.read_text())
state['image_uri'] = image
state['image_tag'] = image.rsplit(':', 1)[1]
path.write_text(json.dumps(state, indent=2) + '\n')
path = Path('.deploy/ecs-service.json')
config = json.loads(path.read_text())
config['primaryContainer']['image'] = image
path.write_text(json.dumps(config, indent=2) + '\n')
PY
```

Open the `origin` URL from `.deploy/deployment.json` and refresh the page to load the new frontend assets.

## Troubleshooting and rollback

Inspect service events and logs:

```bash
aws ecs describe-services --cluster "$APP_NAME" --services "$APP_NAME"
export LOG_GROUP=$(python3 -c 'import json; print(json.load(open(".deploy/deployment.json"))["log_group"])')
aws logs tail "$LOG_GROUP" --since 10m
```

To redeploy an earlier image, set `IMAGE_URI` to its existing ECR URI and repeat steps 2–4. You do not need to rebuild or push it. Record the current working image URI before an update so it is available for rollback.

Changes to experiment steps/configuration can invalidate existing models and may require new IAM prefixes/partition keys and retraining. Changes to dependencies must be declared in `pyproject.toml` or the Dockerfile so they enter the image.

See [initial deployment](03-ecs-deployment.md), [environment details](06-deployed-environment.md), and [cleanup](05-cleanup.md).

Reference: [AWS ECS Express service updates](https://docs.aws.amazon.com/cli/latest/reference/ecs/update-express-gateway-service.html).
