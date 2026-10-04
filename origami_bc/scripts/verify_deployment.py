"""Verify the public app and remove only the synthetic records this check creates."""
from io import BytesIO
import json
from pathlib import Path
import subprocess
from uuid import uuid4

import httpx
from PIL import Image

state = json.loads(Path('.deploy/deployment.json').read_text())
access = json.loads(Path('.deploy/access.json').read_text())
base = state['origin']
participant_id = run_id = None
sample_ids = []


def aws(*command: str) -> None:
    result = subprocess.run(['aws','--profile',state['profile'],'--region',state['region'],
                             '--no-cli-pager',*command],capture_output=True,text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())


with httpx.Client(base_url=base, headers={'X-Origami-Request':'1'}, timeout=45) as client:
    def api(method: str, path: str, **kwargs) -> dict:
        response = client.request(method,path,**kwargs)
        response.raise_for_status()
        return response.json()

    assert api('GET','/health')['status'] == 'ok'
    for asset in ('/','/static/app.js','/static/i18n.js'):
        client.get(asset).raise_for_status()
    print('HTTPS, HTML, JavaScript, and translations respond',flush=True)
    assert client.get('/api/dataset/stats').status_code == 403
    assert client.post('/api/session/join',json={'display_name':'Check','event_code':'incorrect'}).status_code == 403
    try:
        participant_id = api('POST','/api/session/join',json={
            'display_name':'Deployment verification '+uuid4().hex[:6],
            'event_code':access['EVENT_CODE']})['id']
        run_id = api('POST','/api/runs')['id']
        image = Image.new('RGB',(300,400),'white')
        output = BytesIO(); image.save(output,format='PNG')

        def upload_state(index: int) -> str:
            created = api('POST','/api/samples',json={'run_id':run_id,'step_index':index,'content_type':'image/png'})
            sample_id = created['sample']['id']
            sample_ids.append(sample_id)
            fields = created['upload']['fields']
            url = created['upload']['url']
            # The browser will make this preflight; require the configured exact origin.
            preflight = httpx.options(url,headers={'Origin':base,'Access-Control-Request-Method':'POST'},timeout=30)
            assert preflight.headers.get('access-control-allow-origin') == base, 'S3 CORS mismatch'
            upload = httpx.post(url,data=fields,files={'file':('verification.png',output.getvalue(),'image/png')},headers={'Origin':base},timeout=30)
            if upload.is_error:
                raise RuntimeError(f'S3 upload failed: {upload.status_code} {upload.text[:500]}')
            assert api('POST',f'/api/samples/{sample_id}/complete')['status'] == 'READY'
            return sample_id

        first_sample_id = upload_state(0)
        assert api('POST',f'/api/runs/{run_id}/confirm/0')['stage'] == 'NEXT_PHOTO'
        upload_state(1)
        assert api('POST',f'/api/runs/{run_id}/advance/0')['step_index'] == 1
        print('Participant login, DynamoDB writes, S3 CORS/upload, decoding, and step advance passed',flush=True)
        api('POST','/api/admin/login',json={'password':access['ADMIN_PASSWORD']})
        assert api('GET','/api/dataset/stats')['samples'] >= 1
        photo = client.get(f'/api/samples/{first_sample_id}/image')
        photo.raise_for_status()
        assert Image.open(BytesIO(photo.content)).format == 'JPEG'
        print('Separate admin login, stats, and private normalized image retrieval passed',flush=True)
    finally:
        # Delete only data created by this check; leave participant datasets untouched.
        records = [('sample',sample_id) for sample_id in sample_ids] + [('run',run_id),('participant',participant_id)]
        for kind, identifier in records:
            if identifier:
                key={'pk':{'S':'airplane_01'},'sk':{'S':kind+'#'+identifier}}
                aws('dynamodb','delete-item','--table-name',state['table'],'--key',json.dumps(key))
        for sample_id in sample_ids:
            for key in [f'experiments/airplane_01/samples/{sample_id}.jpg',f'experiments/airplane_01/uploads/{sample_id}']:
                aws('s3api','delete-object','--bucket',state['bucket'],'--key',key)
        if participant_id:
            print('Synthetic verification records and images removed',flush=True)
