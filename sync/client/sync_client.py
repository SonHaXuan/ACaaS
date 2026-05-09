"""
ACaaS Edge Sync Client.
Connects to the Policy Sync Server and maintains the Local Policy Store.
Handles three states per Section 4.4:
  NORMAL         — subscribed, writes logs in real time
  OFFLINE        — enforces cached policies, queues logs
  RECONNECT-AND-SYNC — executes Phase C delta, drains log buffer
"""
from __future__ import annotations
import sys, os, json, time, threading, logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../edge/local-policy-store"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../edge/offline-queue"))

import urllib.request, urllib.error
import store
import offline_queue as offline_q

logger = logging.getLogger("sync-client")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(name)s] %(levelname)s %(message)s")

SYNC_SERVER_URL = os.environ.get("SYNC_SERVER_URL", "http://localhost:8006")
HEARTBEAT_SEC   = float(os.environ.get("HEARTBEAT_SEC", "5"))
PMS_URL         = os.environ.get("PMS_URL", "http://policy-manager:8001")


class EdgeState:
    NORMAL = "NORMAL"
    OFFLINE = "OFFLINE"
    RECONNECT_AND_SYNC = "RECONNECT-AND-SYNC"


class SyncClient:
    def __init__(self, edge_node_id: str):
        self.edge_node_id = edge_node_id
        self.state = EdgeState.OFFLINE
        self._stop = threading.Event()
        store.init()

    # ── connectivity helpers ──────────────────────────────────────────────

    def _get(self, path: str, timeout: int = 3) -> dict | None:
        try:
            url = f"{SYNC_SERVER_URL}{path}"
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                return json.loads(resp.read())
        except Exception:
            return None

    def _post(self, path: str, payload: dict, timeout: int = 3) -> dict | None:
        try:
            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                f"{SYNC_SERVER_URL}{path}", data=data,
                headers={"Content-Type": "application/json"}, method="POST"
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except Exception:
            return None

    def _heartbeat(self) -> bool:
        result = self._get("/health")
        return result is not None

    # ── sync operations ───────────────────────────────────────────────────

    def _apply_event(self, event: dict) -> None:
        """Apply a single PolicyUpdateEvent to the local store."""
        pid    = event.get("policy_id", "")
        ev_type = event.get("event_type", "UPDATE")
        new_v  = event.get("new_version", 0)
        phash  = event.get("hash", "")

        if ev_type == "DELETE":
            store.delete(pid)
            logger.info(f"[{self.edge_node_id}] deleted policy {pid}")
            return

        # Fetch full policy body if not embedded
        body = event.get("policy_body")
        if not body:
            try:
                with urllib.request.urlopen(f"{PMS_URL}/policies/{pid}", timeout=3) as resp:
                    policy_data = json.loads(resp.read())
                body = policy_data.get("rule", {})
            except Exception:
                body = {}

        body_str = body if isinstance(body, str) else json.dumps(body, sort_keys=True)

        # Verify hash before applying (Section 4.2)
        import hashlib
        computed = hashlib.sha256(body_str.encode()).hexdigest()
        if phash and computed != phash:
            logger.warning(
                f"[{self.edge_node_id}] skipped policy {pid} v{new_v}: hash mismatch"
            )
            return
        effect = body.get("effect", "PERMIT") if isinstance(body, dict) else "PERMIT"
        store.upsert(
            policy_id=pid,
            rule_json=body_str,
            version=new_v,
            policy_hash=phash,
            effect=effect,
        )
        store.set_last_version(new_v)
        self._post(f"/ack/{self.edge_node_id}?policy_id={pid}&version={new_v}", {})
        logger.info(
            f"[{self.edge_node_id}] applied policy {pid} v{new_v}"
        )

    def register(self) -> bool:
        last_v = store.get_last_version()
        result = self._post("/register", {
            "edge_node_id": self.edge_node_id,
            "last_known_version": last_v,
        })
        return result is not None

    def delta_sync(self) -> int:
        """Phase C: pull missed events and apply atomically."""
        last_v = store.get_last_version()
        result = self._get(
            f"/delta/{self.edge_node_id}?from_version={last_v}&to_version=0"
        )
        if not result:
            return 0
        events = result.get("events", [])
        for ev in sorted(events, key=lambda e: e.get("new_version", 0)):
            self._apply_event(ev)
        count = len(events)
        if count:
            logger.info(f"[{self.edge_node_id}] delta sync: applied {count} events")
        return count

    def drain_logs(self) -> int:
        """Upload queued offline logs to LogChain."""
        count = offline_q.drain_to_logchain()
        if count:
            logger.info(f"[{self.edge_node_id}] drained {count} log entries to LogChain")
        return count

    # ── state machine ─────────────────────────────────────────────────────

    def run(self) -> None:
        logger.info(f"[{self.edge_node_id}] sync client starting")
        while not self._stop.is_set():
            online = self._heartbeat()

            if not online:
                if self.state != EdgeState.OFFLINE:
                    logger.warning(f"[{self.edge_node_id}] → OFFLINE")
                    self.state = EdgeState.OFFLINE
            else:
                if self.state == EdgeState.OFFLINE:
                    logger.info(f"[{self.edge_node_id}] → RECONNECT-AND-SYNC")
                    self.state = EdgeState.RECONNECT_AND_SYNC
                    self.register()
                    self.delta_sync()
                    self.drain_logs()
                    self.state = EdgeState.NORMAL
                    logger.info(f"[{self.edge_node_id}] → NORMAL")
                elif self.state == EdgeState.NORMAL:
                    # Incremental poll (replaces long-lived gRPC stream for simplicity)
                    self.delta_sync()
                    self.drain_logs()

            self._stop.wait(HEARTBEAT_SEC)

    def start(self) -> threading.Thread:
        t = threading.Thread(target=self.run, daemon=True)
        t.start()
        return t

    def stop(self) -> None:
        self._stop.set()


if __name__ == "__main__":
    node_id = os.environ.get("EDGE_NODE_ID", "edge-node-1")
    client = SyncClient(node_id)
    try:
        client.run()
    except KeyboardInterrupt:
        client.stop()
