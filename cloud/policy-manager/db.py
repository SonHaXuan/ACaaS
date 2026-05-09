"""
Policy storage layer.  Uses SQLite for dev; swap DATABASE_URL for PostgreSQL
in production (e.g. postgresql+asyncpg://user:pw@host/acaas).
"""
from __future__ import annotations
import os, json, sqlite3, threading, time
from dataclasses import asdict
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from shared.models.policy import Policy, PolicyRule, SubjectAttributes, ResourceAttributes, Condition, TimeRange

DB_PATH = os.environ.get("PMS_DB_PATH", "/tmp/acaas_pms.db")
_lock = threading.RLock()


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _lock, _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS policies (
                policy_id     TEXT PRIMARY KEY,
                rule_json     TEXT NOT NULL,
                version       INTEGER NOT NULL DEFAULT 1,
                hash          TEXT NOT NULL,
                issuer_sig    TEXT NOT NULL DEFAULT '',
                criticality   REAL NOT NULL DEFAULT 1.0,
                frequency     REAL NOT NULL DEFAULT 0.0,
                deployment_tier TEXT NOT NULL DEFAULT 'cloud',
                created_at    REAL NOT NULL,
                updated_at    REAL NOT NULL,
                deleted       INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.commit()


def upsert_policy(policy: Policy) -> Policy:
    policy.seal()
    with _lock, _get_conn() as conn:
        conn.execute("""
            INSERT INTO policies
              (policy_id, rule_json, version, hash, issuer_sig,
               criticality, frequency, deployment_tier, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(policy_id) DO UPDATE SET
              rule_json=excluded.rule_json,
              version=excluded.version,
              hash=excluded.hash,
              issuer_sig=excluded.issuer_sig,
              criticality=excluded.criticality,
              frequency=excluded.frequency,
              deployment_tier=excluded.deployment_tier,
              updated_at=excluded.updated_at,
              deleted=0
        """, (
            policy.policy_id,
            json.dumps(asdict(policy.rule)),
            policy.version,
            policy.hash,
            policy.issuer_sig,
            policy.criticality,
            policy.frequency,
            policy.deployment_tier,
            policy.created_at,
            policy.updated_at,
        ))
        conn.commit()
    return policy


def get_policy(policy_id: str) -> Policy | None:
    with _lock, _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM policies WHERE policy_id=? AND deleted=0",
            (policy_id,)
        ).fetchone()
    if not row:
        return None
    return _row_to_policy(row)


def list_policies() -> list[Policy]:
    with _lock, _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM policies WHERE deleted=0"
        ).fetchall()
    return [_row_to_policy(r) for r in rows]


def delete_policy(policy_id: str) -> bool:
    with _lock, _get_conn() as conn:
        cur = conn.execute(
            "UPDATE policies SET deleted=1, updated_at=? WHERE policy_id=?",
            (time.time(), policy_id)
        )
        conn.commit()
    return cur.rowcount > 0


def increment_frequency(policy_id: str) -> None:
    with _lock, _get_conn() as conn:
        conn.execute(
            "UPDATE policies SET frequency=frequency+1 WHERE policy_id=?",
            (policy_id,)
        )
        conn.commit()


def _row_to_policy(row: sqlite3.Row) -> Policy:
    rule_d = json.loads(row["rule_json"])
    tr = rule_d["condition"].get("time_range")
    cond = Condition(
        time_range=TimeRange(**tr) if tr else None,
        location=rule_d["condition"].get("location"),
        extra=rule_d["condition"].get("extra", {}),
    )
    rule = PolicyRule(
        subject=SubjectAttributes(**rule_d["subject"]),
        resource=ResourceAttributes(**rule_d["resource"]),
        action=rule_d["action"],
        condition=cond,
        effect=rule_d["effect"],
    )
    return Policy(
        policy_id=row["policy_id"],
        rule=rule,
        version=row["version"],
        hash=row["hash"],
        issuer_sig=row["issuer_sig"],
        criticality=row["criticality"],
        frequency=row["frequency"],
        deployment_tier=row["deployment_tier"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
