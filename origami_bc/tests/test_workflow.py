from io import BytesIO

from fastapi.testclient import TestClient
import numpy as np
from PIL import Image
import pytest

from app.config import Settings
from app.main import create_app


def photo(color=(20, 80, 130)):
    buffer = BytesIO()
    Image.new('RGB', (80, 80), color).save(buffer, format='PNG')
    return buffer.getvalue()


def features(data):
    with Image.open(BytesIO(data)) as image:
        return np.array(image).mean(axis=(0, 1))


@pytest.fixture
def system(tmp_path):
    settings = Settings(data_dir=tmp_path, min_per_class=1)
    app = create_app(settings, encoder=features)
    client = TestClient(app, headers={'X-Origami-Request': '1'})
    return settings, app, client


def join(client, name='Alice'):
    response = client.post('/api/session/join', json={'display_name':name, 'event_code':'ORIGAMI42'})
    assert response.status_code == 200
    return response.json()['id']


def admin(client):
    assert client.post('/api/admin/login', json={'password':'local-admin'}).status_code == 200


def upload(client, run_id, index, data=None):
    response = client.post('/api/samples', json={'run_id':run_id, 'step_index':index, 'content_type':'image/png'})
    assert response.status_code == 200, response.text
    created = response.json()
    if created['upload']:
        assert client.put(created['upload']['url'], content=data or photo((index*25, 50, 150))).status_code == 200
    return client.post('/api/samples/'+created['sample']['id']+'/complete')


def complete_run(client):
    run = client.post('/api/runs').json()
    for index in range(8):
        assert upload(client, run['id'], index).status_code == 200
        response = client.post(f"/api/runs/{run['id']}/advance/{index}")
        assert response.status_code == 200
    assert response.json()['status'] == 'COMPLETE'
    return run


def test_order_ownership_retry_and_restart(system):
    settings, app, client = system
    join(client)
    run = client.post('/api/runs').json()
    assert client.post('/api/runs').json()['id'] == run['id']
    assert client.post(f"/api/runs/{run['id']}/advance/0").status_code == 409
    assert client.post('/api/samples', json={'run_id':run['id'], 'step_index':1, 'content_type':'image/png'}).status_code == 409
    assert upload(client, run['id'], 0, b'broken').status_code == 400
    assert upload(client, run['id'], 0).json()['action_id'] == 'crease_center'
    assert client.post(f"/api/runs/{run['id']}/advance/0").json()['step_index'] == 1
    assert client.post(f"/api/runs/{run['id']}/advance/0").json()['step_index'] == 1
    other = TestClient(app, headers={'X-Origami-Request':'1'})
    join(other, 'Bob')
    assert other.get('/api/runs/'+run['id']).status_code == 404
    restarted = TestClient(create_app(settings, encoder=features), headers={'X-Origami-Request':'1'})
    restarted.cookies.update(client.cookies)
    assert restarted.get('/api/runs/'+run['id']).json()['step_index'] == 1


def test_training_holdout_fallback_failure_cleanup(system):
    settings, app, client = system
    alice = join(client)
    complete_run(client)
    client.post('/api/session/leave')
    bob = join(client, 'Bob')
    complete_run(client)
    admin(client)
    assert client.post('/api/train', json={'holdout':[bob]}).status_code == 202
    status = client.get('/api/train/status').json()
    assert status['status'] == 'READY', status
    model = status['model']
    assert model['training_participants'] == [alice]
    assert model['test_participants'] == [bob]
    assert model['training_samples'] == 8
    assert len(model['confusion_matrix']) == 8
    version = model['id']
    assert client.post(f'/api/models/{version}/fallback').status_code == 200
    assert client.post(f'/api/models/{version}/activate').status_code == 200
    prediction = client.post('/api/predict', content=photo()).json()
    assert len(prediction['probabilities']) == 8
    assert sum(item['probability'] for item in prediction['probabilities']) == pytest.approx(1)
    assert prediction['source'] == 'fallback'
    assert client.post('/api/train', json={'holdout':[alice,bob]}).status_code == 202
    assert client.get('/api/train/status').json()['status'] == 'FAILED'
    assert client.get('/api/dataset/stats').json()['active']['id'] == version
    restarted = TestClient(create_app(settings, encoder=features), headers={'X-Origami-Request':'1'})
    admin(restarted)
    assert restarted.post('/api/predict', content=photo()).json()['model_version'] == version
    assert client.post('/api/admin/cleanup', json={'experiment_id':'wrong'}).status_code == 400
    assert client.post('/api/admin/cleanup', json={'experiment_id':'airplane_01'}).status_code == 200
    stats = client.get('/api/dataset/stats').json()
    assert stats['samples'] == 0 and stats['participants'] == []
    assert stats['active']['id'] == version
    assert client.post('/api/runs').status_code == 409
    assert not list((settings.data_dir/'objects/experiments/airplane_01/samples').glob('*.jpg'))


def test_boundaries_and_exclusion(system):
    settings, app, client = system
    assert TestClient(app).post('/api/session/join',json={}).status_code == 403
    assert client.get('/api/samples').status_code == 403
    assert client.post('/api/train',json={}).status_code == 403
    assert client.post('/api/session/join',json={'display_name':'Alice','event_code':'wrong'}).status_code == 403
    join(client)
    run = complete_run(client)
    admin(client)
    client.post(f"/api/samples/{run['id']}-0/exclude")
    client.post('/api/train',json={'holdout':[]})
    assert 'crease_center' in client.get('/api/train/status').json()['error']
    settings.max_upload = 10
    assert client.post('/api/predict', content=b'x'*11).status_code == 413


def test_expired_training_reports_failure(system):
    _, app, client = system
    admin(client)
    app.state.repo.put('training', {'status':'RUNNING','token':'stale'})
    assert client.get('/api/train/status').json()['status'] == 'FAILED'
