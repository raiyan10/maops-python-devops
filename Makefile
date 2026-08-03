SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c

PYTHON ?= python3
VENV_DIR := .venv
VERSION := $(shell sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)
WHEEL_NAME := maops_pydevops-$(VERSION)-py3-none-any.whl

.PHONY: help venv install format format-check lint type-check test coverage build smoke-install quality release-check clean

help:
	@echo "Available targets:"
	@echo "  help           Show this help message"
	@echo "  venv           Create a local virtual environment in $(VENV_DIR)"
	@echo "  install        Install the project editable with the dev extra"
	@echo "  format         Apply Ruff formatting"
	@echo "  format-check   Check formatting without changing files"
	@echo "  lint           Run Ruff checks"
	@echo "  type-check     Run mypy in strict mode"
	@echo "  test           Run the pytest suite"
	@echo "  coverage       Run tests and enforce >=90% coverage"
	@echo "  build          Build the sdist and wheel"
	@echo "  smoke-install  Install the built wheel into an isolated venv and exercise the CLI"
	@echo "  quality        format-check + lint + type-check + coverage"
	@echo "  release-check  quality + build + smoke-install"
	@echo "  clean          Remove known generated build/test artifacts"

venv:
	$(PYTHON) -m venv $(VENV_DIR)

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e ".[dev]"

format:
	ruff format .

format-check:
	ruff format --check .

lint:
	ruff check .

type-check:
	mypy src

test:
	pytest

coverage:
	pytest --cov=maops_pydevops --cov-report=term-missing --cov-fail-under=90

build:
	rm -rf build dist src/maops_pydevops.egg-info
	$(PYTHON) -m build
	$(PYTHON) scripts/normalize_archive_permissions.py dist

smoke-install:
	$(PYTHON) scripts/verify_wheel.py dist $(WHEEL_NAME); \
	wheel="dist/$(WHEEL_NAME)"; \
	tmp_dir="$$(mktemp -d)"; \
	trap 'rm -rf -- "$$tmp_dir"' EXIT; \
	$(PYTHON) -m venv "$$tmp_dir/venv"; \
	PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_INDEX=1 "$$tmp_dir/venv/bin/python" -m pip install --no-deps -q "$$wheel"; \
	"$$tmp_dir/venv/bin/maops-py" --version; \
	"$$tmp_dir/venv/bin/maops-py" doctor; \
	"$$tmp_dir/venv/bin/maops-py" doctor --format json | "$$tmp_dir/venv/bin/python" -m json.tool >/dev/null; \
	"$$tmp_dir/venv/bin/python" -m maops_pydevops --version

quality: format-check lint type-check coverage

release-check: quality build smoke-install

clean:
	rm -rf dist build src/*.egg-info *.egg-info .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
