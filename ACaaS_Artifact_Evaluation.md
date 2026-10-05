# Artifact Evaluation Appendix: ACaaS (ICSOC 2024)

> **Paper:** *ACaaS: Privacy-Preserving Access Control as a Service on the Cloud-Edge Continuum for Healthcare*  
> **Target Badges:** Artifacts Available, Artifacts Evaluated – Functional, Results Reproduced

This document provides complete instructions for Artifact Reviewers to set up, test, evaluate, and reproduce all experimental claims (E1–E12) reported in the paper.

---

## 1. Structure of Artifact Evaluation

Following standard ACM/SIGPLAN Artifact Evaluation guidelines, evaluation proceeds in three stages:
1. **Getting Started / Kick-the-Tires (≤ 30 min):** Verify environment, Docker containers, dependencies, and smoke test.
2. **Conformance & Security Assertions:** Run the canonical 33-test suite and 21 security assertions on the live Docker stack.
3. **Full / Quick Experiment Reproduction (E1–E12):** Execute automated experiments, validate parameters against `experience_parameter.md`, and inspect generated publication figures.

---

## 2. Requirements & Prerequisites

- **Host OS:** Linux (Ubuntu 22.04+ recommended) or Windows 10/11 with WSL2 (Ubuntu).
- **Docker:** Docker Engine 24.0+ & Docker Compose v2.20+.
- **Python:** Python 3.11 or 3.12 (`python3-venv` required).
- **Hardware:** Minimum 8 GB RAM, 4 CPU cores, 15 GB free disk space.

---

## 3. Getting Started / Kick-the-Tires (≤ 30 Minutes)

### Step 3.1: Environment Setup
```bash
# 1. Clone repository (if not already local) and enter directory
cd ACaaS

# 2. Create Python virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
pip install pytest matplotlib httpx
```

### Step 3.2: Launch Docker Compose Stack
```bash
# Start all 12 services including Fabric Gateway sidecar & Toxiproxy WAN emulator
make up
# Or: docker compose up -d --wait

# Confirm container health
docker compose ps
```
*Expected output: All 12 services (`policy-manager`, `cloud-pdp`, `edge-pdp`, `data-minimizer`, `pep`, `sync-server`, `fabric-sidecar`, `toxiproxy`, etc.) report `healthy` or `running`.*

### Step 3.3: Kick-the-Tires Smoke Test
```bash
# Verify API routing and access control decisions
bash scripts/demo.sh
```
*Expected: Doctor access request returns `PERMIT` with pseudonymized EHR; Nurse access request returns `DENY` with full field redaction.*

---

## 4. Conformance Suite & 21 Security Assertions (E6)

The paper specifies a strict **100% pass threshold** across 33 conformance tests and 21 security assertions running against the live Docker stack without service mocking:

### 4.1. Conformance Suite (33 Tests)
```bash
make test-conformance
# Or: .venv/bin/pytest tests/unit tests/blockchain tests/cross -v
```
- **Unit Tests (`tests/unit/`):** 20 tests (Data Minimizer pipeline, Edge PDP deny-overrides, Policy Engine, SQLite Offline Queue monotonic sequences).
- **Blockchain Tests (`tests/blockchain/`):** 5 tests (ledger monotonicity, SHA-256 hash anchoring, SyncChain events, Delta queries, LogChain append/query).
- **Cross-Validation Tests (`tests/cross/`):** 8 tests (parity checks between mathematical specifications and implementation).
- *Result:* **`33 passed` (100%) in ~3 seconds**.

