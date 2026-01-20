from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from typing import Any, Dict


class QuarantineWriter:
    def __init__(self, base_dir: str) -> None:
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def write(
        self,
        record: Dict[str, Any],
        error: str,
        batch_id: str,
        trace_id: str,
    ) -> str:
        timestamp = datetime.now(timezone.utc).isoformat()
        entry = {
            "batch_id": batch_id,
            "trace_id": trace_id,
            "error": error,
            "quarantine_ts": timestamp,
            "record": record,
        }
        path = os.path.join(self.base_dir, f"quarantine_{batch_id}.jsonl")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(entry, ensure_ascii=True, separators=(",", ":")) + "\n"
            )
        return path
