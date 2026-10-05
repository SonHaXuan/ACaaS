"""
Harness utilities for ACaaS experiments.
Provides deterministic seed control, high-precision timing (perf_counter_ns),
retries with backoff, warm-up iteration handling, and time-scale-aware sleep.
"""
from __future__ import annotations

import os
import random
import time
from typing import Any, Callable, TypeVar

T = TypeVar("T")

TIME_SCALE = float(os.environ.get("ACAAS_TIME_SCALE", "1.0"))


def set_seed(seed: int = 42) -> None:
    """Set global random seed across standard library and optional scientific libs."""
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except ImportError:
        pass


def time_scale_sleep(seconds: float) -> None:
    """Sleep for specified duration scaled by ACAAS_TIME_SCALE."""
    time.sleep(seconds * TIME_SCALE)


class Timer:
    """
    High-precision monotonic execution timer using time.perf_counter_ns().
    Usage:
        with Timer() as t:
            do_work()
        print(t.elapsed_ms, t.elapsed_us, t.elapsed_ns)
    """
    def __init__(self) -> None:
        self.start_ns: int = 0
        self.end_ns: int = 0
        self.elapsed_ns: int = 0

    def __enter__(self) -> "Timer":
        self.start_ns = time.perf_counter_ns()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.end_ns = time.perf_counter_ns()
        self.elapsed_ns = self.end_ns - self.start_ns

    @property
    def elapsed_us(self) -> float:
        return self.elapsed_ns / 1_000.0

    @property
    def elapsed_ms(self) -> float:
        return self.elapsed_ns / 1_000_000.0

    @property
    def elapsed_sec(self) -> float:
        return self.elapsed_ns / 1_000_000_000.0


def measure_callable(fn: Callable[[], T]) -> tuple[T, float]:
    """Execute fn and return (result, latency_ms)."""
    with Timer() as t:
        res = fn()
    return res, t.elapsed_ms


def run_warmup(fn: Callable[[], Any], n_warmup: int = 10) -> None:
    """Run warm-up invocations and discard latency measurements."""
    for _ in range(n_warmup):
        try:
            fn()
        except Exception:
            pass


def retry_with_backoff(
    fn: Callable[[], T],
    max_retries: int = 5,
    initial_delay: float = 0.1,
    backoff_factor: float = 2.0,
    expected_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """Execute fn with exponential backoff on failure."""
    delay = initial_delay * TIME_SCALE
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            return fn()
        except expected_exceptions as ex:
            last_err = ex
            if attempt == max_retries - 1:
                break
            time.sleep(delay)
            delay *= backoff_factor
    if last_err is not None:
        raise last_err
    raise RuntimeError("Retry failed without exception")
