"""
Tests for Hyperledger Fabric Gateway sidecar, 4-peer endorsement ensemble,
INV_mono on-chain validation, seq_e gap detection, and Byzantine fault injection.
"""
from __future__ import annotations

import os
import subprocess
import time
import pytest

from blockchain.fabric.client import FabricGatewayClient
from blockchain.mock.ledger import _build_backend


GATEWAY_URL = os.environ.get("ACAAS_FABRIC_GATEWAY_URL", "http://localhost:7050")


@pytest.fixture(scope="module")
def fabric_client():
    """Ensure Fabric Gateway is reachable, launching local binary if not running."""
    client = FabricGatewayClient(gateway_url=GATEWAY_URL, timeout=3.0)
    proc = None
    try:
        client.health()
    except Exception:
        # Start local binary on port 7050 if docker container not yet accessible
        binary_path = os.path.abspath("blockchain/fabric/sidecar/fabric-sidecar")
        if os.path.exists(binary_path):
            env = os.environ.copy()
            env["PORT"] = "7050"
            proc = subprocess.Popen([binary_path], env=env)
            time.sleep(0.5)
            client = FabricGatewayClient(gateway_url="http://localhost:7050", timeout=3.0)
        else:
            pytest.skip(f"Fabric gateway not running at {GATEWAY_URL} and binary not compiled.")

    # Reset byzantine configuration to honest
    try:
        client.set_byzantine_fault(faulty_peer="peer0.org2", mode="honest")
    except Exception:
        pass

    yield client

    if proc is not None:
        proc.terminate()
        proc.wait()


def test_fabric_health_and_ensemble_status(fabric_client):
    """Verify 4-peer ensemble configuration and AND(Org1, Org2) endorsement policy."""
    health = fabric_client.health()
    assert health.get("status") == "ok"
    assert health.get("service") == "fabric-gateway-sidecar"

    status = fabric_client.get_ensemble_status()
    assert status.get("peer_count") == 4
    peers = status.get("peers", [])
    assert "peer0.org1" in peers
    assert "peer1.org1" in peers
    assert "peer0.org2" in peers
    assert "peer1.org2" in peers
    assert status.get("endorsement_policy") == "AND('Org1MSP.peer','Org2MSP.peer')"


def test_fabric_policy_commit_and_monotonicity(fabric_client):
    """Verify PolicyChain commits and enforces INV_mono rollback rejection."""
    policy_id = f"test-pol-{int(time.time() * 1000)}"

    # Initial commit (v1)
    v1, tx1 = fabric_client.commit_policy(
        policy_id=policy_id,
        policy_hash="hash-v1-initial",
        issuer_sig="sig-admin-1",
        policy_body={"rules": ["permit-doctors"]},
        expected_prev_version=0,
    )
    assert v1 >= 1
    assert len(tx1) == 16

    # Valid monotonic progression (v2)
    v2, tx2 = fabric_client.commit_policy(
        policy_id=policy_id,
        policy_hash="hash-v2-updated",
        issuer_sig="sig-admin-1",
        expected_prev_version=v1,
    )
    assert v2 == v1 + 1

    # Verify version and hash query
    curr_v, curr_h = fabric_client.get_policy_version(policy_id)
    assert curr_v == v2
    assert curr_h == "hash-v2-updated"
    assert fabric_client.verify_policy_hash(policy_id, v2, "hash-v2-updated")
    assert not fabric_client.verify_policy_hash(policy_id, v2, "wrong-hash")

    # INV_mono violation attempt: expected_prev_version mismatches current
    with pytest.raises(ValueError) as excinfo:
        fabric_client.commit_policy(
            policy_id=policy_id,
            policy_hash="hash-v3-stale",
            expected_prev_version=0,  # Rollback attempt
        )
    assert "INV_mono violation" in str(excinfo.value)


