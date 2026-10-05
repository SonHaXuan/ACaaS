"""Unit tests for edge offline queue monotonicity and persistence."""
import os
import sys
import tempfile
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_offline_queue_seq_monotonic():
    """Verify offline queue assigns strictly monotonic seq_e per edge node."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_db = f.name

    old_db = os.environ.get("QUEUE_DB_PATH")
    try:
        os.environ["QUEUE_DB_PATH"] = temp_db
        queue_dir = str(ROOT / "edge" / "offline-queue")
        if queue_dir not in sys.path:
            sys.path.insert(0, queue_dir)
        import offline_queue as oq
        import importlib
        importlib.reload(oq)
        oq.DB_PATH = temp_db
        oq._init()

        seqs = []
        for i in range(1, 11):
            entry = {
                "subject_id": f"doc_{i}",
                "patient_id": f"P_{i}",
                "action": "READ",
                "decision": "PERMIT",
                "edge_id": "edge-node-1",
            }
            seq = oq.enqueue(entry, edge_id="edge-node-1")
            seqs.append(seq)

        # Assert strictly monotonic sequence: 1, 2, 3, ...
        assert len(seqs) == 10
        assert seqs == sorted(seqs)
        for idx in range(len(seqs) - 1):
            assert seqs[idx + 1] == seqs[idx] + 1

        # Check pending entries contain correct seq_e
        pending = oq.pending()
        assert len(pending) == 10
        for idx, item in enumerate(pending, 1):
            assert item["seq"] == idx
            assert item["entry"]["seq_e"] == idx
            assert item["entry"]["edge_id"] == "edge-node-1"

    finally:
        if old_db is not None:
            os.environ["QUEUE_DB_PATH"] = old_db
        elif "QUEUE_DB_PATH" in os.environ:
            del os.environ["QUEUE_DB_PATH"]
        if os.path.exists(temp_db):
            os.unlink(temp_db)
