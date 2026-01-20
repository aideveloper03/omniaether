"""Distributed Parquet-Stream Storage Architecture for AETHER-MINE.

Implements:
- Chunked Parquet writing with batch_id (max 1,000 entries per file)
- Zero-Null policy enforcement
- Versioned, compressed files
- Automatic buffer flushing at 1,000 records or 50MB
"""

import asyncio
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import structlog

from src.core.config import get_settings
from src.core.models import (
    MinedRecord,
    BatchMetadata,
    RecordStatus,
    QuarantinedRecord,
)


logger = structlog.get_logger(__name__)


# Define Parquet schema for MinedRecord
MINED_RECORD_SCHEMA = pa.schema([
    pa.field("record_id", pa.string(), nullable=False),
    pa.field("source_url", pa.string(), nullable=False),
    pa.field("source_domain", pa.string(), nullable=False),
    pa.field("discovery_method", pa.string(), nullable=False),
    pa.field("retrieval_tier", pa.string(), nullable=False),
    pa.field("source_timestamp", pa.timestamp("us", tz="UTC"), nullable=False),
    pa.field("timestamp", pa.timestamp("us", tz="UTC"), nullable=False),
    pa.field("content_hash", pa.string(), nullable=False),
    pa.field("content_type", pa.string(), nullable=False),
    pa.field("content", pa.large_binary(), nullable=False),
    pa.field("content_size_bytes", pa.int64(), nullable=False),
    pa.field("title", pa.string(), nullable=True),
    pa.field("description", pa.string(), nullable=True),
    pa.field("tags", pa.list_(pa.string()), nullable=False),
    pa.field("metadata_json", pa.string(), nullable=False),
    pa.field("status", pa.string(), nullable=False),
    pa.field("batch_id", pa.string(), nullable=False),
    pa.field("shard_id", pa.string(), nullable=False),
    pa.field("intelligence_category", pa.string(), nullable=False),
    pa.field("extracted_entities_json", pa.string(), nullable=False),
    pa.field("risk_score", pa.float64(), nullable=True),
    pa.field("trace_id", pa.string(), nullable=True),
    pa.field("proxy_id", pa.string(), nullable=True),
    pa.field("user_agent", pa.string(), nullable=True),
])


class BatchBuffer:
    """Thread-safe buffer for batching records before Parquet write.
    
    Flushes automatically at:
    - 1,000 records (configurable)
    - 50MB total size (configurable)
    - Configurable time interval
    """
    
    def __init__(
        self,
        max_records: int = 1000,
        max_size_mb: int = 50,
        flush_interval_seconds: int = 60,
    ) -> None:
        self._records: list[MinedRecord] = []
        self._quarantine: list[QuarantinedRecord] = []
        self._lock = threading.RLock()
        self._max_records = max_records
        self._max_size_bytes = max_size_mb * 1024 * 1024
        self._flush_interval = flush_interval_seconds
        self._current_size = 0
        self._last_flush = time.time()
        self._batch_id = str(uuid.uuid4())
        self._flush_callbacks: list[Any] = []
    
    def add_record(self, record: MinedRecord) -> tuple[bool, str | None]:
        """Add a record to the buffer.
        
        Returns:
            Tuple of (should_flush, batch_id_if_flush_needed)
        """
        with self._lock:
            # Enforce Zero-Null policy
            if record.status == RecordStatus.QUARANTINED:
                quarantined = QuarantinedRecord(
                    original_data=record.model_dump(),
                    quarantine_reasons=record.metadata.get("quarantine_reasons", ["unknown"]),
                    source_url=record.source_provenance.url if record.source_provenance else None,
                )
                self._quarantine.append(quarantined)
                logger.warning(
                    "record_quarantined",
                    record_id=record.record_id,
                    reasons=quarantined.quarantine_reasons,
                )
                return False, None
            
            # Update batch and shard IDs
            record.batch_id = self._batch_id
            record.shard_id = str(uuid.uuid4())
            
            # Add to buffer
            self._records.append(record)
            self._current_size += record.content_size_bytes
            
            # Check flush conditions
            should_flush = (
                len(self._records) >= self._max_records
                or self._current_size >= self._max_size_bytes
                or (time.time() - self._last_flush) >= self._flush_interval
            )
            
            if should_flush:
                batch_id = self._batch_id
                return True, batch_id
            
            return False, None
    
    def flush(self) -> tuple[list[MinedRecord], list[QuarantinedRecord], str]:
        """Flush the buffer and return records.
        
        Returns:
            Tuple of (records, quarantined_records, batch_id)
        """
        with self._lock:
            records = self._records
            quarantine = self._quarantine
            batch_id = self._batch_id
            
            # Reset buffer
            self._records = []
            self._quarantine = []
            self._current_size = 0
            self._batch_id = str(uuid.uuid4())
            self._last_flush = time.time()
            
            logger.info(
                "buffer_flushed",
                batch_id=batch_id,
                record_count=len(records),
                quarantine_count=len(quarantine),
            )
            
            return records, quarantine, batch_id
    
    @property
    def pending_count(self) -> int:
        """Get count of pending records."""
        with self._lock:
            return len(self._records)
    
    @property
    def pending_size_bytes(self) -> int:
        """Get size of pending records."""
        with self._lock:
            return self._current_size
    
    @property
    def quarantine_count(self) -> int:
        """Get count of quarantined records."""
        with self._lock:
            return len(self._quarantine)


