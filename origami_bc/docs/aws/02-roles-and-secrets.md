# 2. IAM roles and secrets

Run after guide 1 in the same shell. `scripts/aws_config.py` creates policies scoped to this bucket, table, and the `airplane_01` experiment. When adding the dog experiment, extend the allowed prefixes/partition keys explicitly.

Create three separate ECS roles: the task accesses app data, the execution role pulls images and injects secrets, and the infrastructure role lets Express Mode manage its resources.

```bash
aws iam create-role --role-name "$APP_NAME-task" --assume-role-policy-document file://.deploy/trust-task.json
aws iam put-role-policy --role-name "$APP_NAME-task" --policy-name AppData --policy-document file://.deploy/app-policy.json
aws iam create-role --role-name "$APP_NAME-execution" --assume-role-policy-document file://.deploy/trust-task.json
aws iam attach-role-policy --role-name "$APP_NAME-execution" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
aws iam create-role --role-name "$APP_NAME-infra" --assume-role-policy-document file://.deploy/trust-infra.json
aws iam attach-role-policy --role-name "$APP_NAME-infra" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices
```

Create secrets without placing their values in shell history. Files are temporary and owner-readable only. The generated session signing key should remain stable across deployments. Choose a non-default event code and an admin password of at least 12 characters. The app receives plaintext values from Secrets Manager at container startup; it never stores these values in application metadata.

```bash
python3 - <<'PY'
import getpass
import os
from pathlib import Path
import secrets
os.umask(0o077)
values = {
    'SESSION_SECRET': secrets.token_urlsafe(48),
    'EVENT_CODE': getpass.getpass('Event code (not ORIGAMI42): '),
    'ADMIN_PASSWORD': getpass.getpass('Admin password (12+ characters): '),
}
assert values['EVENT_CODE'] and values['EVENT_CODE'] != 'ORIGAMI42'
assert len(values['ADMIN_PASSWORD']) >= 12
for key, value in values.items():
    Path('.deploy', key + '.secret').write_text(value)
PY
export SESSION_SECRET_ARN=$(aws secretsmanager create-secret --name "$APP_NAME/session" --secret-string file://.deploy/SESSION_SECRET.secret --query ARN --output text)
export EVENT_CODE_ARN=$(aws secretsmanager create-secret --name "$APP_NAME/event" --secret-string file://.deploy/EVENT_CODE.secret --query ARN --output text)
export ADMIN_PASSWORD_ARN=$(aws secretsmanager create-secret --name "$APP_NAME/admin" --secret-string file://.deploy/ADMIN_PASSWORD.secret --query ARN --output text)
python3 - <<'PY'
from pathlib import Path
for path in Path('.deploy').glob('*.secret'):
    path.unlink()
PY
python3 scripts/aws_config.py
aws iam put-role-policy --role-name "$APP_NAME-execution" --policy-name AppSecrets --policy-document file://.deploy/secrets-policy.json
```

Secrets use the account's default Secrets Manager encryption key. If you select a customer-managed KMS key, add scoped decrypt permissions. To resume in a new shell, restore the non-secret exports from guide 1, then retrieve ARNs by name:

```bash
export SESSION_SECRET_ARN=$(aws secretsmanager describe-secret --secret-id "$APP_NAME/session" --query ARN --output text)
export EVENT_CODE_ARN=$(aws secretsmanager describe-secret --secret-id "$APP_NAME/event" --query ARN --output text)
export ADMIN_PASSWORD_ARN=$(aws secretsmanager describe-secret --secret-id "$APP_NAME/admin" --query ARN --output text)
```

Continue with [ECS deployment](03-ecs-deployment.md), or [App Runner](04-apprunner-existing-customers.md) if available. Allow IAM changes to propagate before creating the service.

References: [Express Mode roles](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/express-service-getting-started.html), [ECS secrets](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/secrets-envvar-secrets-manager.html).
