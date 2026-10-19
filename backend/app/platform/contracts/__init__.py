"""Versioned platform facts; importing a contract does not enable enforcement."""

from app.platform.contracts.approval import Approval
from app.platform.contracts.audit import AuditEvent
from app.platform.contracts.execution import ExecutionEnvelope
from app.platform.contracts.identifiers import new_platform_id, stable_platform_id
from app.platform.contracts.policy import (
    ActionContextInput,
    PolicyDecision,
    PolicyRequest,
    hash_action_context,
)
from app.platform.contracts.resources import DefinitionRef, EnvironmentRef, IdentityRef, ResourceMetadata
from app.platform.contracts.runs import RUN_COMPLETED, RUN_CREATED, RUN_FAILED, ExecutionSnapshot, RunFact, run_fact_from_envelope
from app.platform.contracts.secrets import SecretRef
from app.platform.contracts.versioning import PLATFORM_SCHEMA_V1

__all__ = [
    "PLATFORM_SCHEMA_V1",
    "ActionContextInput",
    "Approval",
    "AuditEvent",
    "DefinitionRef",
    "EnvironmentRef",
    "ExecutionEnvelope",
    "ExecutionSnapshot",
    "IdentityRef",
    "PolicyDecision",
    "PolicyRequest",
    "ResourceMetadata",
    "RUN_COMPLETED",
    "RUN_CREATED",
    "RUN_FAILED",
    "RunFact",
    "run_fact_from_envelope",
    "SecretRef",
    "hash_action_context",
    "new_platform_id",
    "stable_platform_id",
]
