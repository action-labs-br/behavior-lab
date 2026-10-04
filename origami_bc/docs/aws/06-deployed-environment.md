# Deployment environment

Account-specific deployment details are kept in the ignored `.deploy/deployment.json`, including the profile, region, resource names, image URI, service ARN, and HTTPS origin. App credentials are kept in the ignored, owner-readable `.deploy/access.json`. Do not commit either file.

To display non-secret deployment details locally:

```bash
python3 -m json.tool .deploy/deployment.json
```

The participant page is at the recorded `origin`; the admin page is at `origin` followed by `/admin`. Cloud data starts empty unless demonstrations have been collected there. Local photos and models are not copied automatically.

Follow the [redeployment guide](07-redeployment.md) for code changes and [cleanup guide](05-cleanup.md) for teardown. Fargate and the managed load balancer remain billable while deployed.

## Validation

```bash
.venv/bin/python scripts/verify_deployment.py
```

This checks HTTPS, participant login, S3 upload/CORS, image normalization, DynamoDB writes, step advance, and admin access, then removes only the synthetic records and images it created.
