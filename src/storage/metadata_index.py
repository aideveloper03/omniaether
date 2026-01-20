from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any, Dict, List

import duckdb


class MetadataIndex:
    def __init__(self, db_path: str) -> None:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn = duckdb.connect(db_path)
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata_index (
                primary_key VARCHAR,
                content_hash VARCHAR,
                shard_path VARCHAR,
                batch_id VARCHAR,
                source_provenance VARCHAR,
                trace_id VARCHAR,
                ingest_ts TIMESTAMP
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_primary_key ON metadata_index(primary_key)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_content_hash ON metadata_index(content_hash)"
        )

    def insert_record(
        self,
        primary_key: str,
        content_hash: str,
        shard_path: str,
        batch_id: str,
        source_provenance: str,
        trace_id: str,
    ) -> None:
        ingest_ts = datetime.now(timezone.utc)
        self._conn.execute(
            """
            INSERT INTO metadata_index
            (primary_key, content_hash, shard_path, batch_id, source_provenance, trace_id, ingest_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [primary_key, content_hash, shard_path, batch_id, source_provenance, trace_id, ingest_ts],
        )

    def find_by_primary_key(self, primary_key: str) -> List[Dict[str, Any]]:
        cursor = self._conn.execute(
            "SELECT * FROM metadata_index WHERE primary_key = ?", [primary_key]
        )
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    def find_by_content_hash(self, content_hash: str) -> List[Dict[str, Any]]:
        cursor = self._conn.execute(
            "SELECT * FROM metadata_index WHERE content_hash = ?", [content_hash]
        )
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    def close(self) -> None:
        self._conn.close()
