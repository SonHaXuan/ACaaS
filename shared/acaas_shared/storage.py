from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from acaas_shared.models import PolicyRecord


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


class JsonPolicyStore:
    def __init__(self, path: str):
        self.path = Path(path)
        ensure_parent(self.path)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def load_all(self) -> list[PolicyRecord]:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return [PolicyRecord.model_validate(item) for item in raw]

    def save_all(self, policies: list[PolicyRecord]) -> None:
        payload = [policy.model_dump(mode="json") for policy in policies]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class SqliteEdgePolicyStore:
    def __init__(self, path: str):
        self.path = Path(path)
        ensure_parent(self.path)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS policies (
                    policy_id TEXT PRIMARY KEY,
                    version INTEGER NOT NULL,
                    hash TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def upsert(self, policy: PolicyRecord) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                INSERT INTO policies(policy_id, version, hash, payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(policy_id) DO UPDATE SET
                    version = excluded.version,
                    hash = excluded.hash,
                    payload = excluded.payload
                """,
                (
                    policy.policy_id,
                    policy.version,
                    policy.hash,
                    json.dumps(policy.model_dump(mode="json")),
                ),
            )
            conn.commit()

    def list_all(self) -> list[PolicyRecord]:
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute("SELECT payload FROM policies").fetchall()
        return [PolicyRecord.model_validate(json.loads(row[0])) for row in rows]

    def latest_version(self) -> int:
        with sqlite3.connect(self.path) as conn:
            row = conn.execute("SELECT COALESCE(MAX(version), 0) FROM policies").fetchone()
        return int(row[0] or 0)

