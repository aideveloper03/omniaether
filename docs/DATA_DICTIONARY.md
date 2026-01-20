# AETHER-MINE Data Dictionary

## Overview

This document defines the unified data schema used throughout AETHER-MINE, including all record types, fields, and their constraints.

## Core Record Types

### MinedRecord

The primary data model for all mined content.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `record_id` | string (UUID) | Auto | Unique identifier for the record |
| `source_provenance` | SourceProvenance | **Yes** | Origin tracking (Zero-Null Policy) |
| `timestamp` | datetime (UTC) | **Yes** | When record was created |
| `content_hash` | string (SHA-256) | **Yes** | Hash of content for deduplication |
| `content_type` | string | Yes | MIME type (e.g., "application/json") |
| `content` | bytes/string | Yes | Raw content data |
| `content_size_bytes` | integer | Yes | Size of content in bytes |
| `title` | string | No | Optional title |
| `description` | string | No | Optional description |
| `tags` | list[string] | No | Classification tags |
| `metadata` | dict | No | Additional metadata |
| `status` | RecordStatus | Yes | Validation status |
| `batch_id` | string | Auto | Assigned batch identifier |
| `shard_id` | string | Auto | Assigned shard identifier |
| `intelligence_category` | IntelligenceCategory | Auto | LLM-assigned category |
| `extracted_entities` | list[dict] | Auto | Extracted entities |
| `risk_score` | float (0-1) | Auto | Risk assessment score |
| `trace_id` | string | Auto | Telemetry trace ID |

### SourceProvenance

Tracks the origin of all data (required for Zero-Null Policy).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | string | **Yes** | Source URL |
| `domain` | string | **Yes** | Source domain |
| `discovery_method` | string | **Yes** | How data was discovered |
| `retrieval_tier` | FallbackTier | **Yes** | Which fallback tier succeeded |
| `timestamp` | datetime | Auto | When data was retrieved |
| `proxy_id` | string | No | Proxy used for retrieval |
| `user_agent` | string | No | User agent used |

### APISchema

Extracted API schema from shadow API interception.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `endpoint` | string | Yes | API endpoint path |
| `base_url` | string | Yes | Base URL |
| `method` | RequestMethod | Yes | HTTP method |
| `request_headers` | dict | No | Captured request headers |
| `response_headers` | dict | No | Captured response headers |
| `query_params` | dict | No | Query parameters |
| `request_body_schema` | dict | No | Inferred request schema |
| `response_body_schema` | dict | No | Inferred response schema |
| `auth_type` | string | No | Authentication type |
| `auth_header` | string | No | Auth header name |
| `content_type` | string | Yes | Response content type |
| `discovered_at` | datetime | Auto | When API was discovered |

### RequestTrace

Telemetry data for every request.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `trace_id` | string | Auto | Unique trace identifier |
| `request_id` | string | Auto | Unique request identifier |
| `timestamp` | datetime | Auto | Request timestamp |
| `url` | string | Yes | Request URL |
| `method` | RequestMethod | Yes | HTTP method |
| `proxy_ip` | string | No | Proxy IP used |
| `user_agent` | string | Yes | User agent string |
| `latency_ms` | float | Yes | Request latency |
| `status_code` | integer | Yes | HTTP status code |
| `success` | boolean | Yes | Request success flag |
| `error_message` | string | No | Error message if failed |
| `retry_count` | integer | Auto | Number of retries |
| `fallback_tier` | FallbackTier | Yes | Fallback tier used |
| `bytes_transferred` | integer | Auto | Bytes transferred |

### BatchMetadata

Metadata for Parquet batch files.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `batch_id` | string | Auto | Unique batch identifier |
| `shard_id` | string | Auto | Shard identifier |
| `created_at` | datetime | Auto | When batch was created |
| `record_count` | integer | Yes | Number of records |
| `size_bytes` | integer | Yes | File size in bytes |
| `file_path` | string | Yes | Path to Parquet file |
| `content_hashes` | list[string] | Auto | All content hashes in batch |
| `primary_keys` | list[string] | Auto | All record IDs in batch |
| `min_timestamp` | datetime | Auto | Earliest record timestamp |
| `max_timestamp` | datetime | Auto | Latest record timestamp |
| `compression` | string | Yes | Compression algorithm |
| `is_finalized` | boolean | Auto | Whether batch is complete |

### QuarantinedRecord

