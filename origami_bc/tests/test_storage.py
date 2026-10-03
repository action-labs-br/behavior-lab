import boto3
from moto import mock_aws
import pytest

from app.storage import BusyError, DynamoRepository, LocalRepository, S3Objects


def contract(repo):
    repo.put('sample#1', {'id':'1', 'probability':0.25})
    repo.put('sample#2', {'id':'2'})
    assert repo.get('sample#1')['probability'] == .25
    assert len(repo.list('sample#')) == 2
    token = repo.acquire('job')
    assert repo.owns('job',token)
    with pytest.raises(BusyError):
        repo.acquire('job')
    repo.release('job','wrong-token')
    assert repo.owns('job',token)
    repo.release('job',token)
    assert not repo.owns('job',token)
    repo.delete('sample#1')
    assert repo.get('sample#1') is None


def test_local(tmp_path):
    contract(LocalRepository(tmp_path, 'test'))


@mock_aws
def test_aws():
    region = 'us-east-1'
    boto3.client('dynamodb',region_name=region).create_table(
        TableName='test', KeySchema=[{'AttributeName':'pk','KeyType':'HASH'},{'AttributeName':'sk','KeyType':'RANGE'}],
        AttributeDefinitions=[{'AttributeName':'pk','AttributeType':'S'},{'AttributeName':'sk','AttributeType':'S'}],
        BillingMode='PAY_PER_REQUEST')
    contract(DynamoRepository('test','airplane',region))
    assert DynamoRepository('test','dog',region).list('sample#') == []
    boto3.client('s3',region_name=region).create_bucket(Bucket='origami-test')
    objects = S3Objects('origami-test',region)
    objects.put('samples/1',b'hello')
    assert objects.get('samples/1') == b'hello'
    with pytest.raises(ValueError):
        objects.get('samples/1',2)
    upload = objects.upload('uploads/1','image/png',1000)
    assert upload['fields']['key'] == 'uploads/1'
    objects.delete_prefix('samples/')
    assert 'Contents' not in objects.client.list_objects_v2(Bucket='origami-test')
