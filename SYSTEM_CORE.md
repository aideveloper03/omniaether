# SYSTEM_CORE

This repository implements a compliance-first ingestion and storage backbone for
structured data capture. The core design focuses on strict validation, traceable
telemetry, and deterministic storage to support high-concurrency pipelines.

## Core Flow

1. **Ingest**: Records are received via the FastAPI controller or CLI.
2. **Enrich**: Optional lightweight parsing adds intelligence tags to metadata.
3. **Validate**: Pydantic v2 enforces a zero-null policy.
4. **Store**: Chunked Parquet shards are written per `batch_id`.
5. **Index**: DuckDB tracks `primary_key` and `content_hash` for fast lookup.
6. **Telemetry**: Every record logs `trace_id`, latency, success rate, and proxy.

## Batch Shim

The `ParquetShardWriter` buffers rows and flushes when either:

- **1,000 records** are accumulated, or
- **50MB** of estimated JSON payload size is reached.

Each shard is written to:

```
data/parquet_shards/<batch_id>/<batch_id>_chunk_00000.parquet
```

## Zero-Null Policy

The `DataRecord` model rejects missing or `null` fields. Any record missing
`source_provenance`, `timestamp`, or `content_hash` is rejected and routed to
`quarantine_shard` with a structured error entry.

## Telemetry

Telemetry is stored as JSONL under:

```
data/telemetry/requests.jsonl
```

This includes the `trace_id`, `proxy_id`, `user_agent`, `latency_ms`, and a
per-record `success_rate` so batch-level reliability can be reconstructed.

## Concurrency Layer

- **FastAPI**: API controller for ingestion.
- **Celery**: Task swarm that can process large batches asynchronously.
- **Redis**: Recommended broker/backend (configurable via environment).
