PYTHON ?= python3
VENV := .venv
VENV_PYTHON := $(VENV)/bin/python
UVICORN := $(VENV)/bin/uvicorn

.PHONY: run venv test deploy

venv:
	$(PYTHON) -m venv $(VENV)
	$(VENV_PYTHON) -m pip install -e '.[test]'
	$(VENV_PYTHON) -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
	@echo 'Virtual environment ready. Activate it with: source .venv/bin/activate'

run:
	TORCH_HOME="$(CURDIR)/.local/torch" PYTHONPATH=. $(UVICORN) app.main:create_app --factory --host 127.0.0.1 --port 8080

test:
	$(VENV_PYTHON) -m pytest -q
	node --check app/static/app.js

deploy: test
	bash scripts/deploy.sh
