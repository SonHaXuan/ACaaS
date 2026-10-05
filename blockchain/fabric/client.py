"""
Hyperledger Fabric Gateway Client for ACaaS.
Interacts with the 4-peer ensemble Gateway Sidecar over HTTP/REST.

Supports:
- PolicyChain: commit_policy (with INV_mono on-chain check), get_policy, get_policy_version, verify_policy_hash.
- LogChain: append_log (with seq_e gap detection), get_logs.
- SyncChain: get_delta, get_current_global_seq, subscribe_sync.
- Fault Injection: set_byzantine_fault, get_ensemble_status.
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class _SidecarChannelView:
    """Provides channel-like query compatibility for callers expecting mock channel API."""

    def __init__(self, client: "FabricGatewayClient", channel_name: str):
        self._client = client
        self.name = channel_name

    def all(self) -> list[dict]:
        if self.name == "LogChain":
            return self._client.get_logs()
        elif self.name == "PolicyChain":
            return []
        elif self.name == "SyncChain":
            return self._client.get_delta(0)
        return []

    def query(self, key: str, value: Any) -> list[dict]:
        if self.name == "LogChain":
            if key == "subject_id":
                return self._client.get_logs(subject_id=value)
            if key == "patient_id":
                return self._client.get_logs(patient_id=value)
            return [r for r in self._client.get_logs() if r.get(key) == value]
        elif self.name == "PolicyChain":
            if key == "policy_id":
                pol = self._client.get_policy(value)
                return [pol] if pol else []
        return [r for r in self.all() if r.get(key) == value]

    def query_range(self, from_seq: int, to_seq: int) -> list[dict]:
        if self.name == "SyncChain":
            return self._client.get_delta(from_seq - 1, to_seq)
        return []

    def subscribe(self, callback: Callable[[dict], None]) -> None:
        if self.name == "SyncChain":
            self._client.subscribe_sync(callback)


class FabricGatewayClient:
    """
    Python client for Hyperledger Fabric Gateway Sidecar.
    Can be used interchangeably with FabricMock or RedisFabric.
    """

    def __init__(self, gateway_url: str | None = None, timeout: float = 10.0):
        url = gateway_url or os.environ.get("ACAAS_FABRIC_GATEWAY_URL", "http://localhost:7050")
        self.gateway_url = url.rstrip("/")
        self.timeout = timeout
        self.policy_chain = _SidecarChannelView(self, "PolicyChain")
        self.log_chain = _SidecarChannelView(self, "LogChain")
        self.sync_chain = _SidecarChannelView(self, "SyncChain")

        self._subscribers: list[Callable[[dict], None]] = []
        self._poller_thread: threading.Thread | None = None
        self._poller_running = False
        self._poller_lock = threading.Lock()
        self._last_observed_seq = 0

    def _request(self, method: str, path: str, payload: dict | None = None, params: dict | None = None) -> dict | list:
        url = f"{self.gateway_url}{path}"
        if params:
            query_str = urlencode({k: v for k, v in params.items() if v is not None})
            if query_str:
                url = f"{url}?{query_str}"

        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                resp_bytes = resp.read()
                if not resp_bytes:
                    return {}
                return json.loads(resp_bytes.decode("utf-8"))
        except HTTPError as e:
            err_body = e.read().decode("utf-8") if e.fp else ""
            if e.code == 409 or "INV_mono" in err_body:
                raise ValueError(err_body.strip()) from e
            elif e.code == 502 or "Endorsement policy not satisfied" in err_body:
                raise RuntimeError(f"Endorsement policy failed: {err_body.strip()}") from e
            elif e.code == 404:
                return {}
            raise RuntimeError(f"Fabric Sidecar error ({e.code}): {err_body.strip()}") from e
        except URLError as e:
            raise ConnectionError(f"Cannot connect to Fabric Gateway at {self.gateway_url}: {e.reason}") from e

    # ── Health & Diagnostics ──────────────────────────────────────────────

    def health(self) -> dict:
        return self._request("GET", "/health")

    def get_ensemble_status(self) -> dict:
        return self._request("GET", "/status")

    def set_byzantine_fault(self, faulty_peer: str = "peer0.org2", mode: str = "honest") -> dict:
        """
        Configure fault injection for E11:
        mode: 'honest' | 'passive' | 'rewind' | 'fork'
        """
        return self._request("POST", "/byzantine/configure", payload={"faulty_peer": faulty_peer, "mode": mode})

    # ── PolicyChain ───────────────────────────────────────────────────────

    def commit_policy(
        self,
        policy_id: str,
        policy_hash: str,
        issuer_sig: str = "",
        policy_body: dict | None = None,
        expected_prev_version: int | None = None,
    ) -> tuple[int, str]:
        """
        Commit a policy update through 4-peer ensemble endorsement.
        Enforces INV_mono on-chain. Returns (new_version, tx_id).
        """
        payload: dict[str, Any] = {
            "policy_id": policy_id,
            "hash": policy_hash,
            "issuer_sig": issuer_sig,
            "policy_body": policy_body,
        }
        if expected_prev_version is not None:
            payload["expected_prev_version"] = expected_prev_version

        res = self._request("POST", "/policies/commit", payload=payload)
        new_v = res.get("new_version", 1)
        tx_id = res.get("tx_id", "")
        return new_v, tx_id

    def delete_policy(self, policy_id: str) -> tuple[int, str]:
        res = self._request("POST", f"/policies/delete/{policy_id}")
        return res.get("new_version", 0), res.get("tx_id", "")

    def get_policy(self, policy_id: str) -> dict | None:
        res = self._request("GET", f"/policies/{policy_id}")
        return res if res else None

    def get_policy_version(self, policy_id: str) -> tuple[int, str]:
        res = self._request("GET", f"/policies/version/{policy_id}")
        return res.get("version", 0), res.get("hash", "")

    def verify_policy_hash(self, policy_id: str, version: int, expected_hash: str) -> bool:
        curr_ver, curr_hash = self.get_policy_version(policy_id)
        return curr_ver == version and curr_hash == expected_hash

    # ── LogChain ──────────────────────────────────────────────────────────

    def append_log(self, entry: dict) -> str:
        """
        Append an access audit record on-chain.
        Validates seq_e monotonicity and flags gaps. Returns tx_id.
        """
        res = self._request("POST", "/logs/append", payload=entry)
        return res.get("tx_id", "")

    def get_logs(self, subject_id: str | None = None, patient_id: str | None = None) -> list[dict]:
        params = {}
        if subject_id is not None:
            params["subject_id"] = subject_id
        if patient_id is not None:
            params["patient_id"] = patient_id
        res = self._request("GET", "/logs", params=params)
        return res if isinstance(res, list) else []

    # ── SyncChain ─────────────────────────────────────────────────────────

    def get_delta(self, from_version: int, to_version: int = 0) -> list[dict]:
        res = self._request("GET", "/policies/delta", params={"from_version": from_version, "to_version": to_version})
        return res if isinstance(res, list) else []

    def get_current_global_seq(self) -> int:
        status = self.get_ensemble_status()
        return status.get("current_global_seq", 0)

    def subscribe_sync(self, callback: Callable[[dict], None]) -> None:
        """Register a callback for SyncChain policy change events."""
        with self._poller_lock:
            self._subscribers.append(callback)
            if not self._poller_running:
                self._poller_running = True
                try:
                    self._last_observed_seq = self.get_current_global_seq()
                except Exception:
                    self._last_observed_seq = 0
                self._poller_thread = threading.Thread(target=self._poll_sync_events, daemon=True)
                self._poller_thread.start()

    def _poll_sync_events(self) -> None:
        while self._poller_running:
            try:
                events = self.get_delta(from_version=self._last_observed_seq)
                for ev in events:
                    seq = ev.get("global_seq", 0)
                    if seq > self._last_observed_seq:
                        self._last_observed_seq = seq
                    for cb in list(self._subscribers):
                        try:
                            cb(ev)
                        except Exception:
                            pass
            except Exception:
                pass
            time.sleep(0.2)

    def stop(self) -> None:
        self._poller_running = False
