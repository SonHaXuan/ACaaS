from fastapi.testclient import TestClient

from scripts.bootstrap_sample_data import main as bootstrap_main
from legacy.services.audit_service.main import app as audit_app
from legacy.services.data_minimizer.main import app as minimizer_app
from legacy.services.edge_gateway.main import app as edge_app
from legacy.services.sync_service.main import app as sync_app


def test_end_to_end_edge_flow(monkeypatch) -> None:
    bootstrap_main()
    sync_client = TestClient(sync_app)
    minimizer_client = TestClient(minimizer_app)
    audit_client = TestClient(audit_app)
    edge_client = TestClient(edge_app)

    def fake_get(url, params=None, **kwargs):
        return sync_client.get("/sync/policies", params=params)

    def fake_post(url, json=None, **kwargs):
        if url.endswith("/minimize"):
            return minimizer_client.post("/minimize", json=json)
        if url.endswith("/audit/events"):
            return audit_client.post("/audit/events", json=json)
        raise AssertionError(f"Unexpected URL: {url}")

    import httpx

    async def fake_async_get(self, *args, **kwargs):
        return fake_get(*args, **kwargs)

    async def fake_async_post(self, *args, **kwargs):
        return fake_post(*args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_async_get)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_async_post)

    sync_response = edge_client.post("/edge/sync")
    assert sync_response.status_code == 200
    access_response = edge_client.post(
        "/edge/access",
        json={
            "request": {
                "subject": {
                    "role": "doctor",
                    "department": "cardiology",
                    "clearance_level": 2,
                },
                "resource": {
                    "resource_type": "EHR",
                    "sensitivity": "medium",
                    "owner_patient_id": "P123",
                },
                "action": "read",
                "environment": {
                    "location": "clinic-a",
                    "hour": 9,
                    "assigned_department": "cardiology",
                },
            }
        },
    )
    assert access_response.status_code == 200
    payload = access_response.json()
    assert payload["decision"]["allowed"] is True
    assert payload["record"]["patient_id"] != "P123"