Records that failed Zero-Null validation.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `record_id` | string | Auto | Unique identifier |
| `original_data` | dict | Yes | Original record data |
| `quarantine_reasons` | list[string] | Yes | Why record was quarantined |
| `quarantine_timestamp` | datetime | Auto | When quarantined |
| `source_url` | string | No | Original source URL |
| `recovery_attempts` | integer | Auto | Recovery attempt count |

### ProxyHealth

Proxy health tracking with circuit breaker.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `proxy_id` | string | Yes | Unique proxy identifier |
| `proxy_url` | string | Yes | Proxy URL |
| `status` | ProxyStatus | Yes | Current status |
| `total_requests` | integer | Auto | Total request count |
| `successful_requests` | integer | Auto | Successful request count |
| `failed_requests` | integer | Auto | Failed request count |
| `consecutive_failures` | integer | Auto | Consecutive failure count |
| `last_used` | datetime | Auto | Last usage timestamp |
| `last_failure` | datetime | Auto | Last failure timestamp |
| `burned_at` | datetime | No | When proxy was burned |
| `cooldown_until` | datetime | No | Cooldown end time |
| `avg_latency_ms` | float | Auto | Average latency |

### DeviceFingerprint

Device fingerprint for browser impersonation.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `fingerprint_id` | string | Auto | Unique fingerprint ID |
| `screen_width` | integer | Yes | Screen width (800-7680) |
| `screen_height` | integer | Yes | Screen height (600-4320) |
| `color_depth` | integer | Yes | Color depth (8-48) |
| `pixel_ratio` | float | Yes | Device pixel ratio |
| `platform` | string | Yes | OS platform |
| `gpu_vendor` | string | Yes | GPU vendor string |
| `gpu_renderer` | string | Yes | GPU renderer string |
| `timezone` | string | Yes | Timezone identifier |
| `language` | string | Yes | Browser language |
| `webgl_hash` | string | No | WebGL fingerprint hash |
| `canvas_hash` | string | No | Canvas fingerprint hash |
| `audio_hash` | string | No | Audio fingerprint hash |
| `fonts` | list[string] | No | Installed fonts |
| `plugins` | list[string] | No | Browser plugins |
| `user_agent` | string | Yes | User agent string |
| `created_at` | datetime | Auto | When created |
| `requests_used` | integer | Auto | Requests made with fingerprint |

## Enumerations

### RecordStatus

| Value | Description |
|-------|-------------|
| `valid` | Record passed all validations |
| `quarantined` | Record failed Zero-Null validation |
| `pending_validation` | Awaiting validation |
| `processed` | Record has been processed by LLM |

### RequestMethod

| Value | Description |
|-------|-------------|
| `GET` | HTTP GET request |
| `POST` | HTTP POST request |
| `PUT` | HTTP PUT request |
| `DELETE` | HTTP DELETE request |
| `PATCH` | HTTP PATCH request |
| `OPTIONS` | HTTP OPTIONS request |
| `HEAD` | HTTP HEAD request |

### FallbackTier

| Value | Priority | Description |
|-------|----------|-------------|
| `shadow_api` | 1 | Direct API fetch with stealth |
| `headless_browser` | 2 | Playwright headless browser |
| `wayback_machine` | 3 | Wayback Machine archive |
| `google_cache` | 4 | Google cached version |
| `human_in_loop` | 5 | Manual intervention required |

### ProxyStatus

| Value | Description |
|-------|-------------|
| `active` | Proxy is available for use |
| `degraded` | Proxy has some failures |
| `burned` | Proxy exceeded failure threshold |
| `cooling_down` | Proxy in cooldown period |

### IntelligenceCategory

| Value | Description |
|-------|-------------|
| `entity_graph` | Contains entity relationships |
| `risk_vector` | Contains risk/anomaly information |
| `asset_inventory` | Contains technology assets |
| `financial_data` | Contains financial information |
| `metadata` | Contains document metadata |
| `unclassified` | Not categorized |

## Parquet Schema

### Main Record Table (`batch_*.parquet`)

```sql
CREATE TABLE records (
    record_id VARCHAR NOT NULL,
    source_url VARCHAR NOT NULL,
    source_domain VARCHAR NOT NULL,
    discovery_method VARCHAR NOT NULL,
    retrieval_tier VARCHAR NOT NULL,
    source_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    content_type VARCHAR NOT NULL,
    content BLOB NOT NULL,
    content_size_bytes BIGINT NOT NULL,
    title VARCHAR,
    description VARCHAR,
    tags VARCHAR[],
    metadata_json VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    batch_id VARCHAR NOT NULL,
    shard_id VARCHAR NOT NULL,
    intelligence_category VARCHAR NOT NULL,
    extracted_entities_json VARCHAR NOT NULL,
    risk_score DOUBLE,
    trace_id VARCHAR,
    proxy_id VARCHAR,
    user_agent VARCHAR
);
```

