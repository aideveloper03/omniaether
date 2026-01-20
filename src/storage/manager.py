from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import ValidationError

from core.config import AppConfig
from core.telemetry import TelemetryEvent, TelemetryLogger
from storage.hashing import verify_content_hash
from storage.metadata_index import MetadataIndex
from storage.models import DataRecord
from storage.parquet_writer import ParquetShardWriter
from storage.quarantine import QuarantineWriter


@dataclass
class IngestReport:
    batch_id: str
    received: int
    stored: int
    quarantined: int
    parquet_files: List[str]


class StorageManager:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.index = MetadataIndex(config.index_path)
        self.quarantine = QuarantineWriter(config.quarantine_dir)
        self.telemetry = TelemetryLogger(config.telemetry_path)

    def ingest_records(
        self, records: List[Dict[str, Any]], batch_id: str
    ) -> IngestReport:
        writer = ParquetShardWriter(
            base_dir=self.config.parquet_dir,
            batch_id=batch_id,
            max_records=self.config.max_records_per_file,
            max_bytes=self.config.max_bytes_per_file,
        )
        stored = 0
        quarantined = 0
        parquet_files: List[str] = []
        for record in records:
            trace_id = self._extract_trace_id(record)
            primary_key = self._extract_primary_key(record)
            try:
                validated = DataRecord.model_validate(record)
            except ValidationError as err:
                quarantined += 1
                self.quarantine.write(
                    record=record,
                    error=str(err),
                    batch_id=batch_id,
                    trace_id=trace_id,
                )
                self._log_event(
                    trace_id=trace_id,
                    proxy_id=record.get("telemetry", {}).get("proxy_id", "unknown"),
                    user_agent=record.get("telemetry", {}).get("user_agent", "unknown"),
                    latency_ms=record.get("telemetry", {}).get("latency_ms", 0),
                    success_rate=0.0,
                    batch_id=batch_id,
                    primary_key=primary_key,
                    outcome="quarantined",
                    error="validation_error",
                )
                continue

            if not verify_content_hash(
                validated.content_hash,
                validated.payload,
                validated.metadata,
                validated.content_type,
                validated.source_provenance,
            ):
                quarantined += 1
                self.quarantine.write(
                    record=record,
                    error="content_hash_mismatch",
                    batch_id=batch_id,
                    trace_id=trace_id,
                )
                self._log_event(
                    trace_id=validated.telemetry.trace_id,
                    proxy_id=validated.telemetry.proxy_id,
                    user_agent=validated.telemetry.user_agent,
                    latency_ms=validated.telemetry.latency_ms,
                    success_rate=0.0,
                    batch_id=batch_id,
                    primary_key=validated.primary_key,
                    outcome="quarantined",
                    error="content_hash_mismatch",
                )
                continue

            row = self._record_to_row(validated)
            shard_path = writer.add(row)
            if shard_path not in parquet_files:
                parquet_files.append(shard_path)
            self.index.insert_record(
                primary_key=validated.primary_key,
                content_hash=validated.content_hash,
                shard_path=shard_path,
                batch_id=batch_id,
                source_provenance=validated.source_provenance,
                trace_id=validated.telemetry.trace_id,
            )
            stored += 1
            self._log_event(
                trace_id=validated.telemetry.trace_id,
                proxy_id=validated.telemetry.proxy_id,
                user_agent=validated.telemetry.user_agent,
                latency_ms=validated.telemetry.latency_ms,
                success_rate=validated.telemetry.success_rate,
                batch_id=batch_id,
                primary_key=validated.primary_key,
                outcome="stored",
            )

        flushed_path = writer.flush()
        if flushed_path and flushed_path not in parquet_files:
            parquet_files.append(flushed_path)
        return IngestReport(
            batch_id=batch_id,
            received=len(records),
            stored=stored,
            quarantined=quarantined,
            parquet_files=parquet_files,
        )

    def close(self) -> None:
        self.index.close()

    @staticmethod
    def _extract_trace_id(record: Dict[str, Any]) -> str:
        telemetry = record.get("telemetry", {})
        return telemetry.get("trace_id") or record.get("trace_id") or str(uuid4())

    @staticmethod
    def _extract_primary_key(record: Dict[str, Any]) -> str:
        return record.get("primary_key", "unknown")

    @staticmethod
    def _record_to_row(record: DataRecord) -> Dict[str, Any]:
        payload_json = json.dumps(
            record.payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
        metadata_json = json.dumps(
            record.metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
        return {
            "primary_key": record.primary_key,
            "batch_id": record.batch_id,
            "source_provenance": record.source_provenance,
            "timestamp": record.timestamp.isoformat(),
            "ingest_ts": datetime.now(timezone.utc).isoformat(),
            "content_hash": record.content_hash,
            "content_type": record.content_type,
            "payload_json": payload_json,
            "metadata_json": metadata_json,
            "trace_id": record.telemetry.trace_id,
            "proxy_id": record.telemetry.proxy_id,
            "user_agent": record.telemetry.user_agent,
            "latency_ms": record.telemetry.latency_ms,
            "success_rate": record.telemetry.success_rate,
        }

    def _log_event(
        self,
        trace_id: str,
        proxy_id: str,
        user_agent: str,
        latency_ms: int,
        success_rate: float,
        batch_id: str,
        primary_key: str,
        outcome: str,
        error: Optional[str] = None,
    ) -> None:
        event = TelemetryEvent(
            trace_id=trace_id,
            proxy_id=proxy_id,
            user_agent=user_agent,
            latency_ms=latency_ms,
            success_rate=success_rate,
            batch_id=batch_id,
            primary_key=primary_key,
            outcome=outcome,
            error=error or "",
        )
        self.telemetry.log(event)
