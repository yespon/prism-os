"""Read-only detection helpers for legacy remote storage resources."""

from dataclasses import dataclass
from typing import Any

from deerflow.storage.provider import StorageProviderConfig


@dataclass(frozen=True)
class LegacyObjectResource:
    kind: str
    name: str
    guidance: str


@dataclass(frozen=True)
class BucketAccessReport:
    bucket: str
    accessible: bool
    error_type: str | None = None


def detect_legacy_object_resources(
    config: StorageProviderConfig,
) -> tuple[LegacyObjectResource, ...]:
    guidance = (
        "Verify access and create an explicit remote migration plan; "
        "PrismOS will not copy or delete objects."
    )
    resources: list[LegacyObjectResource] = []
    if config.s3_bucket_name == "opsintech-files":
        resources.append(LegacyObjectResource("s3-bucket", config.s3_bucket_name, guidance))
    if config.juicefs_subdir == "opsintech-files":
        resources.append(LegacyObjectResource("juicefs-prefix", config.juicefs_subdir, guidance))
    return tuple(resources)


def validate_s3_bucket_access(client: Any, bucket: str) -> BucketAccessReport:
    try:
        client.head_bucket(Bucket=bucket)
    except Exception as exc:
        return BucketAccessReport(bucket=bucket, accessible=False, error_type=type(exc).__name__)
    return BucketAccessReport(bucket=bucket, accessible=True)
