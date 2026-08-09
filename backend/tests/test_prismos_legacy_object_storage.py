from deerflow.storage.legacy_resources import (
    detect_legacy_object_resources,
    validate_s3_bucket_access,
)
from deerflow.storage.provider import StorageProviderConfig


class AccessibleClient:
    def head_bucket(self, *, Bucket: str) -> None:
        assert Bucket == "opsintech-files"


class DeniedClient:
    def head_bucket(self, *, Bucket: str) -> None:
        raise PermissionError(Bucket)


def test_new_defaults_have_no_legacy_remote_resources() -> None:
    assert detect_legacy_object_resources(StorageProviderConfig()) == ()


def test_legacy_resources_are_reported_without_mutation() -> None:
    config = StorageProviderConfig(
        s3_bucket_name="opsintech-files", juicefs_subdir="opsintech-files"
    )
    reports = detect_legacy_object_resources(config)
    assert [item.kind for item in reports] == ["s3-bucket", "juicefs-prefix"]
    assert all("will not copy or delete" in item.guidance for item in reports)


def test_bucket_access_probe_reports_success_and_permission_failure() -> None:
    assert validate_s3_bucket_access(AccessibleClient(), "opsintech-files").accessible
    denied = validate_s3_bucket_access(DeniedClient(), "opsintech-files")
    assert denied.accessible is False
    assert denied.error_type == "PermissionError"
