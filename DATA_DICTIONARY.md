# DATA_DICTIONARY

## Record Schema (`DataRecord`)

| Field | Type | Required | Constraints |
| --- | --- | --- | --- |
| `primary_key` | string | yes | non-empty |
| `batch_id` | string | yes | non-empty |
| `source_provenance` | string | yes | non-empty |
| `timestamp` | datetime | yes | RFC3339/ISO-8601 |
| `content_hash` | string | yes | 64-char hex (SHA-256) |
| `content_type` | string | yes | IANA media type |
| `payload` | object | yes | no null values |
| `metadata` | object | yes | no null values |
| `telemetry.trace_id` | string | yes | non-empty |
| `telemetry.proxy_id` | string | yes | non-empty |
| `telemetry.user_agent` | string | yes | non-empty |
| `telemetry.latency_ms` | integer | yes | >= 0 |
| `telemetry.success_rate` | float | yes | 0.0 - 1.0 |

## Parquet Shard Columns

The Parquet writer stores JSON payloads as ASCII strings for deterministic
schema stability:

| Column | Type |
| --- | --- |
| `primary_key` | string |
| `batch_id` | string |
| `source_provenance` | string |
| `timestamp` | string (ISO-8601) |
| `ingest_ts` | string (ISO-8601) |
| `content_hash` | string |
| `content_type` | string |
| `payload_json` | string |
| `metadata_json` | string |
| `trace_id` | string |
| `proxy_id` | string |
| `user_agent` | string |
| `latency_ms` | int |
| `success_rate` | float |

## Quarantine Record

Quarantined entries are written as JSONL with the following keys:

- `batch_id`
- `trace_id`
- `error`
- `quarantine_ts`
- `record` (raw input)
