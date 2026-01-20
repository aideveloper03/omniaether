# DEBUGGING

## Batch Failures

1. **Check quarantine output**
   - Location: `data/quarantine_shard/quarantine_<batch_id>.jsonl`
   - Each entry includes the batch ID, trace ID, error, and raw record.

2. **Inspect telemetry logs**
   - Location: `data/telemetry/requests.jsonl`
   - Search by `trace_id` to correlate request latency and outcomes.

3. **Validate content hashes**
   - The storage layer verifies `content_hash` using a canonical JSON hash of
     payload and metadata plus content type and provenance.

4. **Confirm Parquet shards**
   - Location: `data/parquet_shards/<batch_id>/`
   - Each shard contains `payload_json` and `metadata_json` as ASCII JSON.

5. **Query the index**
   - Location: `data/index/metadata.duckdb`
   - Example query:
     ```sql
     SELECT * FROM metadata_index WHERE primary_key = '...';
     ```

## Common Issues

- **ValidationError**: Fields missing or `null`. Fix the input record.
- **content_hash_mismatch**: The `content_hash` does not match the canonical
  payload+metadata hash. Recompute before ingestion.
- **Telemetry gaps**: Ensure every record supplies `trace_id`, `latency_ms`,
  `success_rate`, `proxy_id`, and `user_agent`.
