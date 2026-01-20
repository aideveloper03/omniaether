"""DuckDB Global Metadata Index for AETHER-MINE.

Provides sub-millisecond lookups across all Parquet shards by tracking:
- Primary_Key (record_id)
- Content_Hash
- Batch metadata
- Full-text search capabilities
"""

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import structlog

from src.core.config import get_settings
from src.core.models import BatchMetadata


logger = structlog.get_logger(__name__)


class MetadataIndex:
    """Global DuckDB metadata index for fast lookups across Parquet shards."""
    
    _instance: "MetadataIndex | None" = None
    _lock = threading.Lock()
    
    def __new__(cls, db_path: Path | None = None) -> "MetadataIndex":
        """Singleton pattern for shared index."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, db_path: Path | None = None) -> None:
        if self._initialized:
            return
        
        settings = get_settings()
        self._db_path = db_path or settings.duckdb_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._conn = duckdb.connect(str(self._db_path))
        self._setup_schema()
        self._initialized = True
        
        logger.info("duckdb_index_initialized", db_path=str(self._db_path))
    
    def _setup_schema(self) -> None:
        """Create index tables if they don't exist."""
        # Main record index
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS record_index (
                record_id VARCHAR PRIMARY KEY,
                content_hash VARCHAR NOT NULL,
                batch_id VARCHAR NOT NULL,
                shard_id VARCHAR NOT NULL,
                file_path VARCHAR NOT NULL,
                source_url VARCHAR NOT NULL,
                source_domain VARCHAR NOT NULL,
                content_type VARCHAR NOT NULL,
                content_size_bytes BIGINT NOT NULL,
                timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                intelligence_category VARCHAR,
                risk_score DOUBLE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Content hash index for deduplication
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS content_hash_index (
                content_hash VARCHAR PRIMARY KEY,
                record_id VARCHAR NOT NULL,
                first_seen TIMESTAMP WITH TIME ZONE NOT NULL,
                occurrence_count INTEGER DEFAULT 1,
                FOREIGN KEY (record_id) REFERENCES record_index(record_id)
            )
        """)
        
        # Batch metadata table
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS batch_metadata (
                batch_id VARCHAR PRIMARY KEY,
                shard_id VARCHAR NOT NULL,
                file_path VARCHAR NOT NULL,
                record_count INTEGER NOT NULL,
                size_bytes BIGINT NOT NULL,
                min_timestamp TIMESTAMP WITH TIME ZONE,
                max_timestamp TIMESTAMP WITH TIME ZONE,
                compression VARCHAR DEFAULT 'snappy',
                is_finalized BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Domain statistics table
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS domain_stats (
                domain VARCHAR PRIMARY KEY,
                record_count INTEGER DEFAULT 0,
                total_bytes BIGINT DEFAULT 0,
                first_seen TIMESTAMP WITH TIME ZONE,
                last_seen TIMESTAMP WITH TIME ZONE,
                avg_content_size DOUBLE
            )
        """)
        
        # Create indexes for fast lookups
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_record_content_hash 
            ON record_index(content_hash)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_record_domain 
            ON record_index(source_domain)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_record_batch 
            ON record_index(batch_id)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_record_timestamp 
            ON record_index(timestamp)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_record_category 
            ON record_index(intelligence_category)
        """)
        
        self._conn.commit()
    
    def index_record(
        self,
        record_id: str,
        content_hash: str,
        batch_id: str,
        shard_id: str,
        file_path: str,
        source_url: str,
        source_domain: str,
        content_type: str,
        content_size_bytes: int,
        timestamp: datetime,
        intelligence_category: str | None = None,
        risk_score: float | None = None,
    ) -> bool:
        """Index a single record.
        
        Returns True if this is a new record, False if duplicate content_hash.
        """
        try:
            # Check for duplicate content hash
            existing = self._conn.execute(
                "SELECT record_id FROM content_hash_index WHERE content_hash = ?",
                [content_hash]
            ).fetchone()
            
            is_new = existing is None
            
            # Insert into record index
            self._conn.execute("""
                INSERT OR REPLACE INTO record_index (
                    record_id, content_hash, batch_id, shard_id, file_path,
                    source_url, source_domain, content_type, content_size_bytes,
                    timestamp, intelligence_category, risk_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                record_id, content_hash, batch_id, shard_id, file_path,
                source_url, source_domain, content_type, content_size_bytes,
                timestamp, intelligence_category, risk_score
            ])
            
            # Update content hash index
            if is_new:
                self._conn.execute("""
                    INSERT INTO content_hash_index (content_hash, record_id, first_seen)
                    VALUES (?, ?, ?)
                """, [content_hash, record_id, timestamp])
            else:
                self._conn.execute("""
                    UPDATE content_hash_index 
                    SET occurrence_count = occurrence_count + 1
                    WHERE content_hash = ?
                """, [content_hash])
            
            # Update domain stats
            self._conn.execute("""
                INSERT INTO domain_stats (
                    domain, record_count, total_bytes, first_seen, last_seen, avg_content_size
                ) VALUES (?, 1, ?, ?, ?, ?)
                ON CONFLICT (domain) DO UPDATE SET
                    record_count = domain_stats.record_count + 1,
                    total_bytes = domain_stats.total_bytes + EXCLUDED.total_bytes,
                    last_seen = EXCLUDED.last_seen,
                    avg_content_size = (domain_stats.total_bytes + EXCLUDED.total_bytes) / 
                                      (domain_stats.record_count + 1)
            """, [source_domain, content_size_bytes, timestamp, timestamp, float(content_size_bytes)])
            
            self._conn.commit()
            
            logger.debug(
                "record_indexed",
                record_id=record_id,
                content_hash=content_hash[:16],
                is_new=is_new,
            )
            
            return is_new
            
        except Exception as e:
            logger.error("index_record_failed", record_id=record_id, error=str(e))
            self._conn.rollback()
            raise
    
    def index_batch(self, metadata: BatchMetadata) -> None:
        """Index batch metadata."""
        try:
            self._conn.execute("""
                INSERT OR REPLACE INTO batch_metadata (
                    batch_id, shard_id, file_path, record_count, size_bytes,
                    min_timestamp, max_timestamp, compression, is_finalized
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                metadata.batch_id,
                metadata.shard_id,
                metadata.file_path,
                metadata.record_count,
                metadata.size_bytes,
                metadata.min_timestamp,
                metadata.max_timestamp,
                metadata.compression,
                metadata.is_finalized,
            ])
            self._conn.commit()
            
            logger.info(
                "batch_indexed",
                batch_id=metadata.batch_id,
                record_count=metadata.record_count,
            )
            
        except Exception as e:
            logger.error("index_batch_failed", batch_id=metadata.batch_id, error=str(e))
            self._conn.rollback()
            raise
    
    def lookup_by_hash(self, content_hash: str) -> dict[str, Any] | None:
        """Sub-millisecond lookup by content hash."""
        result = self._conn.execute("""
            SELECT r.*, c.first_seen, c.occurrence_count
            FROM record_index r
            JOIN content_hash_index c ON r.content_hash = c.content_hash
            WHERE r.content_hash = ?
        """, [content_hash]).fetchone()
        
        if result:
            columns = [
                "record_id", "content_hash", "batch_id", "shard_id", "file_path",
                "source_url", "source_domain", "content_type", "content_size_bytes",
                "timestamp", "intelligence_category", "risk_score", "created_at",
                "first_seen", "occurrence_count"
            ]
            return dict(zip(columns, result))
        return None
    
    def lookup_by_id(self, record_id: str) -> dict[str, Any] | None:
        """Sub-millisecond lookup by record ID."""
        result = self._conn.execute("""
            SELECT * FROM record_index WHERE record_id = ?
        """, [record_id]).fetchone()
        
        if result:
            columns = [
                "record_id", "content_hash", "batch_id", "shard_id", "file_path",
                "source_url", "source_domain", "content_type", "content_size_bytes",
                "timestamp", "intelligence_category", "risk_score", "created_at"
            ]
            return dict(zip(columns, result))
        return None
    
    def exists_by_hash(self, content_hash: str) -> bool:
        """Check if content hash exists (for deduplication)."""
        result = self._conn.execute(
            "SELECT 1 FROM content_hash_index WHERE content_hash = ?",
            [content_hash]
        ).fetchone()
        return result is not None
    
    def search_by_domain(
        self,
        domain: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Search records by domain."""
        results = self._conn.execute("""
            SELECT * FROM record_index 
            WHERE source_domain = ?
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        """, [domain, limit, offset]).fetchall()
        
        columns = [
            "record_id", "content_hash", "batch_id", "shard_id", "file_path",
            "source_url", "source_domain", "content_type", "content_size_bytes",
            "timestamp", "intelligence_category", "risk_score", "created_at"
        ]
        return [dict(zip(columns, row)) for row in results]
    
    def search_by_category(
        self,
        category: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Search records by intelligence category."""
        results = self._conn.execute("""
            SELECT * FROM record_index 
            WHERE intelligence_category = ?
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        """, [category, limit, offset]).fetchall()
        
        columns = [
            "record_id", "content_hash", "batch_id", "shard_id", "file_path",
            "source_url", "source_domain", "content_type", "content_size_bytes",
            "timestamp", "intelligence_category", "risk_score", "created_at"
        ]
        return [dict(zip(columns, row)) for row in results]
    
    def search_by_risk_score(
        self,
        min_score: float = 0.5,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Search records with risk score above threshold."""
        results = self._conn.execute("""
            SELECT * FROM record_index 
            WHERE risk_score >= ?
            ORDER BY risk_score DESC
            LIMIT ?
        """, [min_score, limit]).fetchall()
        
        columns = [
            "record_id", "content_hash", "batch_id", "shard_id", "file_path",
            "source_url", "source_domain", "content_type", "content_size_bytes",
            "timestamp", "intelligence_category", "risk_score", "created_at"
        ]
        return [dict(zip(columns, row)) for row in results]
    
    def get_domain_stats(self) -> list[dict[str, Any]]:
        """Get statistics for all domains."""
        results = self._conn.execute("""
            SELECT * FROM domain_stats ORDER BY record_count DESC
        """).fetchall()
        
        columns = [
            "domain", "record_count", "total_bytes", "first_seen", 
            "last_seen", "avg_content_size"
        ]
        return [dict(zip(columns, row)) for row in results]
    
    def get_global_stats(self) -> dict[str, Any]:
        """Get global index statistics."""
        record_count = self._conn.execute(
            "SELECT COUNT(*) FROM record_index"
        ).fetchone()[0]
        
        unique_hashes = self._conn.execute(
            "SELECT COUNT(*) FROM content_hash_index"
        ).fetchone()[0]
        
        domain_count = self._conn.execute(
            "SELECT COUNT(*) FROM domain_stats"
        ).fetchone()[0]
        
        batch_count = self._conn.execute(
            "SELECT COUNT(*) FROM batch_metadata WHERE is_finalized = TRUE"
        ).fetchone()[0]
        
        total_bytes = self._conn.execute(
            "SELECT COALESCE(SUM(size_bytes), 0) FROM batch_metadata"
        ).fetchone()[0]
        
        return {
            "total_records": record_count,
            "unique_content_hashes": unique_hashes,
            "unique_domains": domain_count,
            "finalized_batches": batch_count,
            "total_storage_bytes": total_bytes,
            "duplicate_rate": 1 - (unique_hashes / record_count) if record_count > 0 else 0,
        }
    
    def execute_raw(self, query: str, params: list[Any] | None = None) -> list[Any]:
        """Execute raw SQL query."""
        if params:
            return self._conn.execute(query, params).fetchall()
        return self._conn.execute(query).fetchall()
    
    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
        MetadataIndex._instance = None
        self._initialized = False


def get_index() -> MetadataIndex:
    """Get the global metadata index instance."""
    return MetadataIndex()
