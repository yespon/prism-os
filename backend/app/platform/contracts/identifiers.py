from hashlib import sha256
from typing import Literal
from uuid import uuid4

IdentifierKind = Literal["resource", "task", "run", "event"]


def _validate_source(value: str, name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must not be blank")
    return normalized


def new_platform_id(kind: IdentifierKind) -> str:
    return f"{kind}_{uuid4().hex}"


def stable_platform_id(
    kind: IdentifierKind,
    namespace: str,
    external_id: str,
) -> str:
    source = ":".join(
        (_validate_source(namespace, "namespace"), _validate_source(external_id, "external_id"))
    )
    digest = sha256(source.encode("utf-8")).hexdigest()[:32]
    return f"{kind}_{digest}"
