"""
Plotting utilities for ACaaS publication-quality figures.
Generates vector PDF and high-res PNG plots for experiment results.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "results"


def plot_e01_latency(results_dir: Path | None = None) -> Path | None:
    """Generate latency CDF and boxplot for E1."""
    e01_dir = (results_dir or RESULTS_DIR) / "E01"
    if not e01_dir.exists():
        return None

    # Find latest run
    runs = sorted([d for d in e01_dir.iterdir() if d.is_dir()], key=lambda d: d.stat().st_mtime)
    if not runs:
        return None
    latest_run = runs[-1]
    raw_csv = latest_run / "raw.csv"
    if not raw_csv.exists():
        return None

    latencies = []
    with open(raw_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            latencies.append(float(row["latency_ms"]))

    if not latencies:
        return None

    sorted_lats = sorted(latencies)
    n = len(sorted_lats)
    cdf = [i / n for i in range(1, n + 1)]

    # Publication style
    plt.figure(figsize=(6, 4))
    plt.plot(sorted_lats, cdf, color="#1f77b4", linewidth=2, label="Measured E2E Latency")
    plt.axvline(sorted_lats[int(n * 0.5)], color="#d62728", linestyle="--", label=f"Median ({sorted_lats[int(n*0.5)]:.2f} ms)")
    plt.xlabel("End-to-End Latency (ms)", fontsize=11)
    plt.ylabel("Cumulative Probability (CDF)", fontsize=11)
    plt.title("E1: ACaaS Decision Latency Distribution (50 ms WAN)", fontsize=12, fontweight="bold")
    plt.grid(True, linestyle=":", alpha=0.6)
    plt.legend(loc="lower right")
    plt.tight_layout()

    out_pdf = latest_run / "e01_latency_cdf.pdf"
    out_png = latest_run / "e01_latency_cdf.png"
    plt.savefig(out_pdf, format="pdf")
    plt.savefig(out_png, format="png", dpi=300)
    plt.close()

    print(f"Generated plots:\n  {out_pdf}\n  {out_png}")
    return out_pdf


if __name__ == "__main__":
    plot_e01_latency()
