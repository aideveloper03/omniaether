from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class AppConfig:
    data_dir: str
    parquet_dir: str
    quarantine_dir: str
    index_path: str
    telemetry_path: str
    max_records_per_file: int
    max_bytes_per_file: int

    @classmethod
    def from_env(cls) -> "AppConfig":
        data_dir = os.getenv("AETHER_DATA_DIR", "data")
        parquet_dir = os.getenv(
            "AETHER_PARQUET_DIR", os.path.join(data_dir, "parquet_shards")
        )
        quarantine_dir = os.getenv(
            "AETHER_QUARANTINE_DIR", os.path.join(data_dir, "quarantine_shard")
        )
        index_path = os.getenv(
            "AETHER_INDEX_PATH", os.path.join(data_dir, "index", "metadata.duckdb")
        )
        telemetry_path = os.getenv(
            "AETHER_TELEMETRY_PATH", os.path.join(data_dir, "telemetry", "requests.jsonl")
        )
        max_records_per_file = int(
            os.getenv("AETHER_MAX_RECORDS_PER_FILE", "1000")
        )
        max_bytes_per_file = int(
            os.getenv("AETHER_MAX_BYTES_PER_FILE", str(50 * 1024 * 1024))
        )
        return cls(
            data_dir=data_dir,
            parquet_dir=parquet_dir,
            quarantine_dir=quarantine_dir,
            index_path=index_path,
            telemetry_path=telemetry_path,
            max_records_per_file=max_records_per_file,
            max_bytes_per_file=max_bytes_per_file,
        )
