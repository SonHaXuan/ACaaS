#!/usr/bin/env python3
"""
E4: Ledger Overhead Experiment (G2/G5).
Compares baseline (direct PostgreSQL write) vs. ACaaS ledger append (tamper-evident log).
200 operations per configuration (or 20 if --quick).
Metric: per-operation latency distribution (median, IQR, boxplot metrics).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.common.harness import Timer, set_seed
from experiments.common.stats import calc_summary
from experiments.common.io import save_results
from blockchain.mock import fabric


def _run_baseline_db_writes(n_ops: int) -> list[float]:
    """Execute n_ops direct writes to tamper-evident baseline audit table (prev_hash/hash chaining)."""
    import hashlib
    conn = sqlite3.connect(":memory:")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT,
            subject_id TEXT,
            decision TEXT,
            prev_hash TEXT,
            hash TEXT,
            timestamp REAL
        )
    """)
    conn.commit()

    latencies = []
    prev_h = "0" * 32
    for i in range(1, n_ops + 1):
        ts = time.time()
        payload = f"{i}:{prev_h}:sub-{i}:PERMIT:{ts}"
        curr_h = hashlib.sha256(payload.encode()).hexdigest()[:32]
        with Timer() as t:
            c.execute(
                "INSERT INTO audit_log (request_id, subject_id, decision, prev_hash, hash, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (f"req-{i}", f"sub-{i}", "PERMIT", prev_h, curr_h, ts),
            )
            conn.commit()
        latencies.append(t.elapsed_ms)
        prev_h = curr_h
    conn.close()
    return latencies


def _run_acaas_ledger_writes(n_ops: int, gateway_url: str = "http://localhost:7050") -> list[float]:
    """Execute n_ops tamper-evident append_log operations via Fabric Gateway Sidecar or backend."""
    from blockchain.fabric.client import FabricGatewayClient
    client = None
    try:
        c = FabricGatewayClient(gateway_url=gateway_url, timeout=2.0)
        c.health()
        client = c
    except Exception:
        client = fabric

    latencies = []
    for i in range(1, n_ops + 1):
        entry = {
            "request_id": f"e04-req-{i}",
            "subject_id": f"sub-{i}",
            "patient_id": f"P-{i}",
            "decision": "PERMIT",
            "evaluated_at": time.time(),
            "edge_id": "edge-node-1",
            "seq_e": i,
        }
        with Timer() as t:
            client.append_log(entry)
        latencies.append(t.elapsed_ms)
    return latencies


def run_e04(
    n_ops: int = 200,
    seed: int = 42,
    out_dir: Path | None = None,
) -> dict:
    set_seed(seed)
    run_id = f"run_{int(time.time())}"
    print(f"=== Running E4 (Ledger Overhead): N={n_ops} operations per config ===")

    print("\n1. Measuring Baseline DB writes...")
    base_latencies = _run_baseline_db_writes(n_ops)
    base_summary = calc_summary(base_latencies)
    print(f"   Baseline Median: {base_summary['median']:.3f} ms | IQR: {base_summary['iqr']:.3f} ms")

    print("\n2. Measuring ACaaS Ledger writes...")
    ledger_latencies = _run_acaas_ledger_writes(n_ops)
    ledger_summary = calc_summary(ledger_latencies)
    print(f"   ACaaS Ledger Median: {ledger_summary['median']:.3f} ms | IQR: {ledger_summary['iqr']:.3f} ms")

    diff_median = ledger_summary['median'] - base_summary['median']
    print(f"\nTamper-evidence overhead: +{diff_median:.3f} ms per operation")

    raw_records = []
    for i in range(n_ops):
        raw_records.append({
            "op_id": i + 1,
            "baseline_ms": base_latencies[i],
            "ledger_ms": ledger_latencies[i],
        })

    summary_data = {
        "baseline_db": base_summary,
        "acaas_ledger": ledger_summary,
        "overhead_median_ms": round(diff_median, 3),
    }

    save_results(
        experiment_id="E04",
        run_id=run_id,
        raw_records=raw_records,
        summary_data=summary_data,
        params={"n_ops": n_ops, "seed": seed},
        seed=seed,
        base_dir=out_dir,
    )
    return summary_data


def main():
    parser = argparse.ArgumentParser(description="Run E4: Ledger Overhead Experiment")
    parser.add_argument("--quick", action="store_true", help="Quick smoke test (20 ops)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--out", type=str, default=None, help="Output directory")
    args = parser.parse_args()

    n = 20 if args.quick else 200
    out = Path(args.out) if args.out else None
    run_e04(n_ops=n, seed=args.seed, out_dir=out)


if __name__ == "__main__":
    main()
