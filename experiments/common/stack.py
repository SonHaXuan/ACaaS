"""
Docker Compose stack management utilities for ACaaS experiments.
Handles starting/stopping containers, scaling edge nodes, and polling health endpoints.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger("acaas.stack")

ROOT_DIR = Path(__file__).resolve().parents[2]
COMPOSE_BASE = ROOT_DIR / "docker-compose.yml"
COMPOSE_EXP = ROOT_DIR / "docker-compose.experiments.yml"

DEFAULT_HEALTH_ENDPOINTS = {
    "policy-manager": "http://localhost:8001/health",
    "cloud-pdp": "http://localhost:8002/health",
    "edge-pdp": "http://localhost:8003/health",
    "data-minimizer": "http://localhost:8004/health",
    "pep": "http://localhost:8005/health",
    "sync-server": "http://localhost:8006/health",
    "fog-cache": "http://localhost:8007/health",
    "fog-aggregation": "http://localhost:8008/health",
}


def run_command(cmd: list[str], cwd: Path = ROOT_DIR, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Execute shell command and capture output."""
    res = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if check and res.returncode != 0:
        raise RuntimeError(f"Command {' '.join(cmd)} failed (code {res.returncode}):\n{res.stderr}\n{res.stdout}")
    return res


def compose_up(
    use_experiments_overlay: bool = True,
    build: bool = False,
    scale: dict[str, int] | None = None,
) -> None:
    """Launch Docker Compose stack."""
    cmd = ["docker", "compose", "-f", str(COMPOSE_BASE)]
    if use_experiments_overlay and COMPOSE_EXP.exists():
        cmd.extend(["-f", str(COMPOSE_EXP)])
    cmd.extend(["up", "-d"])
    if build:
        cmd.append("--build")
    if scale:
        for srv, cnt in scale.items():
            cmd.extend(["--scale", f"{srv}={cnt}"])
    logger.info(f"Starting stack: {' '.join(cmd)}")
    run_command(cmd)


def compose_down(
    use_experiments_overlay: bool = True,
    remove_volumes: bool = False,
) -> None:
    """Tear down Docker Compose stack."""
    cmd = ["docker", "compose", "-f", str(COMPOSE_BASE)]
    if use_experiments_overlay and COMPOSE_EXP.exists():
        cmd.extend(["-f", str(COMPOSE_EXP)])
    cmd.append("down")
    if remove_volumes:
        cmd.append("-v")
    logger.info(f"Stopping stack: {' '.join(cmd)}")
    run_command(cmd)


def check_url(url: str, timeout: float = 2.0) -> bool:
    """Check if an HTTP endpoint returns 200 OK."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ACaaS-Healthcheck"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def wait_healthy(
    endpoints: dict[str, str] | None = None,
    timeout_sec: float = 60.0,
    interval_sec: float = 1.0,
) -> bool:
    """
    Poll health endpoints until all services respond 200 OK or timeout.
    """
    targets = endpoints or DEFAULT_HEALTH_ENDPOINTS
    deadline = time.time() + timeout_sec
    pending = set(targets.keys())

    logger.info(f"Waiting for {len(pending)} services to become healthy...")
    while time.time() < deadline:
        ready = set()
        for name in pending:
            url = targets[name]
            if check_url(url):
                ready.add(name)
        pending -= ready
        if not pending:
            logger.info("All services are healthy!")
            return True
        time.sleep(interval_sec)

    logger.error(f"Timed out waiting for services: {pending}")
    return False


def exec_container(container_name: str, cmd: list[str]) -> str:
    """Run command inside running container."""
    full_cmd = ["docker", "exec", container_name] + cmd
    res = run_command(full_cmd)
    return res.stdout.strip()
