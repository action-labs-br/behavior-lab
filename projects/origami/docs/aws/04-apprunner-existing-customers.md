# 4. Optional deployment: existing App Runner customers

Use this instead of the ECS deployment only if your account is eligible. App Runner has been closed to new customers since April 30, 2026. See the [AWS notice](https://docs.aws.amazon.com/apprunner/latest/dg/apprunner-availability-change.html).

Complete guides 1–2 and the Docker build/push commands in guide 3. ECS roles from guide 2 are unnecessary if using only App Runner; you may skip their creation. Secret creation and generated JSON are still needed. Create App Runner-specific roles:

```bash
aws iam create-role --role-name "$APP_NAME-ecr" --assume-role-policy-document file://.deploy/trust-ecr.json
aws iam attach-role-policy --role-name "$APP_NAME-ecr" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess
aws iam create-role --role-name "$APP_NAME-runner" --assume-role-policy-document file://.deploy/trust-runner.json
aws iam put-role-policy --role-name "$APP_NAME-runner" --policy-name AppData --policy-document file://.deploy/app-policy.json
aws iam put-role-policy --role-name "$APP_NAME-runner" --policy-name AppSecrets --policy-document file://.deploy/secrets-policy.json
export AUTOSCALING_ARN=$(aws apprunner create-auto-scaling-configuration \
  --auto-scaling-configuration-name "$APP_NAME-single" --min-size 1 --max-size 1 \
  --max-concurrency 40 --query AutoScalingConfiguration.AutoScalingConfigurationArn --output text)
python3 scripts/aws_config.py
aws apprunner create-service --cli-input-json file://.deploy/apprunner-service.json \
  --auto-scaling-configuration-arn "$AUTOSCALING_ARN" > .deploy/apprunner-created.json
export RUNNER_ARN=$(python3 -c 'import json; print(json.load(open(".deploy/apprunner-created.json"))["Service"]["ServiceArn"])')
aws apprunner describe-service --service-arn "$RUNNER_ARN"
```

Wait for `RUNNING`, obtain `Service.ServiceUrl`, prepend `https://`, and follow the CORS and external-phone rehearsal instructions in guide 3. No VPC is needed for this route.

For an update, build/push a new immutable tag, export its `IMAGE_URI`, then:

```bash
python3 scripts/aws_config.py
python3 - <<'PY'
import json, os
from pathlib import Path
config = json.loads(Path('.deploy/apprunner-service.json').read_text())
Path('.deploy/runner-update.json').write_text(json.dumps({
    'ServiceArn':os.environ['RUNNER_ARN'], 'SourceConfiguration':config['SourceConfiguration']
}))
PY
aws apprunner update-service --cli-input-json file://.deploy/runner-update.json
aws apprunner describe-service --service-arn "$RUNNER_ARN"
```

References: [create-service](https://docs.aws.amazon.com/cli/latest/reference/apprunner/create-service.html), [runtime secrets](https://docs.aws.amazon.com/apprunner/latest/dg/env-variable-manage.html).
