from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _ensure_no_none(value: Any, path: str = "root") -> None:
    if value is None:
        raise ValueError(f"null value detected at {path}")
    if isinstance(value, dict):
        for key, item in value.items():
            _ensure_no_none(item, f"{path}.{key}")
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            _ensure_no_none(item, f"{path}[{idx}]")


class TelemetryContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    proxy_id: str
    user_agent: str
    latency_ms: int = Field(ge=0)
    success_rate: float = Field(ge=0.0, le=1.0)

    @field_validator("trace_id", "proxy_id", "user_agent")
    @classmethod
    def non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must be non-empty")
        return value


class DataRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_key: str
    batch_id: str
    source_provenance: str
    timestamp: datetime
    content_hash: str
    content_type: str
    payload: Dict[str, Any]
    metadata: Dict[str, Any]
    telemetry: TelemetryContext

    @field_validator("primary_key", "batch_id", "source_provenance", "content_type")
    @classmethod
    def non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must be non-empty")
        return value

    @field_validator("content_hash")
    @classmethod
    def hash_format(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("content_hash must be a 64-char hex digest")
        return value

    @field_validator("payload", "metadata")
    @classmethod
    def no_nulls(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        _ensure_no_none(value)
        return value
