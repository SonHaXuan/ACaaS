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
TIME_SCALE      = float(os.environ.get("ACAAS_TIME_SCALE", "1.0"))


class EdgeState:
    NORMAL = "NORMAL"
    OFFLINE = "OFFLINE"
    RECONNECT_AND_SYNC = "RECONNECT-AND-SYNC"


class SyncClient:
    def __init__(self, edge_node_id: str):
        self.edge_node_id = edge_node_id
        self.state = EdgeState.OFFLINE
        self.rollback_rejected = 0
        self._stop = threading.Event()
        self._stream_thread: threading.Thread | None = None
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
        pid     = event.get("policy_id", "")
        ev_type = event.get("event_type", "UPDATE")
        new_v   = event.get("new_version", 0)
        phash   = event.get("hash", "")
        gseq    = event.get("global_seq", 0)

        if ev_type == "DELETE":
            store.delete(pid)
            if gseq > 0:
                store.set_last_global_seq(gseq)
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

        # Apply with INV_mono check
        success = store.upsert(
            policy_id=pid,
            rule_json=body_str,
            version=new_v,
            policy_hash=phash,
            effect=effect,
        )
        if not success:
            self.rollback_rejected += 1
            logger.warning(
                f"[{self.edge_node_id}] REJECT_ROLLBACK: policy {pid} v{new_v} rejected by INV_mono"
            )
            return

        if gseq > 0:
            store.set_last_global_seq(gseq)
        else:
            store.set_last_global_seq(new_v)

        self._post(f"/ack/{self.edge_node_id}?policy_id={pid}&version={new_v}&global_seq={gseq}", {})
        logger.info(
            f"[{self.edge_node_id}] applied policy {pid} v{new_v} (global_seq={gseq})"
        )

    def register(self) -> bool:
        last_seq = store.get_last_global_seq()
        result = self._post("/register", {
            "edge_node_id": self.edge_node_id,
            "last_known_global_seq": last_seq,
            "last_known_version": last_seq,
        })
        return result is not None

    def delta_sync(self) -> int:
        """Phase C: pull missed events and apply atomically."""
        last_seq = store.get_last_global_seq()
        result = self._get(
            f"/delta/{self.edge_node_id}?from_version={last_seq}&to_version=0"
        )
        if not result:
            return 0
        events = result.get("events", [])
        # Sort delta chronologically by global sequence number
        for ev in sorted(events, key=lambda e: e.get("global_seq", 0)):
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

    def _sse_stream_worker(self) -> None:
        """Phase B: SSE background subscriber."""
        last_seq = store.get_last_global_seq()
        url = f"{SYNC_SERVER_URL}/stream/{self.edge_node_id}?last_version={last_seq}"
        req = urllib.request.Request(url, headers={"Accept": "text/event-stream"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                for raw_line in resp:
                    if self._stop.is_set() or self.state != EdgeState.NORMAL:
                        break
                    line = raw_line.decode("utf-8").strip()
                    if line.startswith("data:"):
                        data_part = line[5:].strip()
                        if data_part:
                            try:
                                ev = json.loads(data_part)
                                self._apply_event(ev)
                                self.drain_logs()
                            except Exception as ex:
                                logger.error(f"Error parsing SSE event: {ex}")
        except Exception:
            pass  # connection closed or timed out, will retry in state loop

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
                    # Maintain Phase B SSE stream
                    if self._stream_thread is None or not self._stream_thread.is_alive():
                        self._stream_thread = threading.Thread(target=self._sse_stream_worker, daemon=True)
                        self._stream_thread.start()
                    # Incremental log drain
                    self.drain_logs()

            self._stop.wait(HEARTBEAT_SEC * TIME_SCALE)


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
