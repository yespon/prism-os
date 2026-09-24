def test_public_contract_api_exports_only_stable_foundation_types() -> None:
    from app.platform import contracts

    expected = {
        "PLATFORM_SCHEMA_V1",
        "AuditEvent",
        "DefinitionRef",
        "EnvironmentRef",
        "ExecutionEnvelope",
        "IdentityRef",
        "ResourceMetadata",
        "new_platform_id",
        "stable_platform_id",
    }
    assert set(contracts.__all__) == expected
    assert not hasattr(contracts, "Task")
    assert not hasattr(contracts, "Run")
    assert not hasattr(contracts, "Approval")
