#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f .deploy/deployment.json || ! -f .deploy/ecs-service.json || ! -f .deploy/ecs-created.json ]]; then
  echo 'Deployment state is missing. Follow docs/aws/01-foundation.md through docs/aws/03-ecs-deployment.md first.' >&2
  exit 1
fi

eval "$(.venv/bin/python - <<'PY'
import json
from pathlib import Path

state = json.loads(Path('.deploy/deployment.json').read_text())
service = json.loads(Path('.deploy/ecs-created.json').read_text())
values = {
    'AWS_PROFILE': state['profile'],
    'AWS_REGION': state['region'],
    'REGISTRY': f\"{state['account']}.dkr.ecr.{state['region']}.amazonaws.com\",
    'APP_NAME': state['name'],
    'SERVICE_ARN': service['service']['serviceArn'],
}
for key, value in values.items():
    import shlex
    print(f'export {key}={shlex.quote(value)}')
PY
)"

IMAGE_URI="$REGISTRY/$APP_NAME:$(date -u +%Y%m%dT%H%M%SZ)"
aws ecr get-login-password --region "$AWS_REGION" --profile "$AWS_PROFILE" \
  | docker login --username AWS --password-stdin "$REGISTRY"
docker buildx build --platform linux/amd64 --load -t "$IMAGE_URI" .
docker push "$IMAGE_URI"

export IMAGE_URI SERVICE_ARN
.venv/bin/python - <<'PY'
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

aws ecs update-express-gateway-service --region "$AWS_REGION" --profile "$AWS_PROFILE" \
  --cli-input-json file://.deploy/ecs-update.json
aws ecs monitor-express-gateway-service --region "$AWS_REGION" --profile "$AWS_PROFILE" \
  --service-arn "$SERVICE_ARN"
.venv/bin/python scripts/verify_deployment.py

.venv/bin/python - <<'PY'
import json
from pathlib import Path

image = Path('.deploy/ecs-update.json')
update = json.loads(image.read_text())
uri = update['primaryContainer']['image']
state_path = Path('.deploy/deployment.json')
state = json.loads(state_path.read_text())
state.update(image_uri=uri, image_tag=uri.rsplit(':', 1)[1])
state_path.write_text(json.dumps(state, indent=2) + '\n')
service_path = Path('.deploy/ecs-service.json')
service = json.loads(service_path.read_text())
service['primaryContainer']['image'] = uri
service_path.write_text(json.dumps(service, indent=2) + '\n')
PY

echo "Deployment verified: $IMAGE_URI"
