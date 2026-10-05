#!/usr/bin/env python3
"""
E1: Decision Latency Experiment (G4).
Paper parameter:
  - 1,000 sequential requests from a single client (20 if --quick)
  - 50 ms WAN active (configured via Toxiproxy)
  - Policies pre-loaded
  - Metrics: median and IQR of end-to-end decision latency
"""
from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request
import json
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.common.harness import Timer, set_seed, run_warmup
from experiments.common.stats import calc_summary
from experiments.common.wan import wan
from experiments.common.workload import generate_access_requests, generate_policies
from experiments.common.io import save_results


def run_e01(
    n_requests: int = 1000,
    seed: int = 42,
    wan_latency_ms: int = 50,
    pep_url: str = "http://localhost:8005",
    pms_url: str = "http://localhost:8001",
    pdp_url: str = "http://localhost:8003",
    out_dir: Path | None = None,
) -> dict:
    set_seed(seed)
    run_id = f"run_{int(time.time())}"
    print(f"=== Running E1 (Latency): N={n_requests}, WAN={wan_latency_ms}ms, Seed={seed} ===")

    # 1. Configure WAN latency via Toxiproxy if running
    if wan.is_alive():
        print(f"[WAN] Setting Toxiproxy latency to {wan_latency_ms} ms...")
        wan.set_latency(latency_ms=wan_latency_ms)
    else:
        print("[WAN] Toxiproxy not detected, running with direct local latency.")

    # 2. Pre-load policies at PMS and verify edge sync
    test_policy = {
        "policy_id": "e01-cardio-read",
        "rule": {
            "subject": {"role": "doctor", "department": "cardiology", "clearance_level": 2},
            "resource": {"data_type": "EHR", "sensitivity": 3},
            "action": "read",
            "condition": {"time_range": None, "location": None, "extra": {}},
            "effect": "PERMIT",
        },
        "criticality": 3.0,
    }
    try:
        req = urllib.request.Request(
            f"{pms_url}/policies/",
            data=json.dumps(test_policy).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass  # Policy might already exist

    # Wait briefly for edge sync
    time.sleep(1.0)

    # 3. Generate sequential requests matching the pre-loaded policy
    requests = generate_access_requests(
        n=n_requests, seed=seed, permit_ratio=1.0, known_policies=[test_policy]
    )

    # Warmup
    def _do_single_request(r: dict) -> tuple[int, float]:
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
        return code, t.elapsed_ms

    if requests:
        run_warmup(lambda: _do_single_request(requests[0]), n_warmup=10)

    # 4. Execute sequential measurements (Edge ACaaS)
    latencies: list[float] = []
    raw_records: list[dict] = []

    print("\n--- Executing Edge ACaaS Evaluation (PEP -> Edge PDP) ---")
    for i, req_body in enumerate(requests, 1):
        code, lat = _do_single_request(req_body)
        latencies.append(lat)
        raw_records.append({
            "sample_id": i,
            "path": "edge",
            "subject_id": req_body["subject_id"],
            "patient_id": req_body["patient_id"],
            "status_code": code,
            "latency_ms": round(lat, 3),
        })
        if i % 100 == 0 or i == n_requests:
            print(f"  Progress: {i}/{n_requests} requests executed (last: {lat:.2f} ms)")

    # 4b. Cloud-Centric Baseline (direct over WAN)
    print("\n--- Executing Cloud-Centric Baseline (Direct over WAN) ---")
    cloud_pdp_url = "http://localhost:18002" if wan.is_alive() else "http://localhost:8002"
    cloud_latencies: list[float] = []

    def _do_cloud_request(r: dict) -> tuple[int, float]:
        data = json.dumps(r).encode()
        req = urllib.request.Request(
            f"{cloud_pdp_url}/evaluate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with Timer() as t:
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    code = resp.status
            except Exception:
                code = 0
        return code, t.elapsed_ms

    n_cloud = min(n_requests, 100 if n_requests > 100 else n_requests)
    for i, req_body in enumerate(requests[:n_cloud], 1):
        code, lat = _do_cloud_request(req_body)
        cloud_latencies.append(lat)
        raw_records.append({
            "sample_id": i,
            "path": "cloud",
            "subject_id": req_body["subject_id"],
            "patient_id": req_body["patient_id"],
            "status_code": code,
            "latency_ms": round(lat, 3),
        })

    # 5. Compute statistics
    summary_edge = calc_summary(latencies)
    summary_cloud = calc_summary(cloud_latencies) if cloud_latencies else {}
    speedup = round(summary_cloud["median"] / summary_edge["median"], 2) if summary_cloud and summary_edge["median"] > 0 else 1.0

    summary = {
        "edge": summary_edge,
        "cloud_baseline": summary_cloud,
        "speedup_ratio": speedup,
        # Maintain top-level fields for plotting compatibility
        "median": summary_edge["median"],
        "iqr": summary_edge["iqr"],
        "p95": summary_edge["p95"],
        "count": summary_edge["count"],
        "ci_lower": summary_edge["ci_lower"],
        "ci_upper": summary_edge["ci_upper"],
    }
    params = {
        "n_requests": n_requests,
        "wan_latency_ms": wan_latency_ms,
        "seed": seed,
    }

    # 6. Save results
    save_results(
        experiment_id="E01",
        run_id=run_id,
        raw_records=raw_records,
        summary_data=summary,
        params=params,
        seed=seed,
        base_dir=out_dir,
    )

    print("\n--- E1 Latency Summary ---")
    print(f"  Edge Count:  {summary_edge['count']}")
    print(f"  Edge Median: {summary_edge['median']:.3f} ms (IQR: {summary_edge['iqr']:.3f} ms, P95: {summary_edge['p95']:.3f} ms)")
    if summary_cloud:
        print(f"  Cloud Median: {summary_cloud['median']:.3f} ms (Speedup: {speedup}x)")
    print(f"  95% CI: [{summary['ci_lower']:.3f}, {summary['ci_upper']:.3f}] ms")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Run E1: Decision Latency Experiment")
    parser.add_argument("--quick", action="store_true", help="Run quick smoke test (20 requests)")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic random seed")
    parser.add_argument("--wan", type=int, default=50, help="Toxiproxy WAN latency in ms")
    parser.add_argument("--out", type=str, default=None, help="Output directory for results")
    args = parser.parse_args()

    n = 20 if args.quick else 1000
    out = Path(args.out) if args.out else None
    run_e01(n_requests=n, seed=args.seed, wan_latency_ms=args.wan, out_dir=out)


if __name__ == "__main__":
    main()
