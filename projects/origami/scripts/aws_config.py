"""Render deployment JSON from exported, non-secret environment variables."""
import json
import os
from pathlib import Path

out = Path('.deploy')
out.mkdir(exist_ok=True)
region = os.environ['AWS_REGION']
account = os.environ['AWS_ACCOUNT_ID']
name = os.environ.get('APP_NAME', 'origami-bc')
bucket = os.environ['S3_BUCKET']
table = os.environ['DYNAMODB_TABLE']
image = os.environ['IMAGE_URI']
role = lambda suffix: f'arn:aws:iam::{account}:role/{name}-{suffix}'


def save(name: str, value: dict) -> None:
    (out / name).write_text(json.dumps(value, indent=2) + '\n')


for suffix, service in [('task','ecs-tasks.amazonaws.com'), ('infra','ecs.amazonaws.com'),
                        ('runner','tasks.apprunner.amazonaws.com'), ('ecr','build.apprunner.amazonaws.com')]:
    save(f'trust-{suffix}.json', {'Version':'2012-10-17','Statement':[{
        'Effect':'Allow','Principal':{'Service':service},'Action':'sts:AssumeRole'}]})
task_trust = json.loads((out / 'trust-task.json').read_text())
task_trust['Statement'][0]['Condition'] = {
    'StringEquals': {'aws:SourceAccount': account},
    'ArnLike': {'aws:SourceArn': f'arn:aws:ecs:{region}:{account}:*'},
}
save('trust-task.json', task_trust)
save('infra-extra-policy.json', {'Version':'2012-10-17','Statement':[
    {'Effect':'Allow','Action':['ecs:DescribeServices','ecs:UpdateService'],
     'Resource':f'arn:aws:ecs:{region}:{account}:service/{name}/{name}'},
    {'Effect':'Allow','Action':['ec2:DescribeAccountAttributes','cloudwatch:DescribeAlarms'],
     'Resource':'*','Condition':{'StringEquals':{'aws:RequestedRegion':region}}}
]})
save('app-policy.json', {'Version':'2012-10-17','Statement':[
    {'Effect':'Allow','Action':['s3:ListBucket'],'Resource':f'arn:aws:s3:::{bucket}',
     'Condition':{'StringLike':{'s3:prefix':['experiments/airplane_01/*']}}},
    {'Effect':'Allow','Action':['s3:GetObject','s3:PutObject','s3:DeleteObject'],
     'Resource':f'arn:aws:s3:::{bucket}/experiments/airplane_01/*'},
    {'Effect':'Allow','Action':['dynamodb:GetItem','dynamodb:PutItem','dynamodb:DeleteItem','dynamodb:Query'],
     'Resource':f'arn:aws:dynamodb:{region}:{account}:table/{table}',
     'Condition':{'ForAllValues:StringEquals':{'dynamodb:LeadingKeys':['airplane_01']}, 'Null':{'dynamodb:LeadingKeys':'false'}}}
]})
secrets = {key: os.environ.get(key+'_ARN','') for key in ('SESSION_SECRET','EVENT_CODE','ADMIN_PASSWORD')}
if all(secrets.values()):
    save('secrets-policy.json', {'Version':'2012-10-17','Statement':[{
        'Effect':'Allow','Action':['secretsmanager:GetSecretValue'],'Resource':list(secrets.values())}]})
    environment = {'APP_ENV':'production','STORAGE_BACKEND':'aws','AWS_REGION':region,
                   'S3_BUCKET':bucket,'DYNAMODB_TABLE':table}
    save('ecs-service.json', {
        'serviceName':name, 'cluster':name,
        'executionRoleArn':role('execution'), 'infrastructureRoleArn':role('infra'),
        'taskRoleArn':role('task'), 'healthCheckPath':'/health',
        'cpu':'1024','memory':'4096','cpuArchitecture':'X86_64',
        'scalingTarget':{'minTaskCount':1,'maxTaskCount':1},
        'primaryContainer':{'image':image,'containerPort':8080,
            'environment':[{'name':key,'value':value} for key,value in environment.items()],
            'secrets':[{'name':key,'valueFrom':value} for key,value in secrets.items()]}})
    save('apprunner-service.json', {
        'ServiceName':name,
        'SourceConfiguration':{'AutoDeploymentsEnabled':False,
            'AuthenticationConfiguration':{'AccessRoleArn':role('ecr')},
            'ImageRepository':{'ImageIdentifier':image,'ImageRepositoryType':'ECR',
                'ImageConfiguration':{'Port':'8080','RuntimeEnvironmentVariables':environment,
                                      'RuntimeEnvironmentSecrets':secrets}}},
        'InstanceConfiguration':{'Cpu':'1 vCPU','Memory':'4 GB','InstanceRoleArn':role('runner')},
        'HealthCheckConfiguration':{'Protocol':'HTTP','Path':'/health','Interval':10,'Timeout':5,'HealthyThreshold':1,'UnhealthyThreshold':5}})
print('Deployment JSON written to .deploy (no secret values).')
