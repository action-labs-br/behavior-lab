from io import BytesIO

from PIL import Image
import pytest

from app.config import ROOT, Settings, load_experiment
from app.ml import normalize_image


def test_config_and_production_secrets(monkeypatch):
    config = load_experiment(ROOT/'config/experiment.yaml')
    assert len(config['steps']) == 8
    assert len({s['action_id'] for s in config['steps']}) == 8
    monkeypatch.setenv('APP_ENV','production')
    with pytest.raises(ValueError,match='Production requires'):
        Settings.from_env()


def test_orientation_metadata_and_format():
    image = Image.new('RGB',(200,100))
    exif = image.getexif(); exif[274] = 6
    output = BytesIO(); image.save(output,format='JPEG',exif=exif)
    with Image.open(BytesIO(normalize_image(output.getvalue()))) as normalized:
        assert normalized.size == (100,200)
        assert not normalized.getexif()
    output = BytesIO(); image.save(output,format='GIF')
    with pytest.raises(ValueError,match='JPEG or PNG'):
        normalize_image(output.getvalue())
