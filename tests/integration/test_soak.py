"""
Tests for E12 Three-Site Soak Simulation (Phase P5).
Verifies deterministic schedule generation, partition intervals,
zero-loss ledger reconciliation, and Table S-Soak outputs.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import pytest

from experiments.e12_soak import run_e12, load_or_generate_schedule

ROOT = Path(__file__).resolve().parents[2]


def test_schedule_deterministic_structure():
    """Verify schedule.json conforms to paper specifications."""
    schedule = load_or_generate_schedule()
    assert schedule["simulated_minutes"] == 720
    assert schedule["seed"] == 20260704
    assert len(schedule["policy_updates"]) == 29
    assert len(schedule["sites"]) == 3

    urban = schedule["sites"]["urban_ward"]
    clinic = schedule["sites"]["district_clinic"]
    mobile = schedule["sites"]["mobile_unit"]

    assert urban["req_per_min"] == 18
    assert clinic["req_per_min"] == 12
    assert mobile["req_per_min"] == 8


def test_e12_soak_run_metrics(tmp_path):
    """Run E12 soak and verify outputs match logical constraints of the schedule."""
    summaries = run_e12(simulated_minutes=720, seed=20260704, quick=False, out_dir=tmp_path)
    schedule = load_or_generate_schedule()

    # Site 1: Urban
    urban = summaries["urban_ward"]
    assert urban["requests"] == 18 * 720
    assert urban["avail_pct"] == 100.0
    assert urban["partitions"] == len(schedule["sites"]["urban_ward"]["partitions"])
    assert urban["offline_dec"] == sum((e - s + 1) * 18 for s, e in schedule["sites"]["urban_ward"]["partitions"])

    # Site 2: Clinic
    clinic = summaries["district_clinic"]
    assert clinic["requests"] == 12 * 720
    assert clinic["avail_pct"] == 100.0
    assert clinic["partitions"] == len(schedule["sites"]["district_clinic"]["partitions"])
    assert clinic["offline_dec"] == sum((e - s + 1) * 12 for s, e in schedule["sites"]["district_clinic"]["partitions"])

    # Site 3: Mobile
    mobile = summaries["mobile_unit"]
    assert mobile["requests"] == 8 * 720
    assert mobile["avail_pct"] == 100.0
    assert mobile["partitions"] == len(schedule["sites"]["mobile_unit"]["partitions"])
    assert mobile["offline_dec"] == sum((e - s + 1) * 8 for s, e in schedule["sites"]["mobile_unit"]["partitions"])

    # Aggregate
    agg = summaries["aggregate"]
    assert agg["requests"] == (18 + 12 + 8) * 720
    assert agg["avail_pct"] == 100.0
    assert agg["zero_loss_satisfied"] is True
    assert agg["total_logchain_entries"] == agg["requests"]

    # Output file verifications
    assert (tmp_path / "table_s_soak.csv").exists()
    assert (tmp_path / "tab_s_soak.tex").exists()
    assert (tmp_path / "summary.json").exists()

    with open(tmp_path / "table_s_soak.csv") as f:
        reader = list(csv.reader(f))
        assert len(reader) == 5  # header + 3 sites + aggregate
        assert reader[0][0] == "Site"
        assert reader[4][1] == str(agg["requests"])

