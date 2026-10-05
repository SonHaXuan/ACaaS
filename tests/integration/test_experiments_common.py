"""
Tests for experiments.common infrastructure (P1.1, P1.3, P1.4).
Verifies harness, statistical computations, workload generators, and I/O recording.
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path
import pytest

from experiments.common.harness import Timer, set_seed, retry_with_backoff, run_warmup
from experiments.common.stats import median, iqr, percentile, bootstrap_ci, calc_summary
from experiments.common.workload import (
    generate_subjects,
    generate_ehr_records,
    generate_policies,
    generate_access_requests,
)
from experiments.common.io import get_system_environment, save_results, load_summary
from experiments.common.wan import DEFAULT_PROXIES, ToxiproxyClient


def test_timer_precision():
    with Timer() as t:
        time.sleep(0.01)
    assert t.elapsed_ns > 0
    assert t.elapsed_us > 0
    assert t.elapsed_ms >= 5.0  # at least ~10ms


def test_seed_determinism():
    set_seed(12345)
    records1 = generate_ehr_records(n=5, seed=12345)
    set_seed(12345)
    records2 = generate_ehr_records(n=5, seed=12345)
    assert records1 == records2


def test_retry_with_backoff():
    attempts = [0]

    def flaky():
        attempts[0] += 1
        if attempts[0] < 3:
            raise ValueError("temporary error")
        return "success"

    res = retry_with_backoff(flaky, max_retries=5, initial_delay=0.01)
    assert res == "success"
    assert attempts[0] == 3


def test_stats_calculations():
    data = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert median(data) == 30.0
    assert percentile(data, 0.0) == 10.0
    assert percentile(data, 100.0) == 50.0
    assert iqr(data) == 20.0

    low, high = bootstrap_ci(data, ci=0.90, n_resamples=500, seed=42)
    assert low <= high
    assert 10.0 <= low <= 50.0

    summary = calc_summary(data)
    assert summary["count"] == 5
    assert summary["median"] == 30.0
    assert summary["min"] == 10.0
    assert summary["max"] == 50.0
    assert "ci_lower" in summary
    assert "ci_upper" in summary


def test_workload_generators():
    subs = generate_subjects(n=10, seed=42)
    assert len(subs) == 10
    assert "role" in subs[0]
    assert "clearance_level" in subs[0]

    ehrs = generate_ehr_records(n=10, seed=42, size_class="medium")
    assert len(ehrs) == 10
    assert "patient_id" in ehrs[0]
    assert "vitals" in ehrs[0]

    pols = generate_policies(n=5, seed=42)
    assert len(pols) == 5
    assert "rule" in pols[0]

    reqs = generate_access_requests(n=20, seed=42, permit_ratio=0.8)
    assert len(reqs) == 20
    assert "subject_id" in reqs[0]
    assert "action" in reqs[0]


def test_io_environment_and_saving():
    with tempfile.TemporaryDirectory() as tmp_dir:
        base_path = Path(tmp_dir)
        env = get_system_environment(seed=999, params={"mode": "test"})
        assert "os" in env
        assert "cpu" in env
        assert "git" in env
        assert "docker" in env
        assert env["seed"] == 999

        raw_data = [{"sample": 1, "val": 1.23}, {"sample": 2, "val": 4.56}]
        summary_data = {"median": 2.89, "count": 2}
        out_dir = save_results(
            experiment_id="E_TEST",
            run_id="run_01",
            raw_records=raw_data,
            summary_data=summary_data,
            params={"param1": 10},
            seed=999,
            base_dir=base_path,
        )

        assert (out_dir / "raw.csv").exists()
        assert (out_dir / "summary.json").exists()
        assert (out_dir / "env.json").exists()

        loaded_summary = load_summary("E_TEST", run_id="run_01", base_dir=base_path)
        assert loaded_summary == summary_data


def test_wan_default_proxies():
    assert "pms" in DEFAULT_PROXIES
    assert "cloud-pdp" in DEFAULT_PROXIES
    assert "sync-server" in DEFAULT_PROXIES
    client = ToxiproxyClient("http://127.0.0.1:8474")
    assert client.base_url == "http://127.0.0.1:8474"
