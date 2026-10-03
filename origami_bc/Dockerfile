FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 TORCH_HOME=/opt/torch
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir . && pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
RUN python -c "from torchvision.models import resnet18, ResNet18_Weights; resnet18(weights=ResNet18_Weights.IMAGENET1K_V1)"
COPY config ./config
RUN useradd --uid 10001 --create-home appuser && mkdir -p /app/.local && chown appuser /app/.local
USER appuser
EXPOSE 8080
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
