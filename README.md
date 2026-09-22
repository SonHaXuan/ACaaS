# ACaaS — Access Control as a Service

> **Privacy-Preserving Access Control on the Cloud-Edge Continuum for Healthcare**

ACaaS is a runnable prototype for ABAC/RBAC/ReBAC policy enforcement across a three-tier cloud → fog → edge architecture. It enforces access control over Electronic Health Records (EHR) with built-in data minimization (pseudonymization, k-anonymity, field redaction), a mock Hyperledger Fabric PolicyChain for tamper-evident audit, and real-time policy synchronization to edge nodes.

---

## Table of Contents

- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Quick Start (Docker)](#quick-start-docker)
- [Local Development Setup](#local-development-setup)
- [Running All Benchmarks & Tests](#running-all-benchmarks--tests)
- [End-to-End Demo](#end-to-end-demo)
- [Service API Reference](#service-api-reference)
- [Monitoring (Prometheus + Grafana)](#monitoring-prometheus--grafana)
- [Project Structure](#project-structure)

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  CLOUD TIER                     │
│  policy-manager (:8001) ← REST CRUD + Audit     │
│  cloud-pdp      (:8002) ← Full policy eval      │
│  sync-server    (:8006) ← Push deltas to edges  │
│  redis          (:6379) ← Ledger / event bus     │
└────────────────────┬────────────────────────────┘
                     │ HTTP / PolicyChain delta sync
┌────────────────────▼────────────────────────────┐
│                   FOG TIER                      │
│  fog-cache       (:8007) ← Cached policy mirror │
│  fog-aggregation (:8008) ← Aggregate audit logs │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│                  EDGE TIER                      │
│  edge-pdp        (:8003) ← Lightweight PDP      │
│  data-minimizer  (:8004) ← 3-stage pipeline     │
│  pep             (:8005) ← Policy Enforcement   │
│  edge-sync-client        ← Pulls policy updates │
└─────────────────────────────────────────────────┘
```

**Data minimization pipeline (3 stages):**
1. **Pseudonymization** — HMAC-SHA256 patient ID replacement
2. **k-Anonymity generalization** — DOB → decade, postal → 3-digit prefix, ethnicity → region
3. **Field redaction** — role-based masking (doctor / nurse / researcher)

---

## Prerequisites

| Tool | Version |
|------|---------|
| Docker | ≥ 24.0 |
| Docker Compose | ≥ 2.20 (bundled with Docker Desktop) |
| Python | ≥ 3.11 *(local dev / tests only)* |
| pip | ≥ 23 *(local dev only)* |

> **Windows users:** All commands below work in WSL 2 or Git Bash. Make sure Docker Desktop is running and WSL integration is enabled.

---

## Quick Start (Docker)

### 1. Clone the repository

```bash
git clone https://github.com/SonHaXuan/ACaaS.git
cd ACaaS
```

### 2. Build all images

```bash
docker compose build
```

All services share a single Python 3.11-slim base image ([`Dockerfile.python`](Dockerfile.python)) with FastAPI, Uvicorn, Pydantic, and Redis pre-installed.

### 3. Start the full stack

```bash
docker compose up -d
```

This launches **10 services**:

| Service | Port | Description |
|---------|------|-------------|
| `redis` | — | In-memory ledger / event bus |
| `policy-manager` | **8001** | Cloud PMS — CRUD + audit + HIPAA compliance |
| `cloud-pdp` | **8002** | Full cloud-side PDP |
| `edge-pdp` | **8003** | Lightweight edge PDP (SQLite cache) |
| `data-minimizer` | **8004** | 3-stage data minimization service |
| `pep` | **8005** | Policy Enforcement Point |
| `sync-server` | **8006** | Policy delta sync server |
| `fog-cache` | **8007** | Fog policy cache |
| `fog-aggregation` | **8008** | Fog audit aggregation |
| `prometheus` | **9090** | Metrics scraping |
| `grafana` | **3000** | Dashboard (user: `admin`, password: `acaas`) |

### 4. Verify services are healthy

```bash
docker compose ps
curl http://localhost:8001/health   # policy-manager
curl http://localhost:8002/health   # cloud-pdp
curl http://localhost:8003/health   # edge-pdp
curl http://localhost:8004/health   # data-minimizer
curl http://localhost:8005/health   # pep
```

### 5. Stop the stack

```bash
docker compose down
```

To also remove all persistent volumes (databases):

```bash
docker compose down -v
```

---

## Local Development Setup

For running tests and scripts without Docker:

### 1. Create and activate a virtual environment

```bash
python3.11 -m venv .venv
source .venv/bin/activate        # Linux / macOS / WSL
# .venv\Scripts\activate         # Windows CMD
```

### 2. Install dependencies

```bash
pip install -e ".[dev]"
```

This installs the `acaas` package in editable mode along with pytest and all runtime dependencies (FastAPI, Uvicorn, Pydantic, httpx).

### 3. Bootstrap sample data (optional — for script-based demos)

```bash
python scripts/bootstrap_sample_data.py
```

Creates:
- `data/cloud/policies.json` — two sample ABAC policies
- `data/ledger/` — file-based ledger and access log
- `data/edge/ehr_records.json` — patient P123 EHR fixture

---

## Running All Benchmarks & Tests

### Unit Tests

Run **all** unit and cross-validation tests with pytest:

```bash
pytest tests/ -v
```

Individual test suites:

```bash
# Policy engine (deny-overrides, ABAC matching)
pytest tests/test_policy_engine.py -v

# Data minimizer pipeline (pseudonymization, k-anonymity, field redaction)
pytest tests/test_data_minimizer.py -v

# Shared minimizer (access-level-based redaction)
pytest tests/test_minimizer.py -v

# Edge lightweight PDP (SQLite store + evaluator)
pytest tests/test_edge_pdp.py -v

# Blockchain mock (PolicyChain, LogChain, SyncChain)
pytest tests/test_blockchain.py -v
```

> **Note:** `tests/test_integration.py` is a legacy integration test that references older service paths and may require the legacy service structure.

### Cross-Validation Tests

Verifies consistency between two independent ACaaS implementations (Claude-ICSOC vs Codex-ICSOC) across 8 checks:

```bash
pytest tests/test_cross_validation.py -v
```

Or run standalone (prints `PASS` / `FAIL` per check):

```bash
python tests/test_cross_validation.py
```

**Checks performed:**
1. Pseudonymization determinism & unlinkability
2. k-anonymity DOB/postal/ethnicity generalization
3. k-anonymity dataset threshold verification
4. Deny-overrides policy semantics
5. Default-deny with no matching policy
6. SHA-256 policy hash determinism
7. Access-level field redaction (Codex)
8. Role-based field redaction (Claude)

### Load / Throughput Benchmark (Experiment 2 — Locust)

The load test targets the **Edge PDP** (`/evaluate`) to measure throughput scalability. Requires the Docker stack running (`docker compose up -d`).

#### Install Locust

```bash
pip install locust
```

#### Interactive mode (web UI at http://localhost:8089)

```bash
locust -f tests/load/locustfile.py --host http://localhost:8003
```

#### Headless benchmark (1000 concurrent users, 60-second run)

```bash
mkdir -p results
locust -f tests/load/locustfile.py \
  --host http://localhost:8003 \
  --users 1000 \
  --spawn-rate 50 \
  --headless \
  --run-time 60s \
  --csv results/exp2
```

Results are saved to `results/exp2_stats.csv`, `results/exp2_failures.csv`, and `results/exp2_stats_history.csv`.

**Simulated workload:**
- **80%** — Doctor reading EHR (`POST /evaluate`)
- **20%** — Nurse reading lab results (`POST /evaluate`)
- **10%** — Health check (`GET /health`)

---

## End-to-End Demo

With the Docker stack running, execute the full demo script:

```bash
bash scripts/demo.sh
```

The script walks through the complete happy path:

| Step | Description |
|------|-------------|
| **1** | Create ABAC policy: `doctor/cardiology` can `READ` `EHR` |
| **1b** | Wait for edge-sync to apply the new policy |
| **2** | List all policies via policy-manager |
| **3** | Check sync-server event log |
| **4** | Edge PDP direct evaluation (expect `PERMIT`) |
| **5** | Full PEP pipeline with EHR record + data minimization |
| **6** | Deny case: nurse with wrong role (expect `403 DENY`) |
| **6b** | Wait for audit log drain |
| **7** | HIPAA compliance report |

---

## Service API Reference

### Policy Manager (`http://localhost:8001`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/policies/` | List all policies |
| `POST` | `/policies/` | Create / upsert a policy |
| `DELETE` | `/policies/{policy_id}` | Delete a policy |
| `GET` | `/audit/compliance/hipaa` | HIPAA compliance report |

**Example — create a policy:**

```bash
curl -s -X POST http://localhost:8001/policies/ \
  -H "Content-Type: application/json" \
  -d '{
    "policy_id": "doctor-ehr-read",
    "rule": {
      "subject": {"role": "doctor", "department": "cardiology", "clearance_level": 2},
      "resource": {"data_type": "EHR", "sensitivity": 3},
      "action": "read",
      "condition": {"time_range": null, "location": null, "extra": {}},
      "effect": "PERMIT"
    },
    "criticality": 4.0
  }'
```

### Edge PDP (`http://localhost:8003`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check + last sync version |
| `POST` | `/evaluate` | Evaluate an access request |

**Example — evaluate access:**

```bash
curl -s -X POST http://localhost:8003/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "subject_id": "dr-smith",
    "role": "doctor",
    "department": "cardiology",
    "clearance_level": 2,
    "patient_id": "P123",
    "resource_type": "EHR",
    "action": "read",
    "location": "hospital-1"
  }'
```

### Policy Enforcement Point (`http://localhost:8005`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/access` | Full enforcement: PDP + data minimization + audit queue |

**Example — full access request with EHR:**

```bash
curl -s -X POST http://localhost:8005/access \
  -H "Content-Type: application/json" \
  -d '{
    "subject_id": "dr-smith",
    "role": "doctor",
    "department": "cardiology",
    "clearance_level": 2,
    "patient_id": "P123",
    "resource_type": "EHR",
    "action": "read",
    "location": "hospital-1",
    "ehr_record": {
      "patient_id": "P123",
      "name": "Nguyen Van A",
      "date_of_birth": "1985-07-21",
      "postal_code": "70000",
      "ethnicity": "Vietnamese",
      "diagnosis": "hypertension",
      "medication": "amlodipine 5mg"
    }
  }'
```

### Data Minimizer (`http://localhost:8004`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/minimize` | Apply 3-stage minimization pipeline |

### Sync Server (`http://localhost:8006`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/status` | PolicyChain event list |

---

## Monitoring (Prometheus + Grafana)

Once the stack is running:

- **Prometheus** — [http://localhost:9090](http://localhost:9090)
- **Grafana** — [http://localhost:3000](http://localhost:3000)
  - Username: `admin`
  - Password: `acaas`

Prometheus scrape configuration is in `monitoring/prometheus.yml`.

---

## Project Structure

```
ACaaS/
├── Dockerfile.python              # Shared Python base image
├── docker-compose.yml             # Full 10-service stack
├── pyproject.toml                 # Package metadata + pytest config
├── sitecustomize.py               # Pytest plugin isolation
│
├── cloud/
│   ├── policy-manager/            # Cloud PMS (FastAPI + SQLite)
│   │   ├── main.py
│   │   ├── db.py
│   │   ├── adaptive.py            # Adaptive policy engine
│   │   ├── models.py
│   │   └── routes/
│   │       ├── policies.py        # CRUD endpoints
│   │       ├── conflict.py        # Conflict detection
│   │       └── audit.py           # HIPAA audit + compliance
│   └── cloud-pdp/                 # Full cloud PDP
│       ├── main.py
│       └── evaluator.py
│
├── fog/
│   ├── policy-cache/main.py       # Fog-tier policy cache
│   └── aggregation/main.py        # Audit log aggregation
│
├── edge/
│   ├── lightweight-pdp/           # SQLite-backed edge PDP
│   │   ├── main.py
│   │   └── evaluator.py
│   ├── local-policy-store/store.py
│   ├── data-minimizer/            # 3-stage minimization
│   │   ├── main.py
│   │   ├── pseudonymizer.py       # Stage 1: HMAC pseudonymization
│   │   ├── k_anonymity.py         # Stage 2: k-anonymity generalization
│   │   └── field_redactor.py      # Stage 3: role-based redaction
│   ├── pep/main.py                # Policy Enforcement Point
│   └── offline-queue/offline_queue.py
│
├── sync/
│   ├── server/sync_server.py      # Policy delta push server
│   └── client/sync_client.py      # Edge sync client (heartbeat)
│
├── blockchain/
│   └── mock/ledger.py             # Hyperledger Fabric mock (PolicyChain / LogChain / SyncChain)
│
├── shared/
│   └── acaas_shared/              # Pydantic models + policy engine + minimizer
│       ├── models.py
│       ├── policy_engine.py
│       ├── minimizer.py
│       ├── ledger.py
│       └── storage.py
│
├── tests/
│   ├── test_policy_engine.py      # Unit: ABAC evaluation
│   ├── test_data_minimizer.py     # Unit: 3-stage pipeline
│   ├── test_minimizer.py          # Unit: shared minimizer
│   ├── test_edge_pdp.py           # Unit: edge PDP + SQLite store
│   ├── test_blockchain.py         # Unit: Fabric mock ledger
│   ├── test_cross_validation.py   # Cross-validation: Claude vs Codex implementations
│   └── load/locustfile.py         # Locust load test (Experiment 2)
│
└── scripts/
    ├── demo.sh                    # Full end-to-end demo (curl-based)
    ├── run_demo.py                # Python in-process demo runner
    └── bootstrap_sample_data.py   # Seed policies + EHR fixtures
```

---

## Environment Variables

Each service can be configured via environment variables (set in `docker-compose.yml` or `.env`):

| Variable | Default | Service | Description |
|----------|---------|---------|-------------|
| `PMS_PORT` | `8001` | policy-manager | Listening port |
| `PMS_DB_PATH` | `/data/pms.db` | policy-manager | SQLite database path |
| `CLOUD_PDP_PORT` | `8002` | cloud-pdp | Listening port |
| `EDGE_PDP_PORT` | `8003` | edge-pdp | Listening port |
| `EDGE_DB_PATH` | `/data/edge.db` | edge-pdp, pep | SQLite edge store |
| `DATA_MINIMIZER_PORT` | `8004` | data-minimizer | Listening port |
| `PEP_PORT` | `8005` | pep | Listening port |
| `EDGE_PDP_URL` | `http://edge-pdp:8003` | pep | Edge PDP service URL |
| `DATA_MINIMIZER_URL` | `http://data-minimizer:8004` | pep | Data minimizer URL |
| `SYNC_SERVER_PORT` | `8006` | sync-server | Listening port |
| `SYNC_SERVER_URL` | `http://sync-server:8006` | edge-sync-client | Sync server URL |
| `PMS_URL` | `http://policy-manager:8001` | fog-cache, edge-sync-client | Policy manager URL |
| `HEARTBEAT_SEC` | `1` | edge-sync-client | Sync poll interval (seconds) |
| `EDGE_NODE_ID` | `edge-node-1` | edge-sync-client | Node identity |
| `FOG_CACHE_PORT` | `8007` | fog-cache | Listening port |
| `FOG_AGG_PORT` | `8008` | fog-aggregation | Listening port |
| `ACAAS_LEDGER_BACKEND` | `redis` | all cloud services | `redis` or `mock` |
| `ACAAS_REDIS_URL` | `redis://redis:6379/0` | all cloud services | Redis connection URL |
