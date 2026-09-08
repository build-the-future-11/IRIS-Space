PYTHON ?= python3

.PHONY: doctor format format-check lint typecheck test coverage compile build check

doctor:
	PYTHONPATH=src $(PYTHON) -m siderea doctor

format:
	$(PYTHON) -m ruff format src tests
	$(PYTHON) -m ruff check --fix src tests

format-check:
	$(PYTHON) -m ruff format --check src tests

lint:
	$(PYTHON) -m ruff check src tests

typecheck:
	$(PYTHON) -m mypy src/siderea

test:
	$(PYTHON) -m pytest -q

coverage:
	$(PYTHON) -m pytest -q --cov=siderea --cov-report=term-missing

compile:
	$(PYTHON) -m compileall -q src tests

build:
	$(PYTHON) -m build

check: format-check lint typecheck coverage compile
