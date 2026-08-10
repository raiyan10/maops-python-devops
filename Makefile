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
	ruff format src tests

format-check:
	ruff format --check src tests

lint:
	ruff check src tests

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
	"$$tmp_dir/venv/bin/python" -m maops_pydevops --version; \
	smoke_home="$$tmp_dir/home"; mkdir -p "$$smoke_home"; \
	HOME="$$smoke_home" "$$tmp_dir/venv/bin/maops-py" config path; \
	smoke_bin="$$tmp_dir/fake-bin"; mkdir -p "$$smoke_bin"; \
	cp scripts/smoke/fake-git "$$smoke_bin/git"; chmod +x "$$smoke_bin/git"; \
	PATH="$$smoke_bin:$$PATH" HOME="$$smoke_home" "$$tmp_dir/venv/bin/maops-py" tools inspect git --format json | "$$tmp_dir/venv/bin/python" -m json.tool >/dev/null; \
	"$$tmp_dir/venv/bin/maops-py" inventory system --format json | "$$tmp_dir/venv/bin/python" -m json.tool >/dev/null; \
	smoke_fs="$$tmp_dir/fs-fixture"; \
	"$$tmp_dir/venv/bin/python" scripts/smoke/make-fixture-tree.py "$$smoke_fs"; \
	"$$tmp_dir/venv/bin/maops-py" inventory filesystem "$$smoke_fs" --max-depth 2 --top 3 --format json | "$$tmp_dir/venv/bin/python" -m json.tool >/dev/null; \
	smoke_log="$$tmp_dir/log-fixture.log"; \
	"$$tmp_dir/venv/bin/python" scripts/smoke/make-log-fixture.py "$$smoke_log"; \
	"$$tmp_dir/venv/bin/maops-py" logs parse "$$smoke_log" --input-format auto --format json | "$$tmp_dir/venv/bin/python" -m json.tool >/dev/null; \
	"$$tmp_dir/venv/bin/maops-py" logs analyze "$$smoke_log" --input-format auto --format json | "$$tmp_dir/venv/bin/python" -m json.tool >/dev/null; \
	"$$tmp_dir/venv/bin/maops-py" logs parse "$$smoke_log" --input-format auto --format json | "$$tmp_dir/venv/bin/python" -c 'import json,sys; d=json.dumps(json.load(sys.stdin)); assert "smoke-test-secret-do-not-use-1234567890" not in d, "synthetic secret leaked in logs parse output"'; \
	"$$tmp_dir/venv/bin/maops-py" logs analyze "$$smoke_log" --input-format auto --format json | "$$tmp_dir/venv/bin/python" -c 'import json,sys; d=json.dumps(json.load(sys.stdin)); assert "smoke-test-secret-do-not-use-1234567890" not in d, "synthetic secret leaked in logs analyze output"'; \
	"$$tmp_dir/venv/bin/python" scripts/smoke/health_smoke_check.py "$$tmp_dir/venv/bin/maops-py"; \
	smoke_doctor_json="$$tmp_dir/doctor-report.json"; \
	"$$tmp_dir/venv/bin/maops-py" doctor --format json > "$$smoke_doctor_json"; \
	smoke_inventory_json="$$tmp_dir/inventory-report.json"; \
	"$$tmp_dir/venv/bin/maops-py" inventory system --format json > "$$smoke_inventory_json"; \
	"$$tmp_dir/venv/bin/maops-py" report aggregate "$$smoke_doctor_json" "$$smoke_inventory_json" --format json | "$$tmp_dir/venv/bin/python" -m json.tool >/dev/null; \
	smoke_aggregate_md="$$tmp_dir/aggregate-report.md"; \
	"$$tmp_dir/venv/bin/maops-py" report aggregate "$$smoke_doctor_json" "$$smoke_inventory_json" --format markdown --output "$$smoke_aggregate_md"; \
	test -s "$$smoke_aggregate_md"; \
	"$$tmp_dir/venv/bin/python" scripts/smoke/workflow_smoke_check.py "$$tmp_dir/venv/bin/maops-py" "$$smoke_fs" "$$smoke_log"

quality: format-check lint type-check coverage

release-check: quality build smoke-install

clean:
	rm -rf dist build src/*.egg-info *.egg-info .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
