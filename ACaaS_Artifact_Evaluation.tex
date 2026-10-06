# ACaaS — Access Control as a Service

> **Privacy-Preserving Access Control on the Cloud-Edge Continuum for Healthcare**

This repository contains the official runnable prototype and artifact evaluation environment for **ACaaS** as described in the paper. It aims to provide complete instructions to set up, test, evaluate, and reproduce all experimental claims (E1–E12) reported in the paper.

---

## Prerequisites

- **Host OS:** Linux (Ubuntu 22.04+ recommended) or Windows 10/11 with WSL2 (Ubuntu).
- **Docker:** Docker Engine 24.0+ & Docker Compose v2.20+.
- **Python:** Python 3.11 or 3.12 (`python3-venv` required).
- **Hardware:** Minimum 8 GB RAM, 4 CPU cores, 15 GB free disk space.

---

## 1. Getting Started / Kick-the-Tires

### Environment Setup

1. **Clone repository and enter directory:**
   ```bash
   git clone <repository_url> ACaaS
   cd ACaaS
   ```

2. **Create Python virtual environment and install dependencies:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -e ".[dev]"
   pip install pytest matplotlib httpx
   ```

### Launch Docker Compose Stack

Start all services, including the cloud and edge layers, Fabric Gateway sidecar, and Toxiproxy WAN emulator.

```bash
make up
```

Confirm container health:
```bash
docker compose ps
```
*(Expected output: All services report `healthy` or `running`.)*

### Kick-the-Tires Smoke Test

Verify API routing and access control decisions:
```bash
bash scripts/demo.sh
```
*(Expected: Doctor access request returns `PERMIT` with pseudonymized EHR; Nurse access request returns `DENY` with full field redaction.)*

---

## 2. Conformance Suite & Security Assertions (E6)

The implementation maintains a strict **100% pass threshold** across 33 conformance tests and 21 security assertions running against the live Docker stack without service mocking.

Run the entire test suite (58 tests):
```bash
make test
```
*(Result: 58 passed in ~16 seconds)*

You can also run them individually:
- **Conformance Suite (33 Tests):** `make test-conformance` (Unit, Blockchain, and Cross-Validation tests).
- **Security Assertions (21 Assertions):** `make test-security` (Verifies event consistency, hash mismatches, sequence gap detection, drain resilience, etc.).

---

## 3. Experiment Reproduction (E1–E12)

Each experiment is automated through a dedicated script in `experiments/` supporting `--quick` (rapid evaluation in seconds) and full-scale execution.

### Quick Reproduction of All Experiments (~15 Minutes)

```bash
make all-quick
```
This executes E1 through E12 sequentially, validates recorded metrics against canonical parameters, and renders publication figures in `results/figures/`.

### Parameter Validation
To strictly ensure zero discrepancies between paper parameters and executed code:
```bash
make check-params
```

### Generate Publication Figures
To generate all figures collectively without re-running the experiments:
```bash
make figures
```
Plots will be saved as PDF and PNG files in the `results/figures/` directory.

### Detailed Breakdown of Individual Experiments

| ID | Description | Command | Output Files | Paper Comparison Target |
|:---|:------------|:--------|:-------------|:------------------------|
| **E1** | Decision Latency (G4) | `make e1` | `raw.csv`, `summary.json`,<br>`fig_e01_latency.pdf` | Median latency $\approx$ 19 ms ($<$ 50 ms) |
| **E2** | Throughput Scaling (G4/G2) | `make e2` | `raw.csv`, `summary.json`,<br>`fig_e02_throughput.pdf` | Sustained req/s across worker levels |
| **E3** | Batch Sync Latency (G1) | `make e3` | `raw.csv`, `summary.json`,<br>`fig_e03_sync.pdf` | Latency vs batch sizes (1..200) |
| **E4** | Ledger Overhead (G2/G5) | `make e4` | `raw.csv`, <br>`summary.json` | Fabric endorsement vs PostgreSQL baseline |
| **E5** | Offline Resilience (G4) | `make e5` | `raw.csv`, <br>`summary.json` | Cache evaluation & zero drain loss |
| **E6** | Conformance & Security | `make e6` | `summary.json` | 100% pass threshold (33+21 tests) |
| **E7** | Hit-Rate Sensitivity (Prop. 1) | `make e7` | `raw.csv`, `summary.json`,<br>`fig_e07_hitrate.pdf` | Latency vs cache hit-rate |
| **E8** | Minimizer Pipeline Cost (G3) | `make e8` | `raw.csv`, `summary.json`,<br>`fig_e08_minimizer.pdf` | Stage latencies & $k$-anonymity scaling |
| **E9** | Re-identification Attack (Thm. 3) | `make e9` | `raw.csv`, `summary.json`,<br>`fig_e09_attack.pdf` | Empirical risk vs $1/k$ theoretical bound |
| **E10** | Substrate Ablation (Lemma 1) | `make e10` | `raw.csv`, <br>`summary.json` | Hash-anchor 100% tamper vs PubSub 0% |
| **E11** | Byzantine Fault Ensemble ($f=1$) | `make e11` | `raw.csv`, <br>`summary.json` | 100% liveness & 0 INV_mono violations |
| **E12** | Three-Site Soak Simulation | `make e12` | `table_s_soak.csv`,<br>`tab_s_soak.tex` | 27,360 requests, 100% avail, 0 loss |

*(Note: Hardware Dependence – Performance metrics such as raw throughput and absolute latency are dependent on the evaluating machine's CPU/IO. Reviewers should focus on relative trends. Logical assertions remain 100% hardware-independent.)*

---

## 4. Teardown & Environment Cleanup

When finished, shut down the infrastructure properly:

```bash
# Stop containers and remove volumes
make down

# Clean temporary Python cache files
make clean
```
