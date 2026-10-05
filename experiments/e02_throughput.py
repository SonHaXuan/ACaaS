#!/usr/bin/env python3
"""
E2: Throughput & Scalability Experiment (G4/G2).
Concurrent load swept across worker levels (50, 100, 200, 500, 1000 workers; or [10, 20] if --quick),
each worker issuing 20 requests (up to 20,000 total).
Metrics: sustained throughput (req/s), P95 response time, zero-failure threshold.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.common.harness import Timer, set_seed
from experiments.common.stats import calc_summary
from experiments.common.workload import generate_access_requests
from experiments.common.io import save_results


def _worker_task(pep_url: str, requests: list[dict]) -> list[dict]:
    results = []
    for r in requests:
        data = json.dumps(r).encode()
        req = urllib.request.Request(
            f"{pep_url}/access",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with Timer() as t:
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    code = resp.status
            except urllib.error.HTTPError as e:
                code = e.code
            except Exception:
                code = 0
        results.append({"status_code": code, "latency_ms": t.elapsed_ms})
    return results


def run_e02(
    worker_levels: list[int] | None = None,
    reqs_per_worker: int = 20,
    seed: int = 42,
    pep_url: str = "http://localhost:8005",
    out_dir: Path | None = None,
) -> dict:
    set_seed(seed)
    levels = worker_levels or [50, 100, 200, 500, 1000]
    run_id = f"run_{int(time.time())}"
    print(f"=== Running E2 (Throughput): Levels={levels}, ReqsPerWorker={reqs_per_worker} ===")

    sweep_summaries = {}
    all_raw = []

    for workers in levels:
        total_reqs = workers * reqs_per_worker
        print(f"\n--- Testing concurrency level: {workers} workers ({total_reqs} total reqs) ---")
        requests = generate_access_requests(n=total_reqs, seed=seed, permit_ratio=1.0)
        chunks = [requests[i * reqs_per_worker:(i + 1) * reqs_per_worker] for i in range(workers)]

        with Timer() as total_timer:
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [executor.submit(_worker_task, pep_url, chunk) for chunk in chunks]
                all_results = []
                for f in concurrent.futures.as_completed(futures):
                    all_results.extend(f.result())

        total_elapsed_sec = total_timer.elapsed_sec
        latencies = [r["latency_ms"] for r in all_results]
        success_count = sum(1 for r in all_results if r["status_code"] in (200, 403))
        throughput_rps = round(len(all_results) / total_elapsed_sec, 2) if total_elapsed_sec > 0 else 0.0

        summary = calc_summary(latencies)
        summary["workers"] = workers
        summary["throughput_rps"] = throughput_rps
        summary["total_requests"] = len(all_results)
        summary["success_rate"] = round(success_count / len(all_results) * 100.0, 2) if all_results else 0.0
        summary["total_duration_sec"] = round(total_elapsed_sec, 3)

        sweep_summaries[f"workers_{workers}"] = summary
        print(f"  Throughput: {throughput_rps} req/s | P95: {summary['p95']:.2f} ms | Success: {summary['success_rate']}%")

        for idx, r in enumerate(all_results, 1):
            all_raw.append({"workers": workers, "sample_id": idx, **r})

    save_results(
        experiment_id="E02",
        run_id=run_id,
        raw_records=all_raw,
        summary_data=sweep_summaries,
        params={"levels": levels, "reqs_per_worker": reqs_per_worker, "seed": seed},
        seed=seed,
        base_dir=out_dir,
    )
    return sweep_summaries


def main():
    parser = argparse.ArgumentParser(description="Run E2: Throughput Experiment")
    parser.add_argument("--quick", action="store_true", help="Quick smoke test (small worker count)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--out", type=str, default=None, help="Output directory")
    args = parser.parse_args()

    levels = [10, 20] if args.quick else [50, 100, 200, 500, 1000]
    reqs = 5 if args.quick else 20
    out = Path(args.out) if args.out else None
    run_e02(worker_levels=levels, reqs_per_worker=reqs, seed=args.seed, out_dir=out)


if __name__ == "__main__":
    main()