def test_fabric_logchain_gap_detection(fabric_client):
    """Verify LogChain monotonic seq_e check and GAP_DETECTED flagging."""
    edge_id = f"edge-test-{int(time.time() * 1000)}"

    # Append valid seq_e=1
    tx1 = fabric_client.append_log({
        "edge_id": edge_id,
        "seq_e": 1,
        "subject_id": "doc_cardio_1",
        "patient_id": "patient_101",
        "action": "READ",
        "decision": "PERMIT",
    })
    assert len(tx1) == 16

    # Append valid seq_e=2
    fabric_client.append_log({
        "edge_id": edge_id,
        "seq_e": 2,
        "subject_id": "doc_cardio_1",
        "patient_id": "patient_101",
        "action": "READ",
        "decision": "PERMIT",
    })

    # Append out-of-order seq_e=5 (skipping 3 and 4)
    fabric_client.append_log({
        "edge_id": edge_id,
        "seq_e": 5,
        "subject_id": "doc_cardio_1",
        "patient_id": "patient_101",
        "action": "WRITE",
        "decision": "DENY",
    })

    logs = fabric_client.get_logs(patient_id="patient_101")
    edge_logs = [l for l in logs if l.get("edge_id") == edge_id]
    assert len(edge_logs) == 3

    assert edge_logs[0]["seq_e"] == 1
    assert edge_logs[0]["gap_status"] == "OK"

    assert edge_logs[1]["seq_e"] == 2
    assert edge_logs[1]["gap_status"] == "OK"

    assert edge_logs[2]["seq_e"] == 5
    assert "GAP_DETECTED" in edge_logs[2]["gap_status"]
    assert "expected:3, got:5" in edge_logs[2]["gap_status"]


def test_fabric_byzantine_fault_injection(fabric_client):
    """Verify E11 Byzantine fault modes: honest, passive, rewind, fork."""
    policy_base = f"byz-pol-{int(time.time() * 1000)}"

    # 1. Honest mode: all peers sign correctly
    fabric_client.set_byzantine_fault(faulty_peer="peer0.org2", mode="honest")
    v, _ = fabric_client.commit_policy(f"{policy_base}-1", "hash-honest")
    assert v >= 1

    # 2. Passive mode: peer0.org2 drops proposal, peer1.org2 still endorses -> Org2 satisfies threshold
    fabric_client.set_byzantine_fault(faulty_peer="peer0.org2", mode="passive")
    v, _ = fabric_client.commit_policy(f"{policy_base}-2", "hash-passive")
    assert v >= 1  # Liveness preserved!

    # 3. Rewind mode: peer0.org2 signs outdated version, peer1.org2 is honest -> Org2 satisfies threshold
    fabric_client.set_byzantine_fault(faulty_peer="peer0.org2", mode="rewind")
    v, _ = fabric_client.commit_policy(f"{policy_base}-3", "hash-rewind")
    assert v >= 1

    # 4. Fork mode: peer0.org2 signs diverging state, peer1.org2 is honest -> Org2 satisfies threshold
    fabric_client.set_byzantine_fault(faulty_peer="peer0.org2", mode="fork")
    v, _ = fabric_client.commit_policy(f"{policy_base}-4", "hash-fork")
    assert v >= 1

    # Reset back to honest
    fabric_client.set_byzantine_fault(faulty_peer="peer0.org2", mode="honest")


def test_fabric_sync_delta(fabric_client):
    """Verify SyncChain delta query returns missed policy events."""
    curr_seq = fabric_client.get_current_global_seq()
    pol_id = f"sync-pol-{int(time.time() * 1000)}"

    fabric_client.commit_policy(pol_id, "h1")
    fabric_client.commit_policy(pol_id, "h2")

    delta = fabric_client.get_delta(from_version=curr_seq)
    assert len(delta) >= 2
    delta_policy_ids = [d["policy_id"] for d in delta]
    assert pol_id in delta_policy_ids


def test_ledger_backend_switching(monkeypatch):
    """Verify ACAAS_LEDGER_BACKEND=fabric instantiates FabricGatewayClient."""
    monkeypatch.setenv("ACAAS_LEDGER_BACKEND", "fabric")
    monkeypatch.setenv("ACAAS_FABRIC_GATEWAY_URL", GATEWAY_URL)
    backend = _build_backend()
    assert isinstance(backend, FabricGatewayClient)
