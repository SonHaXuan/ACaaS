"""
Result I/O and Environmental Metadata capture for ACaaS experiments (P1.1 & P1.4).
Persists raw CSV data, statistical summaries (summary.json), and full reproduction
environment state (env.json).
"""
from __future__ import annotations

import csv
import json
import logging
import os
import platform
import subprocess
import time
from pathlib import Path
from typing import Any, Sequence

logger = logging.getLogger("acaas.io")

ROOT_DIR = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT_DIR / "results"


def get_git_info() -> dict[str, str]:
    """Retrieve current Git commit SHA, branch, and dirty status."""
    git_info = {"commit": "unknown", "branch": "unknown", "dirty": "unknown"}
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT_DIR), text=True, stderr=subprocess.DEVNULL
        ).strip()
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(ROOT_DIR), text=True, stderr=subprocess.DEVNULL
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=str(ROOT_DIR), text=True, stderr=subprocess.DEVNULL
        ).strip()
        git_info["commit"] = sha
        git_info["branch"] = branch
        git_info["dirty"] = "true" if status else "false"
    except Exception:
        pass
    return git_info


def get_docker_version() -> str:
    """Retrieve Docker client/server version."""
    try:
        out = subprocess.check_output(
            ["docker", "--version"], cwd=str(ROOT_DIR), text=True, stderr=subprocess.DEVNULL
        ).strip()
        return out
    except Exception:
        return "docker unavailable"


def get_system_environment(seed: int | None = None, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Capture full execution environment for reproducibility (P1.4).
    Contains CPU, RAM, OS, Docker version, Git SHA, and run parameters.
    """
    env_info: dict[str, Any] = {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "epoch_time": time.time(),
        "seed": seed,
        "parameters": params or {},
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "python_version": platform.python_version(),
        },
        "cpu": {
            "processor": platform.processor(),
            "cpu_count": os.cpu_count() or 1,
        },
        "git": get_git_info(),
        "docker": get_docker_version(),
    }

    # Optional Linux memory info via /proc/meminfo
    meminfo_path = Path("/proc/meminfo")
    if meminfo_path.exists():
        try:
            mem: dict[str, str] = {}
            for line in meminfo_path.read_text().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    if k.strip() in ("MemTotal", "MemAvailable", "MemFree"):
                        mem[k.strip()] = v.strip()
            env_info["memory"] = mem
        except Exception:
            pass

    return env_info


def save_results(
    experiment_id: str,
    run_id: str,
    raw_records: Sequence[dict[str, Any]],
    summary_data: dict[str, Any],
    params: dict[str, Any] | None = None,
    seed: int | None = None,
    base_dir: Path | None = None,
) -> Path:
    """
    Save raw.csv, summary.json, and env.json into results/<experiment_id>/<run_id>/.
    Returns output directory path.
    """
    out_dir = (base_dir or RESULTS_DIR) / experiment_id / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Write raw.csv
    raw_csv_path = out_dir / "raw.csv"
    if raw_records:
        fieldnames = list(raw_records[0].keys())
        with open(raw_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(raw_records)
    else:
        raw_csv_path.write_text("", encoding="utf-8")

    # 2. Write summary.json
    summary_path = out_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)

    # 3. Write env.json (P1.4)
    env_data = get_system_environment(seed=seed, params=params)
    env_path = out_dir / "env.json"
    with open(env_path, "w", encoding="utf-8") as f:
        json.dump(env_data, f, indent=2)

    logger.info(f"Saved experiment results to {out_dir}")
    return out_dir


def load_summary(experiment_id: str, run_id: str | None = None, base_dir: Path | None = None) -> dict[str, Any] | None:
    """Load summary.json from a given run or the latest run."""
    exp_dir = (base_dir or RESULTS_DIR) / experiment_id
    if not exp_dir.exists():
        return None
    if run_id:
        target = exp_dir / run_id / "summary.json"
    else:
        # Find latest directory
        runs = sorted([d for d in exp_dir.iterdir() if d.is_dir()], key=lambda d: d.stat().st_mtime)
        if not runs:
            return None
        target = runs[-1] / "summary.json"

    if target.exists():
        with open(target, "r", encoding="utf-8") as f:
            return json.load(f)
    return None
