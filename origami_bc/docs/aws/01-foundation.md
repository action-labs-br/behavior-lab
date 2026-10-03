# 1. AWS foundation: private storage and image registry

Run these commands yourself from `origami_bc/`, in Bash. These guides create billable resources; nothing is provisioned merely by running the local app. Use a dedicated demo account or resource names. Commands are for a fresh deployment and are not generally idempotent. Keep the exported variables in the same shell through all guides. No custom domain is needed.

App Runner stopped accepting new customers on April 30, 2026. The default guide uses ECS Express Mode; the separate App Runner guide is only for eligible existing customers. [AWS availability notice](https://docs.aws.amazon.com/apprunner/latest/dg/apprunner-availability-change.html)

Prerequisites: current AWS CLI v2, an authenticated AWS profile with provisioning and IAM PassRole permissions, Python 3, Docker with buildx, and a selected AWS region that supports your runtime. The example uses the commercial AWS partition and `us-east-1`.

```bash
export AWS_PROFILE=your-demo-profile
export AWS_REGION=us-east-1
export AWS_PAGER=''
export APP_NAME=origami-bc
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export S3_BUCKET="${APP_NAME}-${AWS_ACCOUNT_ID}-${AWS_REGION}"
export DYNAMODB_TABLE="${APP_NAME}-metadata"
export IMAGE_TAG=v001
export IMAGE_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${APP_NAME}:${IMAGE_TAG}"
mkdir -p .deploy
chmod 700 .deploy
aws sts get-caller-identity
```

Create the bucket with the region-specific syntax:

```bash
if [ "$AWS_REGION" = us-east-1 ]; then
  aws s3api create-bucket --bucket "$S3_BUCKET"
else
  aws s3api create-bucket --bucket "$S3_BUCKET" \
    --create-bucket-configuration "LocationConstraint=$AWS_REGION"
fi
aws s3api put-public-access-block --bucket "$S3_BUCKET" \
  --public-access-block-configuration 'BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true'
aws s3api put-bucket-encryption --bucket "$S3_BUCKET" \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
```

Do not enable automatic dataset deletion or bucket versioning for this demo. Manual cleanup is the selected retention policy; deleting a versioned object would leave earlier versions behind.

The app uses one table. `pk` identifies the experiment, `sk` identifies a participant, run, sample, model, pointer, or operation lock. Payloads are JSON strings. No indexes, TTL, scans, or provisioned capacity are needed.

```bash
aws dynamodb create-table --table-name "$DYNAMODB_TABLE" \
  --attribute-definitions AttributeName=pk,AttributeType=S AttributeName=sk,AttributeType=S \
  --key-schema AttributeName=pk,KeyType=HASH AttributeName=sk,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST
aws dynamodb wait table-exists --table-name "$DYNAMODB_TABLE"
aws ecr create-repository --repository-name "$APP_NAME" \
  --image-tag-mutability IMMUTABLE \
  --image-scanning-configuration scanOnPush=true
python3 scripts/aws_config.py
```

Continue with [roles and secrets](02-roles-and-secrets.md).

References: [S3 create-bucket](https://docs.aws.amazon.com/cli/latest/reference/s3api/create-bucket.html), [DynamoDB create-table](https://docs.aws.amazon.com/cli/latest/reference/dynamodb/create-table.html), [ECR create-repository](https://docs.aws.amazon.com/cli/latest/reference/ecr/create-repository.html).
