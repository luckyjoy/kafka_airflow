
SHELL := /bin/bash
PYTHON_BIN ?= python3
VENV_DIR ?= venv
AIRFLOW_VERSION ?= 2.9.1
PY_MINOR := $(shell $(PYTHON_BIN) -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo 3.11)
CONSTRAINTS_URL := https://raw.githubusercontent.com/apache/airflow/constraints-$(AIRFLOW_VERSION)/constraints-$(PY_MINOR).txt
EXTRA_PKGS ?= confluent-kafka==2.4.0 apache-airflow-providers-apache-kafka==5.2.0 pytest pytest-cov black==24.8.0 flake8==7.1.0

.PHONY: help dev install test cov lint fmt up down ps logs test-compose clean

help:
	@echo "Targets:"
	@echo "  dev            Create venv and install Airflow (with constraints) + dev deps"
	@echo "  install        Install only dev deps into current env"
	@echo "  test           Run pytest with coverage (fail under 85%)"
	@echo "  cov            Same as test (prints coverage)"
	@echo "  lint           Run Black (check) + Flake8"
	@echo "  fmt            Run Black auto-format"
	@echo "  up             docker compose up -d"
	@echo "  down           docker compose down"
	@echo "  ps             docker compose ps"
	@echo "  logs           docker compose logs -f airflow-webserver airflow-scheduler kafka postgres"
	@echo "  test-compose   Run tests in container (docker-compose.test.yml)"
	@echo "  clean          Remove venv and caches"

$(VENV_DIR)/bin/activate:
	$(PYTHON_BIN) -m venv $(VENV_DIR)
	. $(VENV_DIR)/bin/activate; pip install --upgrade pip setuptools wheel
	. $(VENV_DIR)/bin/activate; pip install "apache-airflow==$(AIRFLOW_VERSION)" --constraint "$(CONSTRAINTS_URL)"
	. $(VENV_DIR)/bin/activate; pip install $(EXTRA_PKGS)

dev: $(VENV_DIR)/bin/activate
	@echo "Dev environment ready. Activate with: source $(VENV_DIR)/bin/activate"

install:
	pip install -U pip
	pip install $(EXTRA_PKGS)

test:
	pytest --cov=dags --cov=tests --cov-report=term-missing --cov-fail-under=85

cov: test

lint:
	black --check .
	flake8 .

fmt:
	black .

up:
	docker compose up -d --build

down:
	docker compose down -v

ps:
	docker compose ps

logs:
	docker compose logs -f airflow-webserver airflow-scheduler kafka postgres

test-compose:
	docker compose -f docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from tests
	docker compose -f docker-compose.test.yml down -v

clean:
	rm -rf $(VENV_DIR) .pytest_cache __pycache__ */__pycache__ .mypy_cache coverage.xml
