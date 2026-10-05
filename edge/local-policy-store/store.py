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
_global_conn = None
_current_db_path = None
_initialized = False

def close() -> None:
    global _global_conn, _current_db_path, _initialized
    with _lock:
        if _global_conn is not None:
            try:
                _global_conn.close()
            except Exception:
                pass
            _global_conn = None
            _current_db_path = None
            _initialized = False

def _conn() -> sqlite3.Connection:
    global _global_conn, _current_db_path, _initialized
    with _lock:
        if _global_conn is None or _current_db_path != DB_PATH:
            close()
            _global_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
            _global_conn.row_factory = sqlite3.Row
            _current_db_path = DB_PATH
            init()
        return _global_conn


def init() -> None:
    global _global_conn, _current_db_path
    with _lock:
        if _global_conn is None or _current_db_path != DB_PATH:
            _global_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
            _global_conn.row_factory = sqlite3.Row
            _current_db_path = DB_PATH
        with _global_conn as c:
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
                    last_global_seq INTEGER NOT NULL DEFAULT 0
                )
            """)
            try:
                c.execute("ALTER TABLE sync_state ADD COLUMN last_global_seq INTEGER NOT NULL DEFAULT 0")
            except Exception:
                pass
            c.commit()


def upsert(policy_id: str, rule_json: str, version: int,
           policy_hash: str, effect: str) -> bool:
    """
    Inserts or updates a policy in the local store.
    Enforces INV_mono: returns False and rejects the update if version <= current version.
    """
    with _lock, _conn() as c:
        existing = c.execute("SELECT version FROM policies WHERE policy_id=?", (policy_id,)).fetchone()
        if existing and version <= existing["version"]:
            # Rollback / non-monotonic update rejected per INV_mono (Section 3.2 / P0.4)
            return False

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
    return True


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


def get_last_global_seq(channel: str = "SyncChain") -> int:
    with _lock, _conn() as c:
        row = c.execute(
            "SELECT last_global_seq FROM sync_state WHERE channel=?", (channel,)
        ).fetchone()
    return row["last_global_seq"] if row else 0


def set_last_global_seq(seq: int, channel: str = "SyncChain") -> None:
    with _lock, _conn() as c:
        c.execute("""
            INSERT INTO sync_state (channel, last_global_seq) VALUES (?,?)
            ON CONFLICT(channel) DO UPDATE SET last_global_seq=excluded.last_global_seq
        """, (channel, seq))
        c.commit()


def get_last_version(channel: str = "SyncChain") -> int:
    return get_last_global_seq(channel)


def set_last_version(version: int, channel: str = "SyncChain") -> None:
    set_last_global_seq(version, channel)



def verify_hash(policy_id: str, expected_hash: str) -> bool:
    """Implements E_e(id) == L(id) check (Eq. 3)."""
    row = get(policy_id)
    if not row:
        return False
    return row["hash"] == expected_hash
