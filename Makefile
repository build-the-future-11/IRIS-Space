PYTHON ?= python3

.PHONY: doctor format format-check lint typecheck test coverage compile build check research-release-check

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

research-release-check:
	@test -n "$(RELEASE_OUTPUT)" || (echo 'Set RELEASE_OUTPUT to a new output directory' >&2; exit 2)
	PYTHON_BIN="$(PYTHON)" scripts/verify-research-release.sh "$(RELEASE_OUTPUT)"

.PHONY: paper-check paper-reconstruct
paper-check:
	$(PYTHON) -m ruff check paper/reconstruct.py paper/experiments/make_tables.py paper/experiments/run_transient_search.py paper/experiments/run_noise_stress.py paper/figures/make_figures.py
	$(PYTHON) -m pytest -q tests/test_paper_reconstruction.py tests/test_research_archives.py

paper-reconstruct:
	@test -n "$(PAPER_OUTPUT)" || (echo 'Set PAPER_OUTPUT to a new output directory' >&2; exit 2)
	PYTHONPATH=src $(PYTHON) paper/reconstruct.py --output "$(PAPER_OUTPUT)"
