"""
Unit tests for the Edge Lightweight PDP evaluator.
Tests deny-overrides, time-range conditions, and role matching.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../edge/local-policy-store"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../edge/lightweight-pdp"))

import store, evaluator

# ── test fixtures ──────────────────────────────────────────────────────────

PERMIT_RULE = json.dumps({
    "subject": {"role": "doctor", "department": "cardiology", "clearance_level": 2},
    "resource": {"data_type": "EHR", "sensitivity": 3},
    "action": "read",
    "condition": {"time_range": None, "location": None, "extra": {}},
    "effect": "PERMIT",
})

DENY_RULE = json.dumps({
    "subject": {"role": "doctor", "department": "cardiology", "clearance_level": 2},
    "resource": {"data_type": "EHR", "sensitivity": 3},
    "action": "read",
    "condition": {"time_range": None, "location": None, "extra": {}},
    "effect": "DENY",
})


def setup_function():
    store.close()
    os.environ["EDGE_DB_PATH"] = "/tmp/acaas_test_edge.db"
    store.DB_PATH = "/tmp/acaas_test_edge.db"
    # reset
    import sqlite3
    with sqlite3.connect(store.DB_PATH) as c:
        c.execute("DROP TABLE IF EXISTS policies")
        c.execute("DROP TABLE IF EXISTS sync_state")
    store.init()


def teardown_function():
    store.close()


def test_permit_for_matching_role():
    store.upsert("p1", PERMIT_RULE, 1, "hash1", "PERMIT")
    decision, pid, reason, latency = evaluator.evaluate({
        "role": "doctor", "department": "cardiology", "clearance_level": 2,
        "resource_type": "EHR", "action": "read", "location": None,
    })
    assert decision == "PERMIT"
    assert pid == "p1"
    assert latency < 50   # well under 10ms target in Python sim


def test_deny_for_wrong_role():
    store.upsert("p2", PERMIT_RULE, 1, "hash2", "PERMIT")
    decision, pid, reason, latency = evaluator.evaluate({
        "role": "nurse", "department": None, "clearance_level": 1,
        "resource_type": "EHR", "action": "read", "location": None,
    })
    assert decision == "DENY"
    assert pid is None


def test_deny_overrides_permit():
    store.upsert("p-permit", PERMIT_RULE, 1, "h1", "PERMIT")
    store.upsert("p-deny",   DENY_RULE,   1, "h2", "DENY")
    decision, pid, reason, _ = evaluator.evaluate({
        "role": "doctor", "department": "cardiology", "clearance_level": 2,
        "resource_type": "EHR", "action": "read", "location": None,
    })
    assert decision == "DENY"


def test_empty_store_default_deny():
    decision, pid, reason, _ = evaluator.evaluate({
        "role": "doctor", "resource_type": "EHR",
        "action": "read", "clearance_level": 1,
    })
    assert decision == "DENY"
    assert "default-deny" in reason


def test_clearance_level_enforcement():
    low_clearance_rule = json.dumps({
        "subject": {"role": "doctor", "department": None, "clearance_level": 5},
        "resource": {"data_type": "EHR", "sensitivity": 5},
        "action": "read",
        "condition": {"time_range": None, "location": None, "extra": {}},
        "effect": "PERMIT",
    })
    store.upsert("p-high-cl", low_clearance_rule, 1, "h3", "PERMIT")
    # requester only has clearance 2, rule requires 5
    decision, _, _, _ = evaluator.evaluate({
        "role": "doctor", "clearance_level": 2,
        "resource_type": "EHR", "action": "read",
    })
    assert decision == "DENY"
