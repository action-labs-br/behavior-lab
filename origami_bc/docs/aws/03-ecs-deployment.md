# 3. Build and deploy with ECS Express Mode

Run after guides 1–2. This is the alternative for accounts without App Runner access. Express Mode manages Fargate, a load balancer, TLS, and related resources. Those resources incur charges while deployed, even between talks. This guide intentionally starts with one task; 20 participants is a rehearsal target, not a verified capacity claim.

The Docker build downloads the pretrained encoder weights into the image. Deployment has no runtime model-download dependency. Use a new immutable ECR tag for each build. This command builds for the architecture selected in the generated ECS configuration:

```bash
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
docker buildx build --platform linux/amd64 --load -t "$IMAGE_URI" .
docker push "$IMAGE_URI"
```

Verify your CLI supports Express Mode and inspect the default VPC. Express Mode's default networking requires a default VPC with public subnets. If none exists, use the optional creation command, or supply suitable existing subnet IDs in `networkConfiguration` in the generated JSON.

```bash
aws ecs create-express-gateway-service help
aws ec2 describe-vpcs --filters Name=is-default,Values=true --query 'Vpcs[].VpcId'
aws ec2 describe-subnets --filters Name=default-for-az,Values=true --query 'Subnets[].{ID:SubnetId,VPC:VpcId,AZ:AvailabilityZone}'
```

Only if the account has no default VPC and you want AWS to create one:

```bash
aws ec2 create-default-vpc
```

Create and monitor the service. The file sets 1024 CPU units, 4096 MiB, port 8080, and `/health`. It contains secret ARNs, never secret values.

```bash
aws ecs create-cluster --cluster-name "$APP_NAME"
python3 scripts/aws_config.py
aws ecs create-express-gateway-service --cli-input-json file://.deploy/ecs-service.json > .deploy/ecs-created.json
export SERVICE_ARN=$(python3 -c 'import json; print(json.load(open(".deploy/ecs-created.json"))["service"]["serviceArn"])')
aws ecs monitor-express-gateway-service --service-arn "$SERVICE_ARN"
aws ecs describe-express-gateway-service --service-arn "$SERVICE_ARN"
```

Copy the HTTPS application URL returned by AWS. Set its exact origin, without a trailing slash, for the S3 browser upload policy:

```bash
export APP_ORIGIN=https://YOUR-ACTUAL-SERVICE-URL
python3 - <<'PY'
import json, os
from pathlib import Path
Path('.deploy/cors.json').write_text(json.dumps({'CORSRules':[{
    'AllowedOrigins':[os.environ['APP_ORIGIN']],
    'AllowedMethods':['POST'], 'AllowedHeaders':['*'], 'MaxAgeSeconds':300
}]}))
PY
aws s3api put-bucket-cors --bucket "$S3_BUCKET" --cors-configuration file://.deploy/cors.json
curl --fail "$APP_ORIGIN/health"
```

Open the URL on an external phone, join with the event code, and finish all eight steps. Then open `/admin`, train with several demonstrations, and check a held-out participant. Rehearse a known-good model and mark it as fallback. Test a restart/redeployment and verify dataset and model recovery. No fallback is bundled; it must be trained from real demonstration photos.

For an update, set a new `IMAGE_TAG` and `IMAGE_URI`, rebuild/push, regenerate configuration, then:

```bash
python3 scripts/aws_config.py
python3 - <<'PY'
import json, os
from pathlib import Path
config = json.loads(Path('.deploy/ecs-service.json').read_text())
Path('.deploy/ecs-update.json').write_text(json.dumps({
    'serviceArn':os.environ['SERVICE_ARN'], 'primaryContainer':config['primaryContainer']
}))
PY
aws ecs update-express-gateway-service --cli-input-json file://.deploy/ecs-update.json
aws ecs monitor-express-gateway-service --service-arn "$SERVICE_ARN"
```

Do not deploy while training: background training is process-local. If the task is replaced mid-job, its 15-minute lease expires and the presenter can retry; the previous model stays active. Logs are available through the service's CloudWatch links in the AWS console.

References: [Express Mode getting started](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/express-service-getting-started.html), [create-service parameters](https://docs.aws.amazon.com/cli/latest/reference/ecs/create-express-gateway-service.html), [update-service parameters](https://docs.aws.amazon.com/cli/latest/reference/ecs/update-express-gateway-service.html).