class ParquetStreamWriter:
    """Chunked Parquet writer with automatic batching and indexing."""
    
    def __init__(
        self,
        output_dir: Path | None = None,
        quarantine_dir: Path | None = None,
        max_records_per_file: int = 1000,
        max_file_size_mb: int = 50,
        compression: str = "snappy",
    ) -> None:
        settings = get_settings()
        self._output_dir = output_dir or settings.parquet_dir
        self._quarantine_dir = quarantine_dir or settings.quarantine_dir
        self._max_records = max_records_per_file
        self._max_size_mb = max_file_size_mb
        self._compression = compression
        self._buffer = BatchBuffer(
            max_records=max_records_per_file,
            max_size_mb=max_file_size_mb,
        )
        self._written_batches: list[BatchMetadata] = []
        self._lock = threading.RLock()
        
        # Ensure directories exist
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._quarantine_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(
            "parquet_writer_initialized",
            output_dir=str(self._output_dir),
            quarantine_dir=str(self._quarantine_dir),
            max_records=max_records_per_file,
            compression=compression,
        )
    
    def _record_to_row(self, record: MinedRecord) -> dict[str, Any]:
        """Convert a MinedRecord to a Parquet row."""
        import orjson
        
        content = record.content
        if isinstance(content, str):
            content = content.encode("utf-8")
        
        return {
            "record_id": record.record_id,
            "source_url": record.source_provenance.url,
            "source_domain": record.source_provenance.domain,
            "discovery_method": record.source_provenance.discovery_method,
            "retrieval_tier": record.source_provenance.retrieval_tier.value,
            "source_timestamp": record.source_provenance.timestamp,
            "timestamp": record.timestamp,
            "content_hash": record.content_hash,
            "content_type": record.content_type,
            "content": content,
            "content_size_bytes": record.content_size_bytes,
            "title": record.title,
            "description": record.description,
            "tags": record.tags,
            "metadata_json": orjson.dumps(record.metadata).decode("utf-8"),
            "status": record.status.value if isinstance(record.status, RecordStatus) else record.status,
            "batch_id": record.batch_id or "",
            "shard_id": record.shard_id or "",
            "intelligence_category": record.intelligence_category.value if hasattr(record.intelligence_category, 'value') else record.intelligence_category,
            "extracted_entities_json": orjson.dumps(record.extracted_entities).decode("utf-8"),
            "risk_score": record.risk_score,
            "trace_id": record.trace_id,
            "proxy_id": record.source_provenance.proxy_id,
            "user_agent": record.source_provenance.user_agent,
        }
    
    def add_record(self, record: MinedRecord) -> BatchMetadata | None:
        """Add a record to the buffer.
        
        Returns BatchMetadata if a batch was written, None otherwise.
        """
        should_flush, batch_id = self._buffer.add_record(record)
        
        if should_flush and batch_id:
            return self._flush_to_parquet()
        
        return None
    
    async def add_record_async(self, record: MinedRecord) -> BatchMetadata | None:
        """Async version of add_record."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.add_record, record)
    
    def _flush_to_parquet(self) -> BatchMetadata:
        """Flush buffer to Parquet file."""
        records, quarantine, batch_id = self._buffer.flush()
        
        if not records:
            # Return empty metadata if no records
            return BatchMetadata(
                batch_id=batch_id,
                record_count=0,
                size_bytes=0,
                file_path="",
                is_finalized=True,
            )
        
        # Generate file path with timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        file_name = f"batch_{batch_id[:8]}_{timestamp}.parquet"
        file_path = self._output_dir / file_name
        
        # Convert records to rows
        rows = [self._record_to_row(r) for r in records]
        
        # Create PyArrow table
        table = pa.Table.from_pylist(rows, schema=MINED_RECORD_SCHEMA)
        
        # Write Parquet file
        pq.write_table(
            table,
            file_path,
            compression=self._compression,
            write_statistics=True,
        )
        
        # Get file size
        file_size = file_path.stat().st_size
        
        # Create batch metadata
        content_hashes = [r.content_hash for r in records]
        primary_keys = [r.record_id for r in records]
        timestamps = [r.timestamp for r in records]
        
        metadata = BatchMetadata(
            batch_id=batch_id,
            record_count=len(records),
            size_bytes=file_size,
            file_path=str(file_path),
            content_hashes=content_hashes,
            primary_keys=primary_keys,
            min_timestamp=min(timestamps),
            max_timestamp=max(timestamps),
            compression=self._compression,
            is_finalized=True,
        )
        
        with self._lock:
            self._written_batches.append(metadata)
        
        logger.info(
            "parquet_batch_written",
            batch_id=batch_id,
            file_path=str(file_path),
            record_count=len(records),
            size_bytes=file_size,
        )
        
        # Write quarantine records
        if quarantine:
            self._write_quarantine(quarantine, batch_id)
        
        return metadata
    
    def _write_quarantine(
        self,
        records: list[QuarantinedRecord],
        batch_id: str,
    ) -> None:
        """Write quarantined records to separate Parquet file."""
        import orjson
        
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        file_name = f"quarantine_{batch_id[:8]}_{timestamp}.parquet"
        file_path = self._quarantine_dir / file_name
        
        # Create quarantine schema
        quarantine_schema = pa.schema([
            pa.field("record_id", pa.string(), nullable=False),
            pa.field("original_data_json", pa.string(), nullable=False),
            pa.field("quarantine_reasons", pa.list_(pa.string()), nullable=False),
            pa.field("quarantine_timestamp", pa.timestamp("us", tz="UTC"), nullable=False),
            pa.field("source_url", pa.string(), nullable=True),
            pa.field("recovery_attempts", pa.int32(), nullable=False),
        ])
        
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
        
        table = pa.Table.from_pylist(rows, schema=quarantine_schema)
        pq.write_table(table, file_path, compression=self._compression)
        
        logger.warning(
            "quarantine_batch_written",
            batch_id=batch_id,
            file_path=str(file_path),
            record_count=len(records),
        )
    
    def flush(self) -> BatchMetadata:
        """Force flush the buffer."""
        return self._flush_to_parquet()
    
    async def flush_async(self) -> BatchMetadata:
        """Async version of flush."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.flush)
    
    def get_written_batches(self) -> list[BatchMetadata]:
        """Get list of written batch metadata."""
        with self._lock:
            return list(self._written_batches)
    
    @property
    def pending_records(self) -> int:
        """Get count of pending records in buffer."""
        return self._buffer.pending_count
    
    @property
    def pending_size_bytes(self) -> int:
        """Get size of pending data in buffer."""
        return self._buffer.pending_size_bytes


