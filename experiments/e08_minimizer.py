#!/usr/bin/env python3
"""
E8: Data Minimizer Processing Cost Experiment (G3).
Paper parameters:
  - 1,000 records per size class (small, medium, large) through all three pipeline stages
    (pseudonymization, k-anonymity generalization, field redaction)
  - 10 warm-up runs discarded
  - Timing via perf_counter_ns
  - k-anonymity cohort scaling at k in {5, 10, 20}
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.common.harness import Timer, set_seed, run_warmup
from experiments.common.stats import calc_summary
from experiments.common.workload import generate_ehr_records
from experiments.common.io import save_results

# Import minimizer pipeline stages directly
MIN_DIR = str(ROOT / "edge" / "data-minimizer")
if MIN_DIR not in sys.path:
    sys.path.insert(0, MIN_DIR)
from pseudonymizer import pseudonymize_record
from k_anonymity import generalize_record, check_k_anonymity, enforce_k_anonymity
from field_redactor import redact


def run_e08(
    n_records: int = 1000,
    seed: int = 42,
    out_dir: Path | None = None,
) -> dict:
    set_seed(seed)
    run_id = f"run_{int(time.time())}"
    print(f"=== Running E8 (Data Minimizer Cost): N={n_records} records per size class ===")

    classes = ["small", "medium", "large"]
    size_results = {}
    raw_records = []

    for s_cls in classes:
        print(f"\n--- Testing size class: {s_cls} ({n_records} records) ---")
        records = generate_ehr_records(n=n_records, seed=seed, size_class=s_cls)

        def _run_single(r: dict) -> dict:
            r1 = pseudonymize_record(r)
            r2 = generalize_record(r1)
            r3 = redact(r2, role="doctor")
            return r3

        # Warm-up (10 runs discarded)
        run_warmup(lambda: _run_single(records[0]), n_warmup=10)

        s1_us_list = []
        s2_us_list = []
        s3_us_list = []
        total_us_list = []

        for i, rec in enumerate(records, 1):
            with Timer() as t1:
                r1 = pseudonymize_record(rec)
            us1 = t1.elapsed_us

            with Timer() as t2:
                r2 = generalize_record(r1)
            us2 = t2.elapsed_us

            with Timer() as t3:
                r3 = redact(r2, role="doctor")
            us3 = t3.elapsed_us

            tot = us1 + us2 + us3
            s1_us_list.append(us1)
            s2_us_list.append(us2)
            s3_us_list.append(us3)
            total_us_list.append(tot)

            raw_records.append({
                "size_class": s_cls,
                "record_id": i,
                "stage1_pseudo_us": round(us1, 2),
                "stage2_generalize_us": round(us2, 2),
                "stage3_redact_us": round(us3, 2),
                "total_us": round(tot, 2),
            })

        s1_summary = calc_summary(s1_us_list)
        s2_summary = calc_summary(s2_us_list)
        s3_summary = calc_summary(s3_us_list)
        tot_summary = calc_summary(total_us_list)

        size_results[s_cls] = {
            "size_class": s_cls,
            "stage1_pseudonymize": s1_summary,
            "stage2_generalize": s2_summary,
            "stage3_redact": s3_summary,
            "total_pipeline": tot_summary,
            "median_ms": round(tot_summary["median"] / 1000.0, 4),
            "p95_ms": round(tot_summary["p95"] / 1000.0, 4),
        }
        print(f"  Size '{s_cls}' -> Total Median: {tot_summary['median']:.1f} µs ({size_results[s_cls]['median_ms']:.3f} ms)")
        print(f"    Stage 1 (Pseudo): {s1_summary['median']:.1f} µs | Stage 2 (Gen): {s2_summary['median']:.1f} µs | Stage 3 (Redact): {s3_summary['median']:.1f} µs")

    # k-anonymity cohort scaling check (k in 5, 10, 20) with enforcement
    print("\n--- Testing k-anonymity scaling & enforcement (k in {5, 10, 20}) ---")
    k_results = {}
    cohort_raw = generate_ehr_records(n=min(n_records * 5, 5000), seed=seed)
    cohort = [generalize_record(r) for r in cohort_raw]
    qi_fields = ["date_of_birth", "postal_code", "ethnicity", "gender"]
    for k_val in [5, 10, 20]:
        with Timer() as t_check:
            is_valid, min_size = check_k_anonymity(cohort, qi_fields=qi_fields, k=k_val)
        with Timer() as t_enforce:
            sanitized, suppressed = enforce_k_anonymity(cohort_raw, qi_fields=qi_fields, k=k_val)
        k_results[f"k_{k_val}"] = {
            "k": k_val,
            "cohort_size": len(cohort),
            "verification_time_ms": round(t_check.elapsed_ms, 3),
            "satisfied": is_valid,
            "enforcement_time_ms": round(t_enforce.elapsed_ms, 3),
            "sanitized_count": len(sanitized),
            "suppressed_count": suppressed,
        }
        print(f"  k={k_val}: verification={t_check.elapsed_ms:.2f} ms (valid: {is_valid}), enforcement={t_enforce.elapsed_ms:.2f} ms (suppressed: {suppressed})")

    summary_all = {
        "pipeline_by_size_class": size_results,
        "k_anonymity_scaling": k_results,
    }

    save_results(
        experiment_id="E08",
        run_id=run_id,
        raw_records=raw_records,
        summary_data=summary_all,
        params={"n_records": n_records, "size_classes": classes, "seed": seed},
        seed=seed,
        base_dir=out_dir,
    )
    return summary_all


def main():
    parser = argparse.ArgumentParser(description="Run E8: Minimizer Processing Cost")
    parser.add_argument("--quick", action="store_true", help="Quick smoke test (20 records)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--out", type=str, default=None, help="Output directory")
    args = parser.parse_args()

    n = 20 if args.quick else 1000
    out = Path(args.out) if args.out else None
    run_e08(n_records=n, seed=args.seed, out_dir=out)


if __name__ == "__main__":
    main()
