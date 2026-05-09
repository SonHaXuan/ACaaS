"""
Locust load test for ACaaS Edge PDP (Experiment 2: Throughput Scalability).
Simulates concurrent doctors making EHR access requests.

Run:
  locust -f locustfile.py --host http://localhost:8003
  locust -f locustfile.py --host http://localhost:8003 \
         --users 1000 --spawn-rate 50 --headless --run-time 60s \
         --csv results/exp2
"""
from locust import HttpUser, task, between
import random, uuid


ROLES = ["doctor", "nurse", "researcher"]
RESOURCE_TYPES = ["EHR", "lab_result", "medication", "vitals"]
ACTIONS = ["read", "write", "delete"]
DEPARTMENTS = ["cardiology", "neurology", "oncology", "general"]


class EdgePDPUser(HttpUser):
    wait_time = between(0.05, 0.2)

    @task(8)
    def evaluate_ehr_read(self):
        """Most common: doctor reading EHR."""
        payload = {
            "request_id": str(uuid.uuid4())[:8],
            "subject_id": f"doc-{random.randint(1, 100)}",
            "role": "doctor",
            "department": random.choice(DEPARTMENTS),
            "clearance_level": random.randint(1, 3),
            "patient_id": f"P{random.randint(1, 10000)}",
            "resource_type": "EHR",
            "action": "read",
            "location": "hospital-1",
        }
        with self.client.post(
            "/evaluate", json=payload, catch_response=True
        ) as resp:
            if resp.status_code in (200, 403):
                resp.success()
            else:
                resp.failure(f"Unexpected status {resp.status_code}")

    @task(2)
    def evaluate_lab_read(self):
        payload = {
            "request_id": str(uuid.uuid4())[:8],
            "subject_id": f"nurse-{random.randint(1, 50)}",
            "role": "nurse",
            "department": random.choice(DEPARTMENTS),
            "clearance_level": 1,
            "patient_id": f"P{random.randint(1, 10000)}",
            "resource_type": "lab_result",
            "action": "read",
            "location": "clinic-2",
        }
        with self.client.post(
            "/evaluate", json=payload, catch_response=True
        ) as resp:
            if resp.status_code in (200, 403):
                resp.success()

    @task(1)
    def health_check(self):
        self.client.get("/health")
