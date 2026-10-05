"""
Simulated Hyperledger Fabric network with three channels:
  - PolicyChain : stores (policy_id, hash, version, issuer_sig)
  - LogChain    : stores immutable access log entries
  - SyncChain   : carries policy update events for edge subscription

In production, replace this with the Hyperledger Fabric Python SDK
connecting to a real 4-peer Raft-consensus network (Section 4.2).
"""
from __future__ import annotations
import hashlib, json, os, threading, time
from collections import defaultdict
from typing import Any, Callable


class _Channel:
    """Append-only ledger channel with subscriber notifications."""

    def __init__(self, name: str):
        self.name = name
        self._records: list[dict] = []
        self._subscribers: list[Callable[[dict], None]] = []
        self._lock = threading.RLock()

    def commit(self, record: dict) -> str:
        """Append a record; returns its tx_id."""
        with self._lock:
            tx_id = hashlib.sha256(
                json.dumps(record, sort_keys=True).encode()
            ).hexdigest()[:16]
            entry = {**record, "tx_id": tx_id, "committed_at": time.time(),
                     "block_number": len(self._records)}
            self._records.append(entry)
        for sub in list(self._subscribers):
            try:
                sub(entry)
            except Exception:
                pass
        return tx_id

    def query(self, key: str, value: Any) -> list[dict]:
        with self._lock:
            return [r for r in self._records if r.get(key) == value]

    def query_range(self, from_seq: int, to_seq: int) -> list[dict]:
        """Filter by global_seq range (inclusive)."""
        with self._lock:
            return [
                r for r in self._records
                if from_seq <= r.get("global_seq", 0) <= to_seq
            ]

    def all(self) -> list[dict]:
        with self._lock:
            return list(self._records)

    def subscribe(self, callback: Callable[[dict], None]) -> None:
        self._subscribers.append(callback)


class FabricMock:
    """
    Singleton simulated Hyperledger Fabric node.
    Three channels: PolicyChain, LogChain, SyncChain.
    """
    _instance: "FabricMock | None" = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst.policy_chain = _Channel("PolicyChain")
                inst.log_chain = _Channel("LogChain")
                inst.sync_chain = _Channel("SyncChain")
                # version counter per policy_id (for per-policy monotonicity)
                inst._versions: dict[str, int] = defaultdict(int)
                inst._version_lock = threading.Lock()
                # global sync event sequence (monotonic across all policies)
                inst._global_seq: int = 0
                inst._seq_lock = threading.Lock()
                cls._instance = inst
            return cls._instance

    # ── PolicyChain chaincode ─────────────────────────────────────────────

    def commit_policy(self, policy_id: str, policy_hash: str,
                      issuer_sig: str = "", policy_body: dict | None = None,
                      expected_prev_version: int | None = None) -> tuple[int, str]:
        """
        Commit a policy update. Returns (new_version, tx_id).
        Monotonically increments version per Section 3.2.
        Enforces INV_mono if expected_prev_version is provided.
        """
        with self._version_lock:
            current_v = self._versions[policy_id]
            if expected_prev_version is not None and current_v != expected_prev_version:
                raise ValueError(
                    f"INV_mono violation: expected prev version {expected_prev_version}, got {current_v}"
                )
            new_v = current_v + 1
            prev_v = current_v
            self._versions[policy_id] = new_v

        tx_id = self.policy_chain.commit({
            "policy_id": policy_id,
            "hash": policy_hash,
            "new_version": new_v,
            "issuer_sig": issuer_sig,
        })

        # SyncChain carries the update event with a global sequence number
        with self._seq_lock:
            self._global_seq += 1
            gseq = self._global_seq
        self.sync_chain.commit({
            "policy_id": policy_id,
            "prev_version": prev_v,
            "new_version": new_v,
            "hash": policy_hash,
            "issuer_sig": issuer_sig,
            "policy_body": policy_body,
            "event_type": "CREATE" if prev_v == 0 else "UPDATE",
            "global_seq": gseq,
        })
        return new_v, tx_id


    def delete_policy(self, policy_id: str) -> tuple[int, str]:
        with self._version_lock:
            new_v = self._versions[policy_id] + 1
            self._versions[policy_id] = new_v

        tx_id = self.policy_chain.commit({
            "policy_id": policy_id,
            "hash": "",
            "new_version": new_v,
            "event_type": "DELETE",
        })
        with self._seq_lock:
            self._global_seq += 1
            gseq = self._global_seq
        self.sync_chain.commit({
            "policy_id": policy_id,
            "prev_version": new_v - 1,
            "new_version": new_v,
            "hash": "",
            "event_type": "DELETE",
            "global_seq": gseq,
        })
        return new_v, tx_id

    def get_policy_version(self, policy_id: str) -> tuple[int, str]:
        """Returns (current_version, hash) from PolicyChain."""
        records = self.policy_chain.query("policy_id", policy_id)
        if not records:
            return 0, ""
        latest = max(records, key=lambda r: r["new_version"])
        return latest["new_version"], latest.get("hash", "")

    def verify_policy_hash(self, policy_id: str, version: int,
                           expected_hash: str) -> bool:
        records = self.policy_chain.query("policy_id", policy_id)
        for r in records:
            if r["new_version"] == version:
                return r.get("hash") == expected_hash
        return False

    # ── LogChain chaincode ────────────────────────────────────────────────

    def append_log(self, entry: dict) -> str:
        log_entry = dict(entry)
        edge_id = log_entry.get("edge_id")
        seq_e = log_entry.get("seq_e")
        if edge_id and seq_e is not None:
            if not hasattr(self, "_last_seq_e"):
                self._last_seq_e = {}
            with self._seq_lock:
                expected_seq = self._last_seq_e.get(edge_id, 0) + 1
                if seq_e != expected_seq:
                    log_entry["gap_status"] = f"GAP_DETECTED{{edge:{edge_id}, expected:{expected_seq}, got:{seq_e}}}"
                else:
                    log_entry["gap_status"] = "OK"
                self._last_seq_e[edge_id] = seq_e
        return self.log_chain.commit(log_entry)

    def get_logs(self, subject_id: str | None = None,
                 patient_id: str | None = None) -> list[dict]:
        if subject_id:
            return self.log_chain.query("subject_id", subject_id)
        if patient_id:
            return self.log_chain.query("patient_id", patient_id)
        return self.log_chain.all()

    # ── SyncChain subscription ────────────────────────────────────────────

    def subscribe_sync(self, callback: Callable[[dict], None]) -> None:
        self.sync_chain.subscribe(callback)

    def get_delta(self, from_version: int,
                  to_version: int = 0) -> list[dict]:
        """Returns sync events with global_seq > from_version up to to_version."""
        with self._seq_lock:
            current_seq = self._global_seq
        if to_version == 0:
            to_version = current_seq
        return self.sync_chain.query_range(from_version + 1, to_version)

    def get_current_global_seq(self) -> int:
        with self._seq_lock:
            return self._global_seq


