"""Quarantine Manager for Zero-Null Policy Enforcement.

Handles records that fail validation and provides recovery mechanisms.
"""

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import structlog
import orjson

from src.core.config import get_settings
from src.core.models import QuarantinedRecord, MinedRecord, SourceProvenance, FallbackTier


logger = structlog.get_logger(__name__)


# Quarantine Parquet schema
QUARANTINE_SCHEMA = pa.schema([
    pa.field("record_id", pa.string(), nullable=False),
    pa.field("original_data_json", pa.string(), nullable=False),
    pa.field("quarantine_reasons", pa.list_(pa.string()), nullable=False),
    pa.field("quarantine_timestamp", pa.timestamp("us", tz="UTC"), nullable=False),
    pa.field("source_url", pa.string(), nullable=True),
    pa.field("recovery_attempts", pa.int32(), nullable=False),
])


class QuarantineManager:
    """Manager for quarantined records that failed Zero-Null validation."""
    
    def __init__(self, quarantine_dir: Path | None = None) -> None:
        settings = get_settings()
        self._quarantine_dir = quarantine_dir or settings.quarantine_dir
        self._quarantine_dir.mkdir(parents=True, exist_ok=True)
        self._pending: list[QuarantinedRecord] = []
        self._lock = threading.RLock()
        self._max_pending = 100
        
        logger.info(
            "quarantine_manager_initialized",
            quarantine_dir=str(self._quarantine_dir),
        )
    
    def quarantine(
        self,
        original_data: dict[str, Any],
        reasons: list[str],
        source_url: str | None = None,
    ) -> QuarantinedRecord:
        """Quarantine a record that failed validation."""
        record = QuarantinedRecord(
            original_data=original_data,
            quarantine_reasons=reasons,
            source_url=source_url,
        )
        
        with self._lock:
            self._pending.append(record)
            
            if len(self._pending) >= self._max_pending:
                self._flush()
        
        logger.warning(
            "record_quarantined",
            record_id=record.record_id,
            reasons=reasons,
            source_url=source_url,
        )
        
        return record
    
    def _flush(self) -> None:
        """Flush pending quarantined records to Parquet."""
        with self._lock:
            if not self._pending:
                return
            
            records = self._pending
            self._pending = []
        
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        file_name = f"quarantine_{timestamp}.parquet"
        file_path = self._quarantine_dir / file_name
        
        rows = [
            {
                "record_id": r.record_id,
                "original_data_json": orjson.dumps(r.original_data).decode("utf-8"),
                "quarantine_reasons": r.quarantine_reasons,
                "quarantine_timestamp": r.quarantine_timestamp,
                "source_url": r.source_url,
                "recovery_attempts": r.recovery_attempts,
            }
            for r in records
        ]
        
        table = pa.Table.from_pylist(rows, schema=QUARANTINE_SCHEMA)
        pq.write_table(table, file_path, compression="snappy")
        
        logger.info(
            "quarantine_flushed",
            file_path=str(file_path),
            record_count=len(records),
        )
    
    def flush(self) -> None:
        """Force flush pending records."""
        self._flush()
    
    def get_quarantine_stats(self) -> dict[str, Any]:
        """Get quarantine statistics."""
        files = list(self._quarantine_dir.glob("quarantine_*.parquet"))
        total_records = 0
        reasons_count: dict[str, int] = {}
        
        for file_path in files:
            table = pq.read_table(file_path)
            total_records += len(table)
            
            for reasons in table.column("quarantine_reasons").to_pylist():
                for reason in reasons:
                    reasons_count[reason] = reasons_count.get(reason, 0) + 1
        
        return {
            "total_quarantined": total_records,
            "pending_count": len(self._pending),
            "file_count": len(files),
            "reasons_breakdown": reasons_count,
        }
    
    def attempt_recovery(self, record_id: str) -> MinedRecord | None:
        """Attempt to recover a quarantined record.
        
        This method tries to fill in missing fields with defaults
        or fetch missing data.
        """
        # Find the record in quarantine files
        for file_path in self._quarantine_dir.glob("quarantine_*.parquet"):
            table = pq.read_table(file_path)
            
            for i, rid in enumerate(table.column("record_id").to_pylist()):
                if rid == record_id:
                    row = {
                        col: table.column(col)[i].as_py()
                        for col in table.column_names
                    }
                    
                    original_data = orjson.loads(row["original_data_json"])
                    reasons = row["quarantine_reasons"]
                    
                    # Try to fix missing fields
                    recovered_data = self._attempt_fix(original_data, reasons)
                    
                    if recovered_data:
                        logger.info(
                            "record_recovered",
                            record_id=record_id,
                            original_reasons=reasons,
                        )
                        return recovered_data
                    
                    logger.warning(
                        "recovery_failed",
                        record_id=record_id,
                        reasons=reasons,
                    )
                    return None
        
        return None
    
    def _attempt_fix(
        self,
        original_data: dict[str, Any],
        reasons: list[str],
    ) -> MinedRecord | None:
        """Attempt to fix validation issues."""
        fixed_data = dict(original_data)
        
        for reason in reasons:
            if reason == "missing_source_provenance":
                # Create minimal provenance if we have any URL info
                if "url" in fixed_data or "source_url" in original_data:
                    url = fixed_data.get("url") or original_data.get("source_url", "unknown://recovered")
                    fixed_data["source_provenance"] = SourceProvenance(
                        url=url,
                        domain="recovered",
                        discovery_method="quarantine_recovery",
                        retrieval_tier=FallbackTier.HUMAN_IN_LOOP,
                    )
                else:
                    return None
            
            elif reason == "missing_timestamp":
                fixed_data["timestamp"] = datetime.now(timezone.utc)
            
            elif reason == "missing_content_hash":
                content = fixed_data.get("content", b"")
                if content:
                    fixed_data["content_hash"] = MinedRecord.compute_content_hash(content)
                else:
                    return None
        
        try:
            return MinedRecord(**fixed_data)
        except Exception as e:
            logger.error("recovery_validation_failed", error=str(e))
            return None
    
    def list_quarantined(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List quarantined records."""
        all_records: list[dict[str, Any]] = []
        
        for file_path in sorted(self._quarantine_dir.glob("quarantine_*.parquet")):
            table = pq.read_table(file_path)
            
            for i in range(len(table)):
                record = {
                    col: table.column(col)[i].as_py()
                    for col in table.column_names
                }
                all_records.append(record)
        
        return all_records[offset:offset + limit]
    
    def purge_old(self, days: int = 30) -> int:
        """Purge quarantine records older than specified days."""
        import os
        from datetime import timedelta
        
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        purged = 0
        
        for file_path in self._quarantine_dir.glob("quarantine_*.parquet"):
            # Extract timestamp from filename
            try:
                timestamp_str = file_path.stem.split("_")[1]
                file_time = datetime.strptime(timestamp_str, "%Y%m%d")
                file_time = file_time.replace(tzinfo=timezone.utc)
                
                if file_time < cutoff:
                    record_count = len(pq.read_table(file_path))
                    os.remove(file_path)
                    purged += record_count
                    
                    logger.info(
                        "quarantine_file_purged",
                        file_path=str(file_path),
                        record_count=record_count,
                    )
            except (ValueError, IndexError):
                continue
        
        return purged
