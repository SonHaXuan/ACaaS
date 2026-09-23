# ACaaS — Access Control as a Service

> **Privacy-Preserving Access Control on the Cloud-Edge Continuum for Healthcare**

This repository contains the runnable prototype for the ACaaS system described in the paper. It includes the cloud Policy Manager, edge Policy Enforcement Point (PEP) and PDP, the data minimization pipeline, and a mock Hyperledger Fabric PolicyChain.

---

## Prerequisites
- Docker and Docker Compose (v2.20+)
- Python 3.11+ (for local test and benchmark execution)

---

## Setup & Run (Docker)

The easiest way to run the full 10-service stack (including Prometheus and Grafana) is via Docker Compose.

1. **Build the images:**
   ```bash
   docker compose build
   ```

2. **Start the services:**
   ```bash
   docker compose up -d
   ```

3. **Stop the stack and clean up:**
   ```bash
   docker compose down -v
   ```

---

## Running Benchmarks & Tests

We provide automated scripts to verify system correctness, cross-validation, and evaluate throughput. 

### 1. End-to-End Demo

With the Docker stack running, you can execute the full end-to-end flow (policy creation, edge sync, access evaluation, data minimization, and audit logging):

```bash
bash scripts/demo.sh
```

### 2. Local Setup for Benchmarking

To run the tests and load benchmarks, set up a local Python environment first:

```bash
python3.11 -m venv .venv
source .venv/bin/activate        # Linux/macOS/WSL
# .venv\Scripts\activate         # Windows CMD
pip install -e ".[dev]"
pip install locust               # Required for load testing
```

### 3. Unit & Cross-Validation Tests

Run the complete test suite. This includes the cross-validation tests verifying semantic consistency across different ACaaS implementations (Claude-ICSOC vs Codex-ICSOC):

```bash
pytest tests/ -v
```

### 4. Throughput Scalability Benchmark (Locust)

This load test evaluates the Edge PDP's throughput capability (Experiment 2). Ensure the Docker stack is running before executing this.

**Run the headless benchmark (1000 concurrent users for 60 seconds):**
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
Results will be output to the `results/` folder as CSV files (`exp2_stats.csv`, etc.).