class ParquetReader:
    """Reader for Parquet shards with filtering capabilities."""
    
    def __init__(self, data_dir: Path | None = None) -> None:
        settings = get_settings()
        self._data_dir = data_dir or settings.parquet_dir
    
    def read_batch(self, batch_id: str) -> pa.Table | None:
        """Read a specific batch by ID."""
        for file_path in self._data_dir.glob(f"batch_{batch_id[:8]}_*.parquet"):
            return pq.read_table(file_path)
        return None
    
    def read_all(self) -> pa.Table:
        """Read all Parquet files into a single table."""
        files = list(self._data_dir.glob("batch_*.parquet"))
        if not files:
            return pa.Table.from_pylist([], schema=MINED_RECORD_SCHEMA)
        
        tables = [pq.read_table(f) for f in files]
        return pa.concat_tables(tables)
    
    def query_by_hash(self, content_hash: str) -> pa.Table:
        """Query records by content hash."""
        import duckdb
        
        table = self.read_all()
        conn = duckdb.connect()
        conn.register("records", table)
        
        result = conn.execute(
            "SELECT * FROM records WHERE content_hash = ?",
            [content_hash]
        ).arrow()
        
        return result
    
    def query_by_domain(self, domain: str) -> pa.Table:
        """Query records by source domain."""
        import duckdb
        
        table = self.read_all()
        conn = duckdb.connect()
        conn.register("records", table)
        
        result = conn.execute(
            "SELECT * FROM records WHERE source_domain = ?",
            [domain]
        ).arrow()
        
        return result
