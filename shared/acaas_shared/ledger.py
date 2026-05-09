from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from acaas_shared.models import AuditEvent, PolicyRecord


def canonical_policy_hash(policy: PolicyRecord) -> str:
    content = json.dumps(policy.rule.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class FileLedger:
    def __init__(self, policy_state_path: str, audit_log_path: str):
        self.policy_state_path = Path(policy_state_path)
        self.audit_log_path = Path(audit_log_path)
        self.policy_state_path.parent.mkdir(parents=True, exist_ok=True)
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.policy_state_path.exists():
            self.policy_state_path.write_text("{}", encoding="utf-8")
        if not self.audit_log_path.exists():
            self.audit_log_path.write_text("", encoding="utf-8")

    def _load_policy_state(self) -> dict[str, Any]:
        return json.loads(self.policy_state_path.read_text(encoding="utf-8"))

    def commit_policy(self, policy: PolicyRecord) -> None:
        state = self._load_policy_state()
        state[policy.policy_id] = {
            "version": policy.version,
            "hash": policy.hash,
            "updated_at": policy.updated_at,
        }
        self.policy_state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def policy_state(self) -> dict[str, Any]:
        return self._load_policy_state()

    def append_audit_event(self, event: AuditEvent) -> None:
        with self.audit_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.model_dump(mode="json")) + "\n")

    def list_audit_events(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for line in self.audit_log_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entries.append(json.loads(line))
        return entries

