"""
Edge Local Policy Store — SQLite-backed, offline-first.
Stores a synced subset of policies indexed by version and hash.
Implements consistency check: E_e(id) == L(id)  (Equation 3).
"""
from __future__ import annotations
import os, json, sqlite3, threading, hashlib, time
from dataclasses import asdict

DB_PATH = os.environ.get("EDGE_DB_PATH", "/tmp/acaas_edge.db")
_lock = threading.RLock()


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init() -> None:
    with _lock, _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS policies (
                policy_id   TEXT PRIMARY KEY,
                rule_json   TEXT NOT NULL,
                version     INTEGER NOT NULL,
                hash        TEXT NOT NULL,
                effect      TEXT NOT NULL,
                updated_at  REAL NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS sync_state (
                channel         TEXT PRIMARY KEY,
                last_version    INTEGER NOT NULL DEFAULT 0
            )
        """)
        c.commit()


def upsert(policy_id: str, rule_json: str, version: int,
           policy_hash: str, effect: str) -> None:
    with _lock, _conn() as c:
        c.execute("""
            INSERT INTO policies (policy_id, rule_json, version, hash, effect, updated_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(policy_id) DO UPDATE SET
              rule_json=excluded.rule_json,
              version=excluded.version,
              hash=excluded.hash,
              effect=excluded.effect,
              updated_at=excluded.updated_at
        """, (policy_id, rule_json, version, policy_hash, effect, time.time()))
        c.commit()


def delete(policy_id: str) -> None:
    with _lock, _conn() as c:
        c.execute("DELETE FROM policies WHERE policy_id=?", (policy_id,))
        c.commit()


def get(policy_id: str) -> dict | None:
    with _lock, _conn() as c:
        row = c.execute(
            "SELECT * FROM policies WHERE policy_id=?", (policy_id,)
        ).fetchone()
    return dict(row) if row else None


def list_all() -> list[dict]:
    with _lock, _conn() as c:
        rows = c.execute("SELECT * FROM policies").fetchall()
    return [dict(r) for r in rows]


def get_last_version(channel: str = "SyncChain") -> int:
    with _lock, _conn() as c:
        row = c.execute(
            "SELECT last_version FROM sync_state WHERE channel=?", (channel,)
        ).fetchone()
    return row["last_version"] if row else 0


def set_last_version(version: int, channel: str = "SyncChain") -> None:
    with _lock, _conn() as c:
        c.execute("""
            INSERT INTO sync_state (channel, last_version) VALUES (?,?)
            ON CONFLICT(channel) DO UPDATE SET last_version=excluded.last_version
        """, (channel, version))
        c.commit()


def verify_hash(policy_id: str, expected_hash: str) -> bool:
    """Implements E_e(id) == L(id) check (Eq. 3)."""
    row = get(policy_id)
    if not row:
        return False
    return row["hash"] == expected_hash
