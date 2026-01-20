from __future__ import annotations

from typing import Any, Dict, List

from core.config import AppConfig
from miners.heuristic_parser import LiteParser
from storage.manager import IngestReport, StorageManager


class IngestionOrchestrator:
    def __init__(self, config: AppConfig) -> None:
        self.storage = StorageManager(config)
        self.parser = LiteParser()

    def ingest_records(
        self, records: List[Dict[str, Any]], batch_id: str
    ) -> IngestReport:
        enriched = [self._enrich_record(record) for record in records]
        return self.storage.ingest_records(enriched, batch_id)

    def close(self) -> None:
        self.storage.close()

    def _enrich_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        payload = record.get("payload", {})
        metadata = record.get("metadata", {})
        if isinstance(metadata, dict):
            metadata = dict(metadata)
        else:
            metadata = {}
        if isinstance(payload, dict):
            text = payload.get("text")
            if isinstance(text, str) and text.strip():
                metadata["intel"] = self.parser.classify(text)
        record = dict(record)
        record["metadata"] = metadata
        return record