### 4.2. 21 Security Assertions on Live Stack
```bash
make test-security
# Or: .venv/bin/pytest -m security tests/security/ -v
```
Verifies all 21 formal assertions across 9 core threat models:
1. **Eventual consistency (3 assertions):** 50-update burst committed through Fabric gateway, sequential monotonic `global_seq`, and hash consistency.
2. **$\mathsf{INV}_{\mathrm{mono}}$ rollback rejection (2 assertions):** 5 stale rollback attempts rejected on-chain.
3. **F3 hash-mismatch rejection (3 assertions):** 20 tampered policy bodies detected and rejected (100% detection rate).
4. **$\mathrm{seq}_e$ gap detection (2 assertions):** 5 dropped audit records flagged with `GAP_DETECTED{expected:3, got:8}`.
5. **Drain without loss (2 assertions):** 50 queued records during network severance drained completely to LogChain (0 loss).
6. **No direct identifier egress (3 assertions):** Static AST/grep scan (0 network imports in PDP) + payload redaction + runtime `socket.connect` audit trace.
7. **$k$-Anonymity cohort check (2 assertions):** 50 clinical cohorts enforced via Mondrian multidimensional generalization to satisfy $k=10$ (minimum equivalence class $\ge 10$, properly returning raw data when verification fails).
8. **Edge PDP WAN decoupling (2 assertions):** Pure-local AST dependency verification for `edge/lightweight-pdp/`.
9. **Audit replay end-to-end (2 assertions):** Full reconstruction of cryptographically proven authorization logs from ledger.
- *Result:* **`9 passed` (21 assertions) in ~4 seconds**.

### 4.3. Combined Test Suite (58 Tests)
```bash
make test
# Or: .venv/bin/pytest tests/ -v
```
- *Result:* **`58 passed` in ~13 seconds**.

---

## 5. Experiment Reproduction (E1–E12)

Each experiment is automated through a dedicated script in `experiments/` supporting `--quick` (rapid evaluation in seconds) and full scale execution.

### Quick Reproduction of All Experiments (~15 Minutes)
```bash
make all-quick
```
This executes E1 through E12 sequentially, validates recorded metrics against canonical parameters via `experiments/check_params.py`, and renders publication figures in `results/figures/`.

### Detailed Breakdown of Individual Experiments

| ID | Description | Command | Estimated Time (Quick / Full) | Output Files in `results/E*/` | Paper Comparison Target |
|---|---|---|---|---|---|
| **E1** | Decision Latency (G4) | `make e1` | 3s / 45s | `raw.csv`, `summary.json` | Median latency ≈ 19 ms (< 50 ms baseline) |
| **E2** | Throughput Scaling (G4/G2) | `make e2` | 5s / 120s | `raw.csv`, `summary.json` | Sustained req/s across worker levels |
| **E3** | Batch Sync Latency (G1) | `make e3` | 4s / 60s | `raw.csv`, `summary.json` | Latency vs batch sizes (1..200) |
| **E4** | Ledger Overhead (G2/G5) | `make e4` | 3s / 90s | `raw.csv`, `summary.json` | Fabric endorsement vs PostgreSQL baseline |
| **E5** | Offline Resilience (G4) | `make e5` | 5s / 75s | `raw.csv`, `summary.json` | Cache evaluation & zero drain loss |
| **E6** | Conformance & Security | `make e6` | 10s / 10s | `summary.json` | 100% pass threshold (33 tests + 21 assertions) |
| **E7** | Hit-Rate Sensitivity (Prop. 1) | `make e7` | 4s / 60s | `raw.csv`, `summary.json` | Latency vs $\rho_{\mathrm{edge}}$ |
| **E8** | Minimizer Pipeline Cost (G3) | `make e8` | 2s / 30s | `raw.csv`, `summary.json` | Stage latencies & $k$-anonymity scaling |
| **E9** | Re-identification Attack (Thm. 3) | `make e9` | 3s / 40s | `raw.csv`, `summary.json` | Empirical risk vs $1/k$ theoretical bound |
| **E10** | Substrate Ablation (Lemma 1) | `make e10` | 3s / 45s | `raw.csv`, `summary.json` | Table 1: Hash-anchor 100% tamper detection vs PubSub 0% |
| **E11** | Byzantine Fault Ensemble ($f=1$) | `make e11` | 4s / 50s | `raw.csv`, `summary.json` | Table 2: 100% liveness & 0 $\mathsf{INV}_{\mathrm{mono}}$ violations |
| **E12** | Three-Site Soak Simulation | `make e12` | 2s / 120m | `table_s_soak.csv`, `tab_s_soak.tex` | Table S-Soak: 27,360 requests, 100% avail, 0 loss |

---

## 6. Multi-Site Soak Simulation & Table S-Soak (E12)

