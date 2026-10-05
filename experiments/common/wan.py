"""
Toxiproxy WAN client for ACaaS experiments (P1.2).
Provides programmatic control over network latency (e.g. 50 ms RTT)
and network partition/healing for edge-to-cloud communications.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger("acaas.wan")

TOXIPROXY_URL = os.environ.get("TOXIPROXY_URL", "http://localhost:8474")

DEFAULT_PROXIES = {
    "pms": {
        "listen": "0.0.0.0:18001",
        "upstream": "policy-manager:8001",
    },
    "cloud-pdp": {
        "listen": "0.0.0.0:18002",
        "upstream": "cloud-pdp:8002",
    },
    "sync-server": {
        "listen": "0.0.0.0:18006",
        "upstream": "sync-server:8006",
    },
}


class ToxiproxyClient:
    """Client for controlling Toxiproxy daemon."""

    def __init__(self, base_url: str = TOXIPROXY_URL) -> None:
        self.base_url = base_url.rstrip("/")

    def _request(self, method: str, path: str, payload: dict | None = None, timeout: float = 5.0) -> Any:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"} if data else {},
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
                return json.loads(body.decode("utf-8")) if body else None
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Toxiproxy HTTP {e.code} on {method} {path}: {err_body}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to connect to Toxiproxy at {url}: {e}") from e

    def is_alive(self) -> bool:
        """Check if Toxiproxy daemon is reachable."""
        try:
            self._request("GET", "/version")
            return True
        except Exception:
            return False

    def list_proxies(self) -> dict[str, Any]:
        """List all registered proxies."""
        return self._request("GET", "/proxies") or {}

    def ensure_proxy(self, name: str, listen: str, upstream: str) -> None:
        """Ensure a proxy is registered and listening."""
        existing = self.list_proxies()
        if name in existing:
            return
        payload = {
            "name": name,
            "listen": listen,
            "upstream": upstream,
            "enabled": True,
        }
        self._request("POST", "/proxies", payload)
        logger.info(f"Registered Toxiproxy proxy '{name}': {listen} -> {upstream}")

    def setup_default_proxies(self) -> None:
        """Register default ACaaS edge-to-cloud proxies."""
        for name, cfg in DEFAULT_PROXIES.items():
            self.ensure_proxy(name, cfg["listen"], cfg["upstream"])

    def set_latency(
        self,
        latency_ms: int = 50,
        jitter_ms: int = 0,
        proxy_names: list[str] | None = None,
        half_roundtrip: bool = True,
    ) -> None:
        """
        Apply latency toxic to proxies.
        If half_roundtrip is True, applies latency_ms / 2 in both upstream and downstream
        so the total added RTT is exactly latency_ms.
        """
        self.setup_default_proxies()
        targets = proxy_names or list(DEFAULT_PROXIES.keys())
        one_way_latency = int(latency_ms / 2) if half_roundtrip else latency_ms

        for p in targets:
            # Clear existing latency toxics
            self.remove_toxic(p, "wan_latency_downstream")
            self.remove_toxic(p, "wan_latency_upstream")

            if latency_ms <= 0:
                continue

            # Add downstream latency toxic
            downstream_toxic = {
                "name": "wan_latency_downstream",
                "type": "latency",
                "stream": "downstream",
                "toxicity": 1.0,
                "attributes": {
                    "latency": one_way_latency,
                    "jitter": jitter_ms,
                },
            }
            self._request("POST", f"/proxies/{p}/toxics", downstream_toxic)

            if half_roundtrip:
                upstream_toxic = {
                    "name": "wan_latency_upstream",
                    "type": "latency",
                    "stream": "upstream",
                    "toxicity": 1.0,
                    "attributes": {
                        "latency": one_way_latency,
                        "jitter": jitter_ms,
                    },
                }
                self._request("POST", f"/proxies/{p}/toxics", upstream_toxic)

            logger.info(f"Set WAN latency on '{p}': total RTT ≈ {latency_ms} ms (jitter {jitter_ms} ms)")

    def partition(self, proxy_names: list[str] | None = None) -> None:
        """
        Sever network connectivity by disabling the proxies.
        Causes immediate failure or timeout for traffic through the proxies.
        """
        self.setup_default_proxies()
        targets = proxy_names or list(DEFAULT_PROXIES.keys())
        for p in targets:
            self._request("POST", f"/proxies/{p}", {"enabled": False})
            logger.info(f"WAN severed (partitioned) on proxy '{p}'")

    def heal(self, proxy_names: list[str] | None = None, reapply_latency_ms: int = 50) -> None:
        """
        Restore network connectivity and optionally reapply standard WAN latency.
        """
        self.setup_default_proxies()
        targets = proxy_names or list(DEFAULT_PROXIES.keys())
        for p in targets:
            self._request("POST", f"/proxies/{p}", {"enabled": True})
            logger.info(f"WAN restored (healed) on proxy '{p}'")
        if reapply_latency_ms > 0:
            self.set_latency(reapply_latency_ms, proxy_names=targets)

    def remove_toxic(self, proxy_name: str, toxic_name: str) -> None:
        """Remove a toxic if it exists."""
        try:
            self._request("DELETE", f"/proxies/{proxy_name}/toxics/{toxic_name}")
        except Exception:
            pass

    def reset(self) -> None:
        """Reset all proxies to enabled and remove all toxics."""
        try:
            self._request("POST", "/reset")
            logger.info("Reset all Toxiproxy proxies to default clean state")
        except Exception:
            pass


# Module-level singleton instance
wan = ToxiproxyClient()


def set_wan_latency(latency_ms: int = 50, jitter_ms: int = 0) -> None:
    wan.set_latency(latency_ms, jitter_ms)


def partition_wan() -> None:
    wan.partition()


def heal_wan(latency_ms: int = 50) -> None:
    wan.heal(reapply_latency_ms=latency_ms)


def reset_wan() -> None:
    wan.reset()
