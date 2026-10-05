#!/usr/bin/env python3
"""
E3: Sync Consistency & Propagation Latency Experiment (G1/Corollary 1).
Policy-batch commit to PolicyChain; synchronization latency measured to last-edge ACK.
Batch sizes: 1, 5, 10, 25, 50, 100, 200 policies (seven levels); 10 repetitions each.
Metric: median ± IQR per batch size.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.common.harness import Timer, set_seed
from experiments.common.stats import calc_summary
from experiments.common.workload import generate_policies
from experiments.common.io import save_results


def run_e03(
    batch_sizes: list[int] | None = None,
    repetitions: int = 10,
    seed: int = 42,
    pms_url: str = "http://localhost:8001",
    sync_url: str = "http://localhost:8006",
    edge_node_id: str = "edge-node-1",
    out_dir: Path | None = None,
) -> dict:
    set_seed(seed)
    sizes = batch_sizes or [1, 5, 10, 25, 50, 100, 200]
    run_id = f"run_{int(time.time())}"
    print(f"=== Running E3 (Sync Latency): BatchSizes={sizes}, Reps={repetitions} ===")

    all_summaries = {}
    raw_records = []

    for batch_size in sizes:
        print(f"\n--- Testing Batch Size: {batch_size} policies ({repetitions} repetitions) ---")
        batch_latencies = []

        for rep in range(1, repetitions + 1):
            policies = generate_policies(n=batch_size, seed=seed + rep * 1000)
            for p in policies:
                p["policy_id"] = f"e03-b{batch_size}-r{rep}-{p['policy_id']}"

            # Record initial sync state
            with Timer() as t:
                # 1. Commit batch to PMS (try /policies/batch first, fallback to loop)
                batch_committed = False
                try:
                    req = urllib.request.Request(
                        f"{pms_url}/policies/batch",
                        data=json.dumps(policies).encode(),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        if resp.status in (200, 201):
                            batch_committed = True
                except Exception:
                    pass

                if not batch_committed:
                    for p in policies:
                        req = urllib.request.Request(
                            f"{pms_url}/policies/",
                            data=json.dumps(p).encode(),
                            headers={"Content-Type": "application/json"},
                            method="POST",
                        )
                        try:
                            urllib.request.urlopen(req, timeout=5)
                        except Exception:
                            pass

                # 2. Poll sync server until all target edges ACK latest sequence
                target_edges = [e.strip() for e in edge_node_id.split(",") if e.strip()]
                start_poll = time.time()
                synced = False
                while time.time() - start_poll < 30.0:
                    try:
                        with urllib.request.urlopen(f"{sync_url}/status", timeout=2) as resp:
                            status_data = json.load(resp)
                            curr_seq = status_data.get("current_global_seq", 0)
                            edges = status_data.get("edge_nodes", [])
                            all_acked = True
                            for te in target_edges:
                                edge_info = next((e for e in edges if e.get("edge_node_id") == te), None)
                                if not edge_info or edge_info.get("last_global_seq", 0) < curr_seq or curr_seq == 0:
                                    all_acked = False
                                    break
                            if all_acked:
                                synced = True
                                break
                    except Exception:
                        pass
                    time.sleep(0.05)

            lat_ms = t.elapsed_ms
            batch_latencies.append(lat_ms)
            raw_records.append({
                "batch_size": batch_size,
                "repetition": rep,
                "latency_ms": round(lat_ms, 3),
                "synced": synced,
            })
            print(f"  Rep {rep}/{repetitions}: {lat_ms:.2f} ms (synced: {synced})")

        summary = calc_summary(batch_latencies)
        summary["batch_size"] = batch_size
        summary["repetitions"] = repetitions
        all_summaries[f"batch_{batch_size}"] = summary
        print(f"  Result -> Median: {summary['median']:.2f} ms | IQR: {summary['iqr']:.2f} ms")

    save_results(
        experiment_id="E03",
        run_id=run_id,
        raw_records=raw_records,
        summary_data=all_summaries,
        params={"batch_sizes": sizes, "repetitions": repetitions, "seed": seed},
        seed=seed,
        base_dir=out_dir,
    )
    return all_summaries


def main():
    parser = argparse.ArgumentParser(description="Run E3: Policy Sync Latency Experiment")
    parser.add_argument("--quick", action="store_true", help="Quick smoke test")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--out", type=str, default=None, help="Output directory")
    args = parser.parse_args()

    sizes = [1, 5] if args.quick else [1, 5, 10, 25, 50, 100, 200]
    reps = 2 if args.quick else 10
    out = Path(args.out) if args.out else None
    run_e03(batch_sizes=sizes, repetitions=reps, seed=args.seed, out_dir=out)


if __name__ == "__main__":
    main()
