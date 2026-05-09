"""
ACaaS Fog Aggregation Service.
Batches access logs from multiple edge nodes before uploading to LogChain.
Reduces LogChain transaction volume (Section 4.1).
"""
import sys, os, json, time, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any
from blockchain.mock import fabric

BATCH_SIZE     = int(os.environ.get("LOG_BATCH_SIZE", "50"))
FLUSH_INTERVAL = int(os.environ.get("LOG_FLUSH_INTERVAL", "30"))

app = FastAPI(title="ACaaS Fog Aggregation Service", version="1.0.0")

_buffer: list[dict] = []
_buffer_lock = threading.Lock()


class LogBatch(BaseModel):
    edge_node_id: str
    entries: list[dict]


@app.post("/logs")
def receive_logs(batch: LogBatch):
    with _buffer_lock:
        for entry in batch.entries:
            _buffer.append({**entry, "received_from": batch.edge_node_id,
                            "received_at": time.time()})
        if len(_buffer) >= BATCH_SIZE:
            _flush()
    return {"received": len(batch.entries), "buffer_size": len(_buffer)}


def _flush() -> int:
    with _buffer_lock:
        if not _buffer:
            return 0
        entries = list(_buffer)
        _buffer.clear()
    count = 0
    for entry in entries:
        fabric.append_log(entry)
        count += 1
    return count


@app.post("/flush")
def manual_flush():
    count = _flush()
    return {"flushed": count}


@app.get("/health")
def health():
    return {"status": "ok", "service": "fog-aggregation",
            "buffer_size": len(_buffer)}


def _periodic_flush():
    while True:
        time.sleep(FLUSH_INTERVAL)
        n = _flush()
        if n:
            print(f"[fog-aggregation] periodic flush: {n} entries")


@app.on_event("startup")
def startup():
    t = threading.Thread(target=_periodic_flush, daemon=True)
    t.start()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0",
                port=int(os.environ.get("FOG_AGG_PORT", 8008)), reload=True)