class _RedisChannel:
    def __init__(self, backend: "RedisFabric", name: str):
        self.backend = backend
        self.name = name

    def all(self) -> list[dict]:
        return self.backend._all_records(self.name)

    def query(self, key: str, value: Any) -> list[dict]:
        return [record for record in self.all() if record.get(key) == value]

    def query_range(self, from_seq: int, to_seq: int) -> list[dict]:
        return [
            record for record in self.all()
            if from_seq <= record.get("global_seq", 0) <= to_seq
        ]

    def subscribe(self, callback: Callable[[dict], None]) -> None:
        self.backend.subscribe_sync(callback)


class RedisFabric:
    def __init__(self, redis_url: str, prefix: str = "acaas"):
        import redis

        self.redis = redis.Redis.from_url(redis_url, decode_responses=True)
        self.prefix = prefix
        self.policy_chain = _RedisChannel(self, "PolicyChain")
        self.log_chain = _RedisChannel(self, "LogChain")
        self.sync_chain = _RedisChannel(self, "SyncChain")

    @property
    def _versions(self) -> dict[str, int]:
        raw = self.redis.hgetall(self._key("versions"))
        return {key: int(value) for key, value in raw.items()}

    def _key(self, suffix: str) -> str:
        return f"{self.prefix}:{suffix}"

    def _list_key(self, channel: str) -> str:
        return self._key(channel.lower())

    def _pubsub_key(self, channel: str) -> str:
        return self._key(f"{channel.lower()}:pubsub")

    def _all_records(self, channel: str) -> list[dict]:
        values = self.redis.lrange(self._list_key(channel), 0, -1)
        return [json.loads(item) for item in values]

    def _commit_channel(self, channel: str, record: dict, publish: bool = False) -> str:
        key = self._list_key(channel)
        tx_id = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()[:16]
        entry = {
            **record,
            "tx_id": tx_id,
            "committed_at": time.time(),
            "block_number": self.redis.llen(key),
        }
        payload = json.dumps(entry, sort_keys=True)
        self.redis.rpush(key, payload)
        if publish:
            self.redis.publish(self._pubsub_key(channel), payload)
        return tx_id

    def commit_policy(self, policy_id: str, policy_hash: str,
                      issuer_sig: str = "", policy_body: dict | None = None,
                      expected_prev_version: int | None = None) -> tuple[int, str]:
        version_key = self._key("versions")
        hash_key = self._key("policy_hashes")
        if expected_prev_version is not None:
            current_v = int(self.redis.hget(version_key, policy_id) or 0)
            if current_v != expected_prev_version:
                raise ValueError(
                    f"INV_mono violation: expected prev version {expected_prev_version}, got {current_v}"
                )
        new_v = int(self.redis.hincrby(version_key, policy_id, 1))
        prev_v = new_v - 1
        self.redis.hset(hash_key, policy_id, policy_hash)

        tx_id = self._commit_channel("PolicyChain", {
            "policy_id": policy_id,
            "hash": policy_hash,
            "new_version": new_v,
            "issuer_sig": issuer_sig,
        })

        gseq = int(self.redis.incr(self._key("global_seq")))
        self._commit_channel("SyncChain", {
            "policy_id": policy_id,
            "prev_version": prev_v,
            "new_version": new_v,
            "hash": policy_hash,
            "issuer_sig": issuer_sig,
            "policy_body": policy_body,
            "event_type": "CREATE" if prev_v == 0 else "UPDATE",
            "global_seq": gseq,
        }, publish=True)
        return new_v, tx_id

    def delete_policy(self, policy_id: str) -> tuple[int, str]:
        version_key = self._key("versions")
        hash_key = self._key("policy_hashes")
        new_v = int(self.redis.hincrby(version_key, policy_id, 1))
        self.redis.hset(hash_key, policy_id, "")

        tx_id = self._commit_channel("PolicyChain", {
            "policy_id": policy_id,
            "hash": "",
            "new_version": new_v,
            "event_type": "DELETE",
        })
        gseq = int(self.redis.incr(self._key("global_seq")))
        self._commit_channel("SyncChain", {
            "policy_id": policy_id,
            "prev_version": new_v - 1,
            "new_version": new_v,
            "hash": "",
            "event_type": "DELETE",
            "global_seq": gseq,
        }, publish=True)
        return new_v, tx_id

    def get_policy_version(self, policy_id: str) -> tuple[int, str]:
        version = int(self.redis.hget(self._key("versions"), policy_id) or 0)
        policy_hash = self.redis.hget(self._key("policy_hashes"), policy_id) or ""
        return version, policy_hash

    def verify_policy_hash(self, policy_id: str, version: int, expected_hash: str) -> bool:
        current_version, current_hash = self.get_policy_version(policy_id)
        return current_version == version and current_hash == expected_hash

    def append_log(self, entry: dict) -> str:
        log_entry = dict(entry)
        edge_id = log_entry.get("edge_id")
        seq_e = log_entry.get("seq_e")
        if edge_id and seq_e is not None:
            last_key = self._key("last_seq_e")
            expected_seq = int(self.redis.hget(last_key, edge_id) or 0) + 1
            if seq_e != expected_seq:
                log_entry["gap_status"] = f"GAP_DETECTED{{edge:{edge_id}, expected:{expected_seq}, got:{seq_e}}}"
            else:
                log_entry["gap_status"] = "OK"
            self.redis.hset(last_key, edge_id, seq_e)
        return self._commit_channel("LogChain", log_entry)

    def get_logs(self, subject_id: str | None = None,
                 patient_id: str | None = None) -> list[dict]:
        logs = self.log_chain.all()
        if subject_id is not None:
            logs = [log for log in logs if log.get("subject_id") == subject_id]
        if patient_id is not None:
            logs = [log for log in logs if log.get("patient_id") == patient_id]
        return logs

    def subscribe_sync(self, callback: Callable[[dict], None]) -> None:
        def _listen() -> None:
            pubsub = self.redis.pubsub()
            pubsub.subscribe(self._pubsub_key("SyncChain"))
            for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                try:
                    callback(json.loads(message["data"]))
                except Exception:
                    pass

        thread = threading.Thread(target=_listen, daemon=True)
        thread.start()

    def get_delta(self, from_version: int, to_version: int = 0) -> list[dict]:
        current_seq = int(self.redis.get(self._key("global_seq")) or 0)
        if to_version == 0:
            to_version = current_seq
        return self.sync_chain.query_range(from_version + 1, to_version)

    def get_current_global_seq(self) -> int:
        return int(self.redis.get(self._key("global_seq")) or 0)



def _build_backend() -> Any:
    backend = os.environ.get("ACAAS_LEDGER_BACKEND", "").strip().lower()
    fabric_url = os.environ.get("ACAAS_FABRIC_GATEWAY_URL", "").strip()
    if backend in ("fabric", "fabric-gateway") or (not backend and bool(fabric_url)):
        try:
            from blockchain.fabric.client import FabricGatewayClient
            return FabricGatewayClient(gateway_url=fabric_url or "http://localhost:7050")
        except Exception:
            pass

    redis_url = os.environ.get("ACAAS_REDIS_URL", "").strip()
    use_redis = backend == "redis" or (not backend and bool(redis_url))
    if use_redis:
        try:
            return RedisFabric(
                redis_url=redis_url or "redis://localhost:6379/0",
                prefix=os.environ.get("ACAAS_LEDGER_PREFIX", "acaas"),
            )
        except Exception:
            pass
    return FabricMock()


fabric = _build_backend()

