def test_public_contract_api_keeps_p0_and_adds_only_m1_facts() -> None:
    from app.platform import contracts

    expected = {
        "PLATFORM_SCHEMA_V1",
        "ActionContextInput",
        "Approval",
        "AuditEvent",
        "DefinitionRef",
        "EnvironmentRef",
        "ExecutionEnvelope",
        "IdentityRef",
        "ResourceMetadata",
        "SecretRef",
        "PolicyDecision",
        "PolicyRequest",
        "hash_action_context",
        "new_platform_id",
        "stable_platform_id",
    }
    assert set(contracts.__all__) == expected
    assert not hasattr(contracts, "Task")
    assert not hasattr(contracts, "Run")
    assert contracts.Approval.__name__ == "Approval"
