"""Opt-in smoke check using actual pretrained weights, never synthetic weights."""
from io import BytesIO

import numpy as np
from PIL import Image

from app.ml import ResNetEncoder

buffer = BytesIO()
Image.new('RGB', (300, 400), 'white').save(buffer, format='JPEG')
embedding = ResNetEncoder()(buffer.getvalue())
assert embedding.shape == (512,)
assert np.isfinite(embedding).all()
print('Pretrained ResNet18: 512 finite CPU features; frozen encoder smoke check passed.')
