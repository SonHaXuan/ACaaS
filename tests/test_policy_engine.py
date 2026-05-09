from acaas_shared.models import AccessRequest, Conditions, PolicyRecord, PolicyRule, ResourceAttributes, SubjectAttributes
from acaas_shared.policy_engine import evaluate_policies


def test_allow_policy_match() -> None:
    policy = PolicyRecord(
        policy_id="p1",
        version=1,
        hash="h",
        created_at="now",
        updated_at="now",
        rule=PolicyRule(
            policy_id="p1",
            subject=SubjectAttributes(role="doctor", department="cardiology", clearance_level=2),
            resource=ResourceAttributes(resource_type="EHR", sensitivity="medium"),
            actions=["read"],
            conditions=Conditions(locations=["clinic-a"], time_range=[8, 18]),
            effect="allow",
        ),
    )
    request = AccessRequest(
        subject=SubjectAttributes(role="doctor", department="cardiology", clearance_level=2),
        resource=ResourceAttributes(resource_type="EHR", sensitivity="medium", owner_patient_id="P123"),
        action="read",
        environment={"location": "clinic-a", "hour": 10},
    )
    decision = evaluate_policies([policy], request)
    assert decision.allowed is True


def test_deny_overrides_allow() -> None:
    allow_policy = PolicyRecord(
        policy_id="allow",
        version=1,
        hash="h",
        created_at="now",
        updated_at="now",
        rule=PolicyRule(
            policy_id="allow",
            subject=SubjectAttributes(role="intern", department="cardiology", clearance_level=1),
            resource=ResourceAttributes(resource_type="EHR", sensitivity="high"),
            actions=["read"],
            conditions=Conditions(),
            effect="allow",
            priority=50,
        ),
    )
    deny_policy = PolicyRecord(
        policy_id="deny",
        version=1,
        hash="h",
        created_at="now",
        updated_at="now",
        rule=PolicyRule(
            policy_id="deny",
            subject=SubjectAttributes(role="intern", department="cardiology", clearance_level=1),
            resource=ResourceAttributes(resource_type="EHR", sensitivity="high"),
            actions=["read"],
            conditions=Conditions(),
            effect="deny",
            priority=10,
        ),
    )
    request = AccessRequest(
        subject=SubjectAttributes(role="intern", department="cardiology", clearance_level=1),
        resource=ResourceAttributes(resource_type="EHR", sensitivity="high"),
        action="read",
    )
    decision = evaluate_policies([allow_policy, deny_policy], request)
    assert decision.allowed is False
    assert decision.matched_policy_id == "deny"