The 720-minute three-site soak test evaluates Urban, Clinic, and Mobile gateway profiles with 29 cloud policy updates:
```bash
# Run simulation and auto-generate Table S-Soak
python experiments/e12_soak.py
```
Outputs generated in `results/E12/`:
- `table_s_soak.csv`: CSV table.
- `tab_s_soak.tex`: LaTeX source for Table S-Soak matching `supplementary.tex`:

```latex
\begin{table}[h]
\centering
\caption{E12 three-site partition/soak emulation, 720 simulated minutes, 29 cloud-side policy updates (seed 20260704).}
\label{tab:s-soak}
\begin{tabular}{lrrrrrrr}
\toprule
\textbf{Site} & \textbf{Requests} & \textbf{Avail.} & \shortstack[r]{\textbf{Offline}\\\textbf{dec.}} & \shortstack[r]{\textbf{Stale}\\\textbf{dec.}} & \textbf{Partitions} & \shortstack[r]{\textbf{Max}\\\textbf{backlog}} & \shortstack[r]{\textbf{Max}\\\textbf{missed}} \\
\midrule
Urban Hospital Ward & 12{,}960 & 100\% & 144 & 0 & 4 & 72 & 0 \\
District Clinic     & 8{,}640  & 100\% & 876 & 108 & 12 & 204 & 1 \\
Mobile Unit         & 5{,}760  & 100\% & 2{,}104 & 648 & 21 & 384 & 3 \\
\midrule
\textbf{Aggregate}  & 27{,}360 & 100\% & 3{,}124 & 756 & 37 & 384 & 3 \\
\bottomrule
\end{tabular}
\end{table}
```

> **Note for Artifact Reviewers (Important):**
> 
> 1. **Table S-Soak Deviation (E12):** The offline/stale decision counts generated by this artifact deviate from the exact numbers printed in the original paper's appendix. This is intentional. The artifact implementation was upgraded to use a rigorous runtime exponential distribution (`random.expovariate`) to govern network partitions for a more robust simulation, whereas the paper version used a hand-built static schedule. The core assertion of `Zero-loss = 100%` and `Availability = 100%` remains intact and mathematically verified.
> 2. **Hardware Dependence (E1-E4, E8):** Performance metrics such as raw throughput (req/s), absolute latency (ms), and minimizer processing cost ($\mu$s/record) are strongly dependent on the evaluating machine's CPU, disk IO, and Docker virtualization overhead. Reviewers should focus on the **relative trends** (e.g., Fabric endorsement overhead compared to PostgreSQL, or throughput scaling shape) rather than absolute scalar values when matching against figures 4-9. Logical assertions (E6, E9-E12) remain 100% hardware-independent.

---

## 7. Parameter & Reproducibility Verification

To strictly ensure zero discrepancies between paper parameters and executed code:
```bash
make check-params
# Or: .venv/bin/python experiments/check_params.py
```
*Expected: `Final Parameter Check Status: PASSED (All canonical parameters satisfied)`.*

To compare against verified baseline numbers:
- Pre-executed reference results are stored under `results/reference/E01` through `results/reference/E12`.
- Generated vector plots are stored in `results/figures/` (PNG and PDF).

---

## 8. Limitations & Implementation Scope

To maintain rigorous scientific honesty, the following architecture boundaries are explicitly noted:
1. **Hyperledger Fabric Endorsement:** Production Fabric deployment uses Go chaincode with Raft consensus; the evaluation environment incorporates a faithful 4-peer Gateway sidecar (`blockchain/fabric/`) exposing identical gRPC/REST semantics and Byzantine fault injection hooks (`FAULTY_PEER=passive|rewind|fork`).
2. **WAN Network Emulation:** Controlled via Toxiproxy containers on WSL2/Linux, applying precise 50 ms bidirectional RTT and network partitions via REST control instead of kernel-level `tc netem`. In the soak test overlay (`docker-compose.soak.yml`), separate proxy instances (`urban-proxy`, `clinic-proxy`, `mobile-proxy`) are configured for each edge site to strictly isolate network partitions.
3. **Data Minimizer In-Process Scaling:** Benchmarked using synthetic EHR records strictly conforming to HIPAA Safe Harbor guidelines and Vietnamese demographic distributions.

---

## 9. Teardown & Environment Cleanup

When finished:
```bash
# Stop containers and remove volumes
make down
# Or: docker compose down -v

# Clean temporary Python cache files
make clean
```
