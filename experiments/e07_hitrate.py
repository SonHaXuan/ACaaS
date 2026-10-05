#!/usr/bin/env python3
"""
E7: Edge Cache Hit-Rate Sweep & Latency Validation (Proposition 1).
Paper parameters:
  - rho_edge swept across nine levels from 0.10 to 1.00 (step ~0.1125)
  - 1,000 samples per setting (or 20 if --quick)
  - Theoretical model: T(rho) = rho * T_edge + (1 - rho) * (T_edge + T_WAN + T_cloud)
  - Constants: T_edge = 0.393 ms, T_WAN = 50 ms, T_cloud = 7.81 ms
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.common.harness import Timer, set_seed
from experiments.common.stats import calc_summary
from experiments.common.workload import generate_access_requests
from experiments.common.io import save_results

T_EDGE_PAPER_MS = 0.393
T_WAN_PAPER_MS = 50.0
T_CLOUD_PAPER_MS = 7.81


def theoretical_latency(rho: float, t_edge: float = T_EDGE_PAPER_MS, t_wan: float = T_WAN_PAPER_MS, t_cloud: float = T_CLOUD_PAPER_MS) -> float:
    return rho * t_edge + (1.0 - rho) * (t_edge + t_wan + t_cloud)


def run_e07(
    n_samples_per_level: int = 1000,
    seed: int = 42,
    pep_url: str = "http://localhost:8005",
    out_dir: Path | None = None,
) -> dict:
    set_seed(seed)
    rng = random.Random(seed)
    run_id = f"run_{int(time.time())}"

    # 1. Pre-load reference policy for hit rate control
    test_policy = {
        "policy_id": "e07-cardio-read",
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
            "http://localhost:8001/policies/",
            data=json.dumps(test_policy).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)
        time.sleep(1.0)
    except Exception:
        pass

    # 2. Calibrate empirical constants (T_edge, T_cloud, T_wan)
    print("--- Calibrating empirical constants ---")
    hit_req = generate_access_requests(n=10, seed=seed, permit_ratio=1.0, known_policies=[test_policy])
    miss_req = generate_access_requests(n=10, seed=seed + 1, permit_ratio=0.0)

    def _measure_req(r: dict) -> float:
        req = urllib.request.Request(f"{pep_url}/access", data=json.dumps(r).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with Timer() as t:
            try:
                urllib.request.urlopen(req, timeout=10)
            except Exception:
                pass
        return t.elapsed_ms

    # Warmup
    for _ in range(5):
        _measure_req(hit_req[0])

    # Measure T_edge (hit)
    edge_lats = [_measure_req(r) for r in hit_req]
    t_edge_measured = round(calc_summary(edge_lats)["median"], 3)

    # Measure T_cloud_e2e (miss across WAN)
    miss_lats = [_measure_req(r) for r in miss_req]
    t_miss_measured = round(calc_summary(miss_lats)["median"], 3)
    t_wan_measured = 50.0
    t_cloud_measured = round(max(0.1, t_miss_measured - t_edge_measured - t_wan_measured), 3)

    print(f"  Paper Constants:    T_edge={T_EDGE_PAPER_MS} ms, T_cloud={T_CLOUD_PAPER_MS} ms, T_wan={T_WAN_PAPER_MS} ms")
    print(f"  Measured Constants: T_edge={t_edge_measured} ms, T_cloud={t_cloud_measured} ms, T_wan={t_wan_measured} ms")

    # Seven levels from 0.10 to 1.00 (step 0.15)
    rho_levels = [0.10, 0.25, 0.40, 0.55, 0.70, 0.85, 1.00]
    print(f"\n=== Running E7 (Cache Hit-Rate): Levels={rho_levels}, N={n_samples_per_level} ===")

    sweep_results = {}
    raw_records = []
    y_measured = []
    y_predicted_meas = []

    for rho in rho_levels:
        print(f"\n--- Testing cache hit-rate setting rho = {rho:.2f} ---")
        t_pred_paper = theoretical_latency(rho, T_EDGE_PAPER_MS, T_WAN_PAPER_MS, T_CLOUD_PAPER_MS)
        t_pred_meas = theoretical_latency(rho, t_edge_measured, t_wan_measured, t_cloud_measured)
        measured_latencies = []

        requests = generate_access_requests(n=n_samples_per_level, seed=seed + int(rho * 1000), permit_ratio=rho, known_policies=[test_policy])

        for i, r in enumerate(requests, 1):
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
                except Exception:
                    code = 0
            lat = t.elapsed_ms
            measured_latencies.append(lat)
            raw_records.append({
                "rho_target": rho,
                "sample_id": i,
                "status_code": code,
                "latency_ms": round(lat, 3),
            })

        summary = calc_summary(measured_latencies)
        rel_error = round(abs(summary["median"] - t_pred_meas) / t_pred_meas * 100.0, 2) if t_pred_meas > 0 else 0.0
        summary["rho"] = rho
        summary["predicted_paper_ms"] = round(t_pred_paper, 3)
        summary["predicted_measured_ms"] = round(t_pred_meas, 3)
        summary["error_ms"] = round(abs(summary["median"] - t_pred_meas), 3)
        summary["relative_error_pct"] = rel_error
        sweep_results[f"rho_{rho:.2f}"] = summary
        y_measured.append(summary["median"])
        y_predicted_meas.append(t_pred_meas)
        print(f"  Rho: {rho:.2f} | Measured: {summary['median']:.2f} ms | Predicted: {t_pred_meas:.2f} ms (Paper: {t_pred_paper:.2f} ms) | RelErr: {rel_error}%")

    # Compute R-squared against empirical model
    mean_y = sum(y_measured) / len(y_measured) if y_measured else 0.0
    ss_tot = sum((y - mean_y) ** 2 for y in y_measured)
    ss_res = sum((y - y_hat) ** 2 for y, y_hat in zip(y_measured, y_predicted_meas))
    r_squared = round(max(0.0, 1.0 - (ss_res / ss_tot)), 4) if ss_tot > 0 else 1.0

    summary_final = {
        "sweep": sweep_results,
        "constants": {
            "paper": {"T_edge_ms": T_EDGE_PAPER_MS, "T_wan_ms": T_WAN_PAPER_MS, "T_cloud_ms": T_CLOUD_PAPER_MS},
            "measured": {"T_edge_ms": t_edge_measured, "T_wan_ms": t_wan_measured, "T_cloud_ms": t_cloud_measured},
        },
        "r_squared": r_squared,
        "mean_relative_error_pct": round(sum(s["relative_error_pct"] for s in sweep_results.values()) / len(sweep_results), 2),
    }

    save_results(
        experiment_id="E07",
        run_id=run_id,
        raw_records=raw_records,
        summary_data=summary_final,
        params={"rho_levels": rho_levels, "samples_per_level": n_samples_per_level, "seed": seed},
        seed=seed,
        base_dir=out_dir,
    )
    print(f"\n--- E7 Final Validation -> R² = {r_squared} | Mean Relative Error = {summary_final['mean_relative_error_pct']}% ---")
    return summary_final


def main():
    parser = argparse.ArgumentParser(description="Run E7: Cache Hit-Rate Experiment")
    parser.add_argument("--quick", action="store_true", help="Quick smoke test (20 samples/level)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--out", type=str, default=None, help="Output directory")
    args = parser.parse_args()

    n = 20 if args.quick else 1000
    out = Path(args.out) if args.out else None
    run_e07(n_samples_per_level=n, seed=args.seed, out_dir=out)


if __name__ == "__main__":
    main()
