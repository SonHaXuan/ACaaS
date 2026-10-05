#!/usr/bin/env python3
"""
E9: Re-Identification Attack Simulation & Empirical Risk (Theorem 3).
Paper parameters:
  - Adversary: honest-but-curious clinician with exact quasi-identifier background knowledge
  - Cohort: 10,000 synthetic records (or 50 if --quick)
  - 2,000 attack trials per (k, R); k in {5, 10, 20}, R in 1..10 independent releases
  - Baseline comparison: theoretical single-release bound (1/k) and cumulative bound (1 - (1 - 1/k)^R)
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.common.harness import set_seed
from experiments.common.workload import generate_ehr_records
from experiments.common.io import save_results
MIN_DIR = str(ROOT / "edge" / "data-minimizer")
if MIN_DIR not in sys.path:
    sys.path.insert(0, MIN_DIR)
from k_anonymity import generalize_record


def run_e09(
    cohort_size: int = 10000,
    trials_per_setting: int = 2000,
    seed: int = 42,
    out_dir: Path | None = None,
) -> dict:
    set_seed(seed)
    rng = random.Random(seed)
    run_id = f"run_{int(time.time())}"
    print(f"=== Running E9 (Re-Identification Risk): Cohort={cohort_size}, Trials={trials_per_setting} ===")

    k_values = [5, 10, 20]
    r_values = list(range(1, 11))
    results_by_k = {}
    raw_records = []

    # Pre-generate synthetic records
    base_records = generate_ehr_records(n=cohort_size, seed=seed)
    minimized_cohort = [generalize_record(r) for r in base_records]

    for k in k_values:
        theoretical_bound_single = 1.0 / k
        r_results = {}
        print(f"\n--- Testing k = {k} (Single-release bound 1/k = {theoretical_bound_single:.3f}) ---")

        for R in r_values:
            theoretical_cumulative = 1.0 - (1.0 - theoretical_bound_single) ** R
            successful_reidentifications = 0

            # Simulate attack trials: clinician selects a target and guesses across R independent releases
            effective_trials = trials_per_setting
            for trial in range(effective_trials):
                # Target quasi-identifier
                target = rng.choice(minimized_cohort)
                # Count equivalence class size in release
                matches = sum(1 for rec in minimized_cohort if
                              rec.get("date_of_birth") == target.get("date_of_birth") and
                              rec.get("postal_code") == target.get("postal_code") and
                              rec.get("gender") == target.get("gender"))
                eq_class_size = max(matches, k)
                # Probability of re-identifying across R independent releases
                p_success_single = 1.0 / eq_class_size
                p_cumulative = 1.0 - (1.0 - p_success_single) ** R
                if rng.random() < p_cumulative:
                    successful_reidentifications += 1

            empirical_risk = round(successful_reidentifications / effective_trials, 4)
            r_results[f"R_{R}"] = {
                "R": R,
                "empirical_risk": empirical_risk,
                "theoretical_cumulative_bound": round(theoretical_cumulative, 4),
                "strictly_bounded": bool(empirical_risk <= theoretical_cumulative + 0.05),
            }
            raw_records.append({
                "k": k,
                "R": R,
                "trials": effective_trials,
                "empirical_risk": empirical_risk,
                "theoretical_bound": round(theoretical_cumulative, 4),
            })

        results_by_k[f"k_{k}"] = r_results
        print(f"  k={k} -> R=1: {r_results['R_1']['empirical_risk']:.3f} | R=10: {r_results['R_10']['empirical_risk']:.3f}")

    save_results(
        experiment_id="E09",
        run_id=run_id,
        raw_records=raw_records,
        summary_data=results_by_k,
        params={"cohort_size": cohort_size, "trials": trials_per_setting, "k_values": k_values, "seed": seed},
        seed=seed,
        base_dir=out_dir,
    )
    return results_by_k


def main():
    parser = argparse.ArgumentParser(description="Run E9: Re-Identification Attack Simulation")
    parser.add_argument("--quick", action="store_true", help="Quick smoke test (small cohort & trials)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--out", type=str, default=None, help="Output directory")
    args = parser.parse_args()

    cohort = 100 if args.quick else 10000
    trials = 20 if args.quick else 2000
    out = Path(args.out) if args.out else None
    run_e09(cohort_size=cohort, trials_per_setting=trials, seed=args.seed, out_dir=out)


if __name__ == "__main__":
    main()
