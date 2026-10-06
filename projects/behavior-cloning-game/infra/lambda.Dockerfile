FROM public.ecr.aws/lambda/python:3.12

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/var/task \
    TORCH_HOME=/tmp/torch

COPY web/api/requirements-aws.txt ${LAMBDA_TASK_ROOT}/requirements-aws.txt
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements-aws.txt
RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    --extra-index-url https://pypi.org/simple \
    "torch==2.13.0+cpu"

COPY game/util ${LAMBDA_TASK_ROOT}/util
COPY game/downsamplers ${LAMBDA_TASK_ROOT}/downsamplers
COPY web/__init__.py ${LAMBDA_TASK_ROOT}/web/__init__.py
COPY web/api ${LAMBDA_TASK_ROOT}/web/api

CMD ["web.api.lambda_handler.handler"]
