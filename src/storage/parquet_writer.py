from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import pyarrow as pa
import pyarrow.parquet as pq


class ParquetShardWriter:
    def __init__(
        self,
        base_dir: str,
        batch_id: str,
        max_records: int,
        max_bytes: int,
    ) -> None:
        self.base_dir = base_dir
        self.batch_id = batch_id
        self.max_records = max_records
        self.max_bytes = max_bytes
        self._rows: List[Dict[str, Any]] = []
        self._bytes_estimate = 0
        self._shard_index = 0
        self._current_shard_path: Optional[str] = None

        self._batch_dir = os.path.join(self.base_dir, self.batch_id)
        os.makedirs(self._batch_dir, exist_ok=True)

    def _new_shard_path(self) -> str:
        filename = f"{self.batch_id}_chunk_{self._shard_index:05d}.parquet"
        return os.path.join(self._batch_dir, filename)

    @staticmethod
    def _estimate_bytes(row: Dict[str, Any]) -> int:
        return len(
            json.dumps(row, separators=(",", ":"), sort_keys=True, ensure_ascii=True)
        )

    @property
    def current_shard_path(self) -> Optional[str]:
        return self._current_shard_path

    def add(self, row: Dict[str, Any]) -> str:
        if not self._rows:
            self._current_shard_path = self._new_shard_path()
        self._rows.append(row)
        self._bytes_estimate += self._estimate_bytes(row)
        shard_path = self._current_shard_path
        if shard_path is None:
            raise RuntimeError("failed to resolve shard path")
        if len(self._rows) >= self.max_records or self._bytes_estimate >= self.max_bytes:
            self.flush()
        return shard_path

    def flush(self) -> Optional[str]:
        if not self._rows:
            return None
        if self._current_shard_path is None:
            raise RuntimeError("no shard path to flush")
        table = pa.Table.from_pylist(self._rows)
        pq.write_table(table, self._current_shard_path, compression="zstd")
        flushed_path = self._current_shard_path
        self._rows = []
        self._bytes_estimate = 0
        self._current_shard_path = None
        self._shard_index += 1
        return flushed_path
