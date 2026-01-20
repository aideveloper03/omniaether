from __future__ import annotations

from datetime import datetime, timezone
import os
from pydantic import BaseModel, ConfigDict, Field


class TelemetryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    proxy_id: str
    user_agent: str
    latency_ms: int
    success_rate: float
    event_ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    batch_id: str
    primary_key: str
    outcome: str
    error: str = ""


class TelemetryLogger:
    def __init__(self, path: str) -> None:
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def log(self, event: TelemetryEvent) -> None:
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(event.model_dump_json() + "\n")
