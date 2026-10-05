"""
Statistical computation utilities for ACaaS experiments.
Computes median, IQR, percentiles (P50, P90, P95, P99), and bootstrap CI.
"""
from __future__ import annotations

import math
import random
from typing import Sequence


def percentile(data: Sequence[float], p: float) -> float:
    """Compute the p-th percentile (0 <= p <= 100) using linear interpolation."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    n = len(sorted_data)
    if n == 1:
        return sorted_data[0]
    rank = (p / 100.0) * (n - 1)
    k = math.floor(rank)
    d = rank - k
    if k + 1 < n:
        return sorted_data[k] + d * (sorted_data[k + 1] - sorted_data[k])
    return sorted_data[-1]


def median(data: Sequence[float]) -> float:
    """Compute the median of numeric sequence."""
    return percentile(data, 50.0)


def iqr(data: Sequence[float]) -> float:
    """Compute the Interquartile Range (IQR = Q75 - Q25)."""
    if not data:
        return 0.0
    q75 = percentile(data, 75.0)
    q25 = percentile(data, 25.0)
    return q75 - q25


def bootstrap_ci(
    data: Sequence[float],
    ci: float = 0.95,
    n_resamples: int = 1000,
    seed: int = 42,
) -> tuple[float, float]:
    """
    Compute non-parametric bootstrap confidence interval for the median (or mean).
    Returns (lower_bound, upper_bound).
    """
    if not data:
        return 0.0, 0.0
    if len(data) == 1:
        return data[0], data[0]

    rng = random.Random(seed)
    n = len(data)
    medians: list[float] = []

    for _ in range(n_resamples):
        sample = [data[rng.randint(0, n - 1)] for _ in range(n)]
        medians.append(median(sample))

    alpha = (1.0 - ci) / 2.0
    lower = percentile(medians, alpha * 100.0)
    upper = percentile(medians, (1.0 - alpha) * 100.0)
    return round(lower, 4), round(upper, 4)


def calc_summary(data: Sequence[float], ci: float = 0.95) -> dict[str, float]:
    """
    Compute comprehensive summary statistics for experiment metrics.
    """
    if not data:
        return {
            "count": 0, "mean": 0.0, "std": 0.0,
            "median": 0.0, "iqr": 0.0,
            "p25": 0.0, "p75": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0,
            "min": 0.0, "max": 0.0,
            "ci_lower": 0.0, "ci_upper": 0.0,
        }

    n = len(data)
    mean_val = sum(data) / n
    variance = sum((x - mean_val) ** 2 for x in data) / (n - 1) if n > 1 else 0.0
    std_val = math.sqrt(variance)

    q25 = percentile(data, 25.0)
    q50 = percentile(data, 50.0)
    q75 = percentile(data, 75.0)
    p90 = percentile(data, 90.0)
    p95 = percentile(data, 95.0)
    p99 = percentile(data, 99.0)
    iqr_val = q75 - q25
    ci_low, ci_high = bootstrap_ci(data, ci=ci)

    return {
        "count": n,
        "mean": round(mean_val, 4),
        "std": round(std_val, 4),
        "median": round(q50, 4),
        "iqr": round(iqr_val, 4),
        "p25": round(q25, 4),
        "p75": round(q75, 4),
        "p90": round(p90, 4),
        "p95": round(p95, 4),
        "p99": round(p99, 4),
        "min": round(min(data), 4),
        "max": round(max(data), 4),
        "ci_lower": ci_low,
        "ci_upper": ci_high,
    }
