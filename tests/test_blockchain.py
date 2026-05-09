"""Unit tests for the Fabric mock — PolicyChain, LogChain, SyncChain."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blockchain.mock.ledger import FabricMock


def _fresh():
    """Return a fresh FabricMock (not the singleton for isolation)."""
    m = object.__new__(FabricMock)
    from blockchain.mock.ledger import _Channel
    from collections import defaultdict
    import threading
    m.policy_chain = _Channel("PolicyChain")
    m.log_chain    = _Channel("LogChain")
    m.sync_chain   = _Channel("SyncChain")
    m._versions     = defaultdict(int)
    m._version_lock = threading.Lock()
    m._global_seq = 0
    m._seq_lock = threading.Lock()
    return m


def test_policy_version_monotonic():
    fb = _fresh()
    v1, _ = fb.commit_policy("p1", "hash-a")
    v2, _ = fb.commit_policy("p1", "hash-b")
    assert v2 == v1 + 1


def test_verify_hash():
    fb = _fresh()
    v, _ = fb.commit_policy("p1", "correct-hash")
    assert fb.verify_policy_hash("p1", v, "correct-hash")
    assert not fb.verify_policy_hash("p1", v, "wrong-hash")


def test_sync_chain_event_published():
    fb = _fresh()
    events = []
    fb.subscribe_sync(events.append)
    fb.commit_policy("p2", "h2")
    assert len(events) == 1
    assert events[0]["policy_id"] == "p2"
    assert events[0]["event_type"] == "CREATE"


def test_delta_returns_missed_events():
    fb = _fresh()
    fb.commit_policy("p1", "h1")
    fb.commit_policy("p2", "h2")
    fb.commit_policy("p3", "h3")
    delta = fb.get_delta(from_version=1)
    assert len(delta) == 2   # v2 and v3


def test_log_chain_append_and_query():
    fb = _fresh()
    fb.append_log({"subject_id": "doc1", "patient_id": "P1", "decision": "PERMIT"})
    logs = fb.get_logs(subject_id="doc1")
    assert len(logs) == 1
    assert logs[0]["decision"] == "PERMIT"
