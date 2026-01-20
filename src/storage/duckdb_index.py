import duckdb
import os
from loguru import logger
from src.core.config import settings

class DuckDBIndex:
    def __init__(self):
        self.db_path = settings.DUCKDB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize the DuckDB schema."""
        try:
            conn = duckdb.connect(self.db_path)
            # Create a global index table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS file_index (
                    primary_key VARCHAR,
                    content_hash VARCHAR,
                    file_path VARCHAR,
                    batch_id VARCHAR,
                    timestamp TIMESTAMP,
                    record_type VARCHAR,
                    PRIMARY KEY (content_hash)
                )
            """)
            conn.close()
            logger.info(f"DuckDB index initialized at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize DuckDB: {e}")
            raise

    def register_batch(self, batch_metadata: list[dict]):
        """
        Register a batch of records into the index.
        batch_metadata: List of dicts with keys matching the table schema.
        """
        if not batch_metadata:
            return

        conn = duckdb.connect(self.db_path)
        try:
            # Efficiently insert multiple rows
            # We assume batch_metadata is a list of tuples or compatible dicts
            # For simplicity, we can use an appender or executemany
            
            # Prepare data for insertion
            values = []
            for item in batch_metadata:
                values.append((
                    item['primary_key'], 
                    item['content_hash'], 
                    item['file_path'], 
                    item['batch_id'], 
                    item['timestamp'],
                    item['record_type']
                ))
            
            conn.executemany("""
                INSERT OR REPLACE INTO file_index 
                (primary_key, content_hash, file_path, batch_id, timestamp, record_type)
                VALUES (?, ?, ?, ?, ?, ?)
            """, values)
            
            logger.info(f"Registered {len(values)} records in DuckDB index.")
        except Exception as e:
            logger.error(f"Failed to register batch in DuckDB: {e}")
            raise
        finally:
            conn.close()

    def lookup(self, content_hash: str):
        conn = duckdb.connect(self.db_path)
        try:
            result = conn.execute("SELECT * FROM file_index WHERE content_hash = ?", [content_hash]).fetchone()
            return result
        finally:
            conn.close()

# Singleton instance
duckdb_index = DuckDBIndex()
