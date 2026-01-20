# Debugging Guide

## Tracing Failures
Every request and task is assigned a `trace_id`. Use this ID to correlate logs across services.

### Common Issues

#### 1. Parquet Flush Failures
If records fail validation or filesystem writes fail:
- Check `/workspace/data/quarantine/`.
- Files are named `quarantine_{uuid}.json`.
- `reason` field explains the validation error (e.g., missing field, null value).

#### 2. Celery Worker Hangs
- Check Redis connection: `redis-cli ping`.
- Verify Playwright browser installation: `playwright install`.
- Logs are output to stderr/stdout by default.

#### 3. DuckDB Locks
- DuckDB is embedded. Ensure only the writer process (or single coordinated writer) holds the write lock.
- In this architecture, the `stream_writer` is designed to be the primary writer. If multiple workers write, ensure they write to separate files and the `DuckDBIndex` handles concurrency safely (via connection pooling or strict locking). *Note: Current implementation assumes a shared filesystem but independent worker processes may need a centralized indexer service for production safety.*

## Telemetry
Performance metrics are logged with the `PERFORMANCE_METRIC` tag.
- `duration_ms`: Execution time.
- `status`: Success/Failed.
