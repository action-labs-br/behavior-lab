"""Provision the demo foundation with AWS CLI; resumable and secret-safe."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from datetime import datetime, timezone

parser = argparse.ArgumentParser()
parser.add_argument('--profile', default=os.environ.get('AWS_PROFILE', 'default'))
parser.add_argument('--region', default='us-east-1')
args = parser.parse_args()
os.umask(0o077)
out = Path('.deploy')
out.mkdir(exist_ok=True)
out.chmod(0o700)


def aws(*command: str, optional: bool = False) -> dict | list | None:
    result = subprocess.run(['aws', '--profile', args.profile, '--region', args.region,
                             '--no-cli-pager', *command, '--output', 'json'],
                            capture_output=True, text=True)
    if result.returncode:
        if optional and any(code in result.stderr for code in
                            ('NoSuchEntity', 'ResourceNotFoundException',
                             'RepositoryNotFoundException', 'NoSuchBucket', '(404)')):
            return None
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout) if result.stdout.strip() else {}


account = aws('sts', 'get-caller-identity')['Account']
name = 'origami-bc'
state_path = out / 'deployment.json'
state = json.loads(state_path.read_text()) if state_path.exists() else {}
if state and (state['account'] != account or state['region'] != args.region):
    raise RuntimeError('Deployment state belongs to a different account/region')
state.update(account=account, region=args.region, profile=args.profile, name=name,
             bucket=f'{name}-{account}-{args.region}', table=f'{name}-metadata')
state.setdefault('image_tag', datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
state['image_uri'] = f"{account}.dkr.ecr.{args.region}.amazonaws.com/{name}:{state['image_tag']}"


def save() -> None:
    state_path.write_text(json.dumps(state, indent=2) + '\n')


def render() -> None:
    env = {**os.environ, 'AWS_REGION':args.region, 'AWS_ACCOUNT_ID':account,
           'APP_NAME':name, 'S3_BUCKET':state['bucket'], 'DYNAMODB_TABLE':state['table'],
           'IMAGE_URI':state['image_uri']}
    for key, arn in state.get('secrets', {}).items():
        env[key + '_ARN'] = arn
    subprocess.run([sys.executable, 'scripts/aws_config.py'], env=env, check=True)


save()
print(f'Provisioning {name} in {account} / {args.region}', flush=True)
if aws('s3api', 'head-bucket', '--bucket', state['bucket'], optional=True) is None:
    command = ['s3api','create-bucket','--bucket',state['bucket']]
    if args.region != 'us-east-1':
        command += ['--create-bucket-configuration', f'LocationConstraint={args.region}']
    aws(*command)
aws('s3api','put-public-access-block','--bucket',state['bucket'],
    '--public-access-block-configuration','BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true')
aws('s3api','put-bucket-encryption','--bucket',state['bucket'],
    '--server-side-encryption-configuration',json.dumps({'Rules':[{'ApplyServerSideEncryptionByDefault':{'SSEAlgorithm':'AES256'}}]}))
print('Private encrypted S3 bucket ready', flush=True)
if aws('dynamodb','describe-table','--table-name',state['table'],optional=True) is None:
    aws('dynamodb','create-table','--table-name',state['table'],
        '--attribute-definitions','AttributeName=pk,AttributeType=S','AttributeName=sk,AttributeType=S',
        '--key-schema','AttributeName=pk,KeyType=HASH','AttributeName=sk,KeyType=RANGE',
        '--billing-mode','PAY_PER_REQUEST')
aws('dynamodb','wait','table-exists','--table-name',state['table'])
print('DynamoDB metadata table ready', flush=True)
if aws('ecr','describe-repositories','--repository-names',name,optional=True) is None:
    aws('ecr','create-repository','--repository-name',name,'--image-tag-mutability','IMMUTABLE',
        '--image-scanning-configuration','scanOnPush=true')
print('ECR repository ready', flush=True)
access_path = out / 'access.json'
access = json.loads(access_path.read_text()) if access_path.exists() else {
    'SESSION_SECRET':secrets.token_urlsafe(48),
    'EVENT_CODE':'ORIGAMI-' + secrets.token_hex(4).upper(),
    'ADMIN_PASSWORD':secrets.token_urlsafe(24),
}
access_path.write_text(json.dumps(access, indent=2) + '\n')
access_path.chmod(0o600)
state.setdefault('secrets', {})
for key, suffix in [('SESSION_SECRET','session'),('EVENT_CODE','event'),('ADMIN_PASSWORD','admin')]:
    secret_name = name + '/' + suffix
    found = aws('secretsmanager','describe-secret','--secret-id',secret_name,optional=True)
    if found:
        state['secrets'][key] = found['ARN']
    else:
        temporary = out / (key + '.secret')
        temporary.write_text(access[key])
        try:
            created = aws('secretsmanager','create-secret','--name',secret_name,
                          '--secret-string','file://' + str(temporary))
            state['secrets'][key] = created['ARN']
        finally:
            temporary.unlink(missing_ok=True)
    save()
render()
print('App secrets ready (values saved privately in .deploy/access.json)', flush=True)
roles = [('task','task'),('execution','task'),('infra','infra')]
for suffix, trust in roles:
    role_name = name + '-' + suffix
    if aws('iam','get-role','--role-name',role_name,optional=True) is None:
        aws('iam','create-role','--role-name',role_name,
            '--assume-role-policy-document','file://' + str(out / f'trust-{trust}.json'),
            '--tags','Key=Project,Value=origami-bc')
aws('iam','put-role-policy','--role-name',name+'-task','--policy-name','AppData',
    '--policy-document','file://' + str(out / 'app-policy.json'))
aws('iam','attach-role-policy','--role-name',name+'-execution',
    '--policy-arn','arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy')
aws('iam','put-role-policy','--role-name',name+'-execution','--policy-name','AppSecrets',
    '--policy-document','file://' + str(out / 'secrets-policy.json'))
aws('iam','attach-role-policy','--role-name',name+'-infra',
    '--policy-arn','arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices')
print('Separate task, execution, and infrastructure roles ready', flush=True)
aws('iam','put-role-policy','--role-name',name+'-infra','--policy-name','ExpressGatewaySupplement',
    '--policy-document','file://' + str(out / 'infra-extra-policy.json'))
clusters = aws('ecs','describe-clusters','--clusters',name)['clusters']
if not clusters:
    aws('ecs','create-cluster','--cluster-name',name,'--tags','key=Project,value=origami-bc')
print('ECS cluster ready; foundation provisioning complete', flush=True)
save()
