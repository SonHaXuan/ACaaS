"""
Offline Queue — persists access logs locally when the edge node is
disconnected from the cloud. On reconnection, drains to LogChain.
Uses monotonic sequence numbers to prevent replay (Section 4.4).
"""
from __future__ import annotations
import os, json, sqlite3, threading, time, hashlib

DB_PATH = os.environ.get("QUEUE_DB_PATH", "/tmp/acaas_queue.db")
_lock = threading.RLock()


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _init() -> None:
    with _lock, _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS log_queue (
                seq         INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_json  TEXT NOT NULL,
                entry_hash  TEXT NOT NULL,
                enqueued_at REAL NOT NULL,
                uploaded    INTEGER NOT NULL DEFAULT 0
            )
        """)
        c.commit()


_init()


def enqueue(entry: dict, edge_id: str | None = None) -> int:
    """Append a log entry with monotonic sequence number seq_e."""
    edge = edge_id or entry.get("edge_id") or os.environ.get("EDGE_NODE_ID", "edge-node-1")
    entry["edge_id"] = edge
    with _lock, _conn() as c:
        cur = c.execute(
            "INSERT INTO log_queue (entry_json, entry_hash, enqueued_at) VALUES (?,?,?)",
            ("{}", "", time.time())
        )
        seq = cur.lastrowid
        entry["seq_e"] = seq
        payload = json.dumps(entry, sort_keys=True)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        c.execute(
            "UPDATE log_queue SET entry_json=?, entry_hash=? WHERE seq=?",
            (payload, digest, seq)
        )
        c.commit()
    return seq


def pending() -> list[dict]:
    """Return all unuploaded entries in sequence order."""
    with _lock, _conn() as c:
        rows = c.execute(
            "SELECT seq, entry_json, entry_hash FROM log_queue "
            "WHERE uploaded=0 ORDER BY seq ASC"
        ).fetchall()
    return [{"seq": r["seq"], "entry": json.loads(r["entry_json"]),
             "hash": r["entry_hash"]} for r in rows]


def mark_uploaded(seq: int) -> None:
    with _lock, _conn() as c:
        c.execute("UPDATE log_queue SET uploaded=1 WHERE seq=?", (seq,))
        c.commit()


def drain_to_logchain(fabric_mock=None) -> int:
    """Upload pending entries to LogChain; returns count uploaded."""
    if fabric_mock is None:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))
        backend = os.environ.get("ACAAS_LEDGER_BACKEND", "").strip().lower()
        if backend == "redis":
            from blockchain.mock.ledger import RedisFabric
            fabric_mock = RedisFabric(
                redis_url=os.environ.get("ACAAS_REDIS_URL", "redis://localhost:6379/0"),
                prefix=os.environ.get("ACAAS_LEDGER_PREFIX", "acaas"),
            )
        else:
            from blockchain.mock import fabric as fab
            fabric_mock = fab

    entries = pending()
    count = 0
    for item in entries:
        log_payload = dict(item["entry"])
        if "seq_e" not in log_payload:
            log_payload["seq_e"] = item["seq"]
        log_payload["queue_seq"] = item["seq"]
        try:
            fabric_mock.append_log(log_payload)
            mark_uploaded(item["seq"])
            count += 1
        except Exception:
            break
    return count


def queue_size() -> int:
    with _lock, _conn() as c:
        row = c.execute(
            "SELECT COUNT(*) as n FROM log_queue WHERE uploaded=0"
        ).fetchone()
    return row["n"] if row else 0
