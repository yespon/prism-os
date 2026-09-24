from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PlainSerializer


def _non_blank(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("value must not be blank")
    return normalized


def _timezone_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include a timezone")
    return value.astimezone(UTC)


TenantId = Annotated[str, Field(min_length=1, max_length=255), AfterValidator(_non_blank)]
UtcDatetime = Annotated[
    datetime,
    AfterValidator(_timezone_aware),
    PlainSerializer(lambda value: value.isoformat().replace("+00:00", "Z"), return_type=str),
]


class FrozenContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
