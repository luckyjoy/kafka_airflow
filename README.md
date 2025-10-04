
# Apache Airflow + Kafka ETL Pipeline ⚙️  
[![CI](https://github.com/luckyjoy/kafka_airflow/actions/workflows/ci.yml/badge.svg)](https://github.com/luckyjoy/kafka_airflow/actions/workflows/ci.yml)

A robust, production-minded **ETL** pipeline orchestrated by **Apache Airflow** and using **Apache Kafka** to decouple ingestion from processing. It simulates daily **User Sign‑up Events** flowing through **Producer → Kafka → Consumer → Staging (CSV) → Loader**, with strong error handling, idempotency, and a full developer/CI toolchain.

---

## ✨ Highlights
- **Docker Compose** stack for **Kafka + Airflow + Postgres** (`docker-compose.yml`)
- **Airflow DAG** with safe parse‑time behavior (no connection lookups at import)
- **Kafka utilities** using `confluent-kafka` (producer retries, consumer offset semantics)
- **Unit tests** (with fakes) + **coverage threshold** (**85%**) enforced in CI
- **Code quality**: Black + Flake8 in CI
- **Makefile** for one‑command dev flows
- **Containerized tests** via `docker-compose.test.yml`

---

## 🗂 Repository Layout
```
./
├─ docker-compose.yml              # Kafka + Airflow + Postgres stack
├─ docker-compose.test.yml         # Run tests in an Airflow container
├─ Makefile                        # dev, test, lint, fmt, up/down, etc.
├─ build.sh                        # local dev setup (venv, Airflow, conn)
├─ dags/
│  ├─ user_etl_dag.py             # Airflow DAG (templated bootstrap servers)
│  └─ kafka_utils.py              # Kafka producer/consumer utils
├─ tests/
│  ├─ test_kafka_utils.py         # base producer/consumer tests
│  ├─ test_kafka_utils_retry.py   # producer retry behavior
│  ├─ test_consumer_behaviors.py  # consumer edge cases
│  ├─ test_dag.py                 # import + structure
│  └─ test_dag_enhanced.py        # DAG props + templated args
├─ .github/workflows/ci.yml       # CI: lint + tests + coverage + compose validate
├─ .flake8                        # Flake8 rules
├─ pyproject.toml                 # Black config
├─ pytest.ini                     # pytest defaults
├─ logs/                          # Airflow logs (mounted)
├─ plugins/                       # Airflow plugins (optional)
└─ README.md
```

---

## 🧭 Architecture Diagram
```mermaid
flowchart LR
  subgraph Airflow
    A[Producer Task\n(PythonOperator)] -->|produce_user_data| K
    C[Consumer Task\n(PythonOperator)] -->|stages CSV| S[Staging File\n/tmp/kafka_staging_*.csv]
    L[Loader Task\n(PythonOperator)] --> D[(Data Warehouse\n(placeholder))]
    A --> C --> L --> X[Cleanup\n(BashOperator)]
  end

  K[(Kafka Topic\nuser_signups)]
  A -->|messages| K
  C <-->|poll/commit offsets| K
```

---

## 🚀 Quick Start

### Option A — Docker Compose (recommended)
Requirements: Docker Desktop (or Engine) and Compose v2.

```bash
docker compose up -d --build
# Airflow UI → http://localhost:8080  (admin / admin)
# Unpause DAG: robust_kafka_etl_pipeline
```

> The compose stack auto-installs `confluent-kafka` and creates an Airflow connection
> **`kafka_default`** with Extra `{ "bootstrap.servers": "kafka:9092" }`.

### Option B — Local dev via script
```bash
chmod +x build.sh
./build.sh                    # create venv + install Airflow (constraints) + deps
./build.sh --init-db          # airflow db migrate
./build.sh --create-admin     # admin/admin (idempotent)
./build.sh --add-kafka-conn   # adds kafka_default (bootstrap.servers)
./build.sh --start            # webserver :8080 + scheduler (background)
```

### Option C — Containerized tests only
```bash
make test-compose
# or
docker compose -f docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from tests
```

---

## ⚙️ Configuration
- **Kafka connection**: The DAG uses **templated** bootstrap servers to avoid `DagBag` failures at import:
  ```jinja
  {{ conn.kafka_default.extra_dejson['bootstrap.servers'] | default('kafka:9092', true) }}
  ```
  Ensure an Airflow connection with **Conn Id** `kafka_default` exists (Compose and `build.sh --add-kafka-conn` handle this for you).

- **Topic**: `user_signups` (auto-created in the Compose stack).
- **Batch size**: `NUM_RECORDS_TO_GENERATE` in `user_etl_dag.py` (default 50).
- **Staging output**: `/tmp/kafka_staging_<run_id>.csv` on the worker.

---

## 🧪 Testing
Local (venv):
```bash
make dev
source venv/bin/activate
make test         # pytest w/ coverage (85% threshold)
make lint         # black --check + flake8
```
Containerized:
```bash
make test-compose
```

**Coverage**: CI and `make test` enforce `--cov-fail-under=85`. Adjust in CI config and Makefile if needed.

---

## 🔄 CI/CD (GitHub Actions)
- **Location**: `.github/workflows/ci.yml`
- **Pipeline**:
  - Install Airflow with official constraints (Python 3.11)
  - Install `confluent-kafka` + Kafka provider
  - **Black** (check) + **Flake8** (style)
  - **pytest** with coverage (**85% minimum**), upload `coverage.xml`
  - Validate `docker-compose.yml` and `docker-compose.test.yml`

Badge:
```markdown
[![CI](https://github.com/luckyjoy/kafka_airflow/actions/workflows/ci.yml/badge.svg)](https://github.com/luckyjoy/kafka_airflow/actions/workflows/ci.yml)
```

---

## 🔍 Notable Implementation Details
- **Idempotent offsets**: Consumer commits offsets **only after** staging succeeds → safer retries.
- **Malformed messages**: Skipped and **offset committed** to prevent poison-pill loops.
- **Fast producer**: Single `flush()` after the batch (better throughput).
- **Parse-time safety**: No `BaseHook`/DB calls during DAG import.
- **Cleanup**: `all_done` trigger ensures staging files are removed even on failure.

---

## 🛠 Makefile Cheatsheet
```bash
make dev           # create venv + install deps (Airflow with constraints)
make test          # pytest w/ coverage (>=85%)
make lint          # black --check + flake8
make fmt           # black (auto-format)
make up            # docker compose up -d (full stack)
make down          # docker compose down -v
make logs          # tail logs from key services
make test-compose  # run tests in apache/airflow container
```

---

## 🧯 Troubleshooting
- **DAG import errors**: Ensure `dags/user_etl_dag.py` and `dags/kafka_utils.py` are co-located.
- **`confluent_kafka` missing**: Installed automatically in Compose; locally run `make dev`.
- **Topic missing**: Create it manually if auto-create is disabled:
  ```bash
  docker compose exec kafka kafka-topics.sh --bootstrap-server kafka:9092 \
    --create --topic user_signups --partitions 1 --replication-factor 1
  ```
- **Windows**: Prefer **WSL2** for Docker/paths; keep LF line endings in shell scripts.

---

## 📜 License
MIT (or your organization’s standard license)
