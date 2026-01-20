import os
import uuid
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from typing import List, Union, Any
from datetime import datetime
from src.core.config import settings
from src.core.telemetry import logger, PerformanceTimer
from src.storage.models import BaseRecord, ShadowApiRecord, DocumentRecord, IntelligenceRecord
from src.storage.duckdb_index import duckdb_index

class ParquetStreamWriter:
    def __init__(self, batch_size: int = 1000):
        self.batch_size = batch_size
        self.buffer: List[BaseRecord] = []
        self.output_dir = settings.PARQUET_OUTPUT_DIR
        self.quarantine_dir = settings.QUARANTINE_DIR
        
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.quarantine_dir, exist_ok=True)

    def add_record(self, record: Union[BaseRecord, dict]):
        """
        Add a record to the buffer.
        If record is a dict, it attempts to validate it against known models.
        """
        validated_record = self._validate(record)
        if validated_record:
            self.buffer.append(validated_record)
        
        if len(self.buffer) >= self.batch_size:
            self.flush()

    def _validate(self, record: Any) -> Union[BaseRecord, None]:
        try:
            if isinstance(record, BaseRecord):
                return record
            # Try to infer type or expect caller to pass BaseRecord
            # For now, strict: must be BaseRecord instance
            logger.warning(f"Record rejected: Must be instance of BaseRecord, got {type(record)}")
            self._quarantine(record, "invalid_type")
            return None
        except Exception as e:
            self._quarantine(record, str(e))
            return None

    def _quarantine(self, record: Any, reason: str):
        """Write invalid record to quarantine JSON."""
        try:
            filename = f"quarantine_{uuid.uuid4()}.json"
            path = os.path.join(self.quarantine_dir, filename)
            import json
            
            data = record.model_dump() if isinstance(record, BaseRecord) else str(record)
            
            with open(path, "w") as f:
                json.dump({"data": data, "reason": reason, "timestamp": str(datetime.utcnow())}, f)
        except Exception as e:
            logger.error(f"Failed to quarantine record: {e}")

    def flush(self):
        """Write buffered records to Parquet and update index."""
        if not self.buffer:
            return

        batch_id = str(uuid.uuid4())
        filename = f"batch_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{batch_id}.parquet"
        file_path = os.path.join(self.output_dir, filename)

        with PerformanceTimer("parquet_flush", {"batch_size": len(self.buffer)}):
            try:
                # Convert buffer to DataFrame
                # We need to handle mixed types if they exist, but usually we should have consistent types or separate streams.
                # For this implementation, we'll assume a mix is possible but we flatten them.
                # Ideally, we separate by type (ShadowApi, Document, etc.)
                
                # Group by type
                grouped = {}
                for rec in self.buffer:
                    t = type(rec).__name__
                    if t not in grouped:
                        grouped[t] = []
                    grouped[t].append(rec.model_dump())

                index_entries = []

                for record_type, records in grouped.items():
                    # Create separate file per type for cleaner schema
                    type_filename = f"{record_type}_{filename}"
                    type_path = os.path.join(self.output_dir, type_filename)
                    
                    df = pd.DataFrame(records)
                    table = pa.Table.from_pandas(df)
                    pq.write_table(table, type_path, compression='snappy')
                    
                    # Prepare index entries
                    for rec in records:
                        index_entries.append({
                            "primary_key": rec.get("url") or rec.get("file_name") or rec.get("trace_id"), # Best effort PK
                            "content_hash": rec["content_hash"],
                            "file_path": type_path,
                            "batch_id": batch_id,
                            "timestamp": rec["timestamp"],
                            "record_type": record_type
                        })

                # Update DuckDB
                duckdb_index.register_batch(index_entries)
                
                logger.info(f"Flushed {len(self.buffer)} records to {self.output_dir}")
                self.buffer = []
                
            except Exception as e:
                logger.error(f"Failed to flush parquet batch: {e}")
                # Don't clear buffer on failure? Or quarantine all?
                # For now, we attempt to quarantine the whole buffer
                for rec in self.buffer:
                    self._quarantine(rec, f"batch_flush_failure: {str(e)}")
                self.buffer = []

# Global writer instance
stream_writer = ParquetStreamWriter()