### Quarantine Table (`quarantine_*.parquet`)

```sql
CREATE TABLE quarantine (
    record_id VARCHAR NOT NULL,
    original_data_json VARCHAR NOT NULL,
    quarantine_reasons VARCHAR[] NOT NULL,
    quarantine_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    source_url VARCHAR,
    recovery_attempts INTEGER NOT NULL
);
```

## DuckDB Index Schema

### record_index

Primary lookup table for fast queries.

```sql
CREATE TABLE record_index (
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
);

-- Indexes for fast lookups
CREATE INDEX idx_record_content_hash ON record_index(content_hash);
CREATE INDEX idx_record_domain ON record_index(source_domain);
CREATE INDEX idx_record_batch ON record_index(batch_id);
CREATE INDEX idx_record_timestamp ON record_index(timestamp);
CREATE INDEX idx_record_category ON record_index(intelligence_category);
```

### content_hash_index

Deduplication tracking.

```sql
CREATE TABLE content_hash_index (
    content_hash VARCHAR PRIMARY KEY,
    record_id VARCHAR NOT NULL,
    first_seen TIMESTAMP WITH TIME ZONE NOT NULL,
    occurrence_count INTEGER DEFAULT 1
);
```

### batch_metadata

Batch file tracking.

```sql
CREATE TABLE batch_metadata (
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
);
```

### domain_stats

Domain-level statistics.

```sql
CREATE TABLE domain_stats (
    domain VARCHAR PRIMARY KEY,
    record_count INTEGER DEFAULT 0,
    total_bytes BIGINT DEFAULT 0,
    first_seen TIMESTAMP WITH TIME ZONE,
    last_seen TIMESTAMP WITH TIME ZONE,
    avg_content_size DOUBLE
);
```

## Zero-Null Policy

### Required Fields

All records MUST have these fields populated:

1. **source_provenance** - Complete provenance tracking
2. **timestamp** - UTC timestamp of record creation
3. **content_hash** - SHA-256 hash of content

### Validation Flow

```
Record Creation
      │
      ▼
┌─────────────────┐
│ Validate Fields │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
  Valid    Invalid
    │         │
    ▼         ▼
 Buffer   Quarantine
    │
    ▼
 Parquet
```

### Quarantine Recovery

Records in quarantine can be recovered if:

1. Missing `timestamp`: Auto-fill with current time
2. Missing `content_hash`: Compute from content
3. Missing `source_provenance`: Requires manual intervention

## Content Hash Computation

```python
def compute_content_hash(content: bytes | str) -> str:
    """
    Compute SHA-256 hash of content.
    
    Returns 64-character lowercase hex string.
    """
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()
```

## Field Constraints

### String Lengths

| Field | Min | Max |
|-------|-----|-----|
| `record_id` | 36 | 36 (UUID) |
| `content_hash` | 64 | 64 (SHA-256) |
| `url` | 1 | - |
| `domain` | 1 | 253 |

### Numeric Ranges

| Field | Min | Max |
|-------|-----|-----|
| `screen_width` | 800 | 7680 |
| `screen_height` | 600 | 4320 |
| `color_depth` | 8 | 48 |
| `pixel_ratio` | 1.0 | 4.0 |
| `risk_score` | 0.0 | 1.0 |
| `status_code` | 100 | 599 |

### Timestamp Format

All timestamps use ISO 8601 format with UTC timezone:
```
2024-01-15T14:30:00.000000+00:00
```

## Metadata JSON Structure

The `metadata_json` field stores arbitrary metadata as JSON:

```json
{
    "quarantine_reasons": ["missing_provenance"],
    "headers": {"content-type": "application/json"},
    "status_code": 200,
    "dork_query": "site:example.com filetype:pdf",
    "search_engine": "duckduckgo",
    "bucket": "acme-backup",
    "key": "data/report.pdf",
    "provider": "aws"
}
```

## Extracted Entities JSON Structure

```json
[
    {
        "type": "email",
        "value": "john@example.com",
        "confidence": 0.95
    },
    {
        "type": "organization",
        "value": "Acme Corp",
        "confidence": 0.85
    }
]
```
