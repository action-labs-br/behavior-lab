# 5. Manual dataset cleanup and infrastructure teardown

Dataset retention is manual. In `/admin`, type `airplane_01` and click **Delete dataset and close collection**. This removes sample images and participant/run/sample records, closes collection, and retains trained models and their evaluation metadata for reuse. Repeat after five minutes to remove objects written by previously issued upload grants. No lifecycle rule silently deletes the dataset.

For full teardown, the following commands are destructive. Check account/region and resource names first. Remove the runtime before deleting its data and roles. Export the same variables used during provisioning and recover the service ARN from `.deploy` or the AWS console.

```bash
aws sts get-caller-identity
aws s3 ls "s3://$S3_BUCKET/"
```

For ECS, request removal and monitor until AWS reports it deleted:

```bash
aws ecs delete-express-gateway-service --service-arn "$SERVICE_ARN"
aws ecs monitor-express-gateway-service --service-arn "$SERVICE_ARN"
aws ecs delete-cluster --cluster "$APP_NAME"
```

For App Runner instead:

```bash
aws apprunner delete-service --service-arn "$RUNNER_ARN"
```

After service deletion completes, delete all data, including model artifacts, and registry images:

```bash
aws s3 rm "s3://$S3_BUCKET" --recursive
aws s3api delete-bucket --bucket "$S3_BUCKET"
aws dynamodb delete-table --table-name "$DYNAMODB_TABLE"
aws ecr delete-repository --repository-name "$APP_NAME" --force
aws secretsmanager delete-secret --secret-id "$APP_NAME/session" --recovery-window-in-days 7
aws secretsmanager delete-secret --secret-id "$APP_NAME/event" --recovery-window-in-days 7
aws secretsmanager delete-secret --secret-id "$APP_NAME/admin" --recovery-window-in-days 7
```

Remove only the roles for the runtime you created. ECS:

```bash
aws iam delete-role-policy --role-name "$APP_NAME-task" --policy-name AppData
aws iam delete-role --role-name "$APP_NAME-task"
aws iam delete-role-policy --role-name "$APP_NAME-execution" --policy-name AppSecrets
aws iam detach-role-policy --role-name "$APP_NAME-execution" --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
aws iam delete-role --role-name "$APP_NAME-execution"
aws iam detach-role-policy --role-name "$APP_NAME-infra" --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices
aws iam delete-role --role-name "$APP_NAME-infra"
```

App Runner:

```bash
aws iam delete-role-policy --role-name "$APP_NAME-runner" --policy-name AppData
aws iam delete-role-policy --role-name "$APP_NAME-runner" --policy-name AppSecrets
aws iam delete-role --role-name "$APP_NAME-runner"
aws iam detach-role-policy --role-name "$APP_NAME-ecr" --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess
aws iam delete-role --role-name "$APP_NAME-ecr"
aws apprunner delete-auto-scaling-configuration --auto-scaling-configuration-arn "$AUTOSCALING_ARN"
```

Inspect CloudWatch log groups and any remaining Express Mode resources in the console. Delete dedicated log groups by their actual names if no longer needed. A default VPC may be shared; leave it in place unless you have separately verified it is unused. Retained logs, secrets during their recovery window, or residual resources may have costs. These commands do not claim to remove unrelated/shared resources.

References: [ECS delete](https://docs.aws.amazon.com/cli/latest/reference/ecs/delete-express-gateway-service.html), [App Runner delete](https://docs.aws.amazon.com/cli/latest/reference/apprunner/delete-service.html).
