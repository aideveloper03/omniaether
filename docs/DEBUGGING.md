# AETHER-MINE Debugging Guide

## Overview

This guide covers debugging strategies for AETHER-MINE, including tracing batch failures, investigating quarantined records, and diagnosing evasion system issues.

## Tracing System

### Understanding Trace IDs

Every operation in AETHER-MINE generates a `trace_id` with the format:
```
aether-{uuid_hex_16}-{timestamp_ms}
Example: aether-a1b2c3d4e5f6g7h8-123456
```

### Tracing a Request

1. **Get trace from API response:**
```json
{
  "status": "started",
  "trace_id": "aether-a1b2c3d4e5f6g7h8-123456"
}
```

2. **Query traces via API:**
```bash
curl http://localhost:8000/api/v1/telemetry/traces/aether-a1b2c3d4e5f6g7h8-123456
```

3. **Response includes:**
```json
{
  "traces": [
    {
      "trace_id": "aether-a1b2c3d4e5f6g7h8-123456",
      "request_id": "uuid",
      "url": "https://target.com/api",
      "method": "GET",
      "proxy_ip": "1.2.3.4",
      "user_agent": "Mozilla/5.0...",
      "latency_ms": 234.5,
      "status_code": 200,
      "success": true,
      "fallback_tier": "shadow_api",
      "bytes_transferred": 12345
    }
  ]
}
```

## Batch Failure Debugging

### Identifying Failed Batches

1. **Check system stats:**
```bash
curl http://localhost:8000/api/v1/stats
```

2. **Look for discrepancies:**
```json
{
  "total_records": 10000,
  "finalized_batches": 9,
  "quarantine_count": 150  // ⚠️ High quarantine count
}
```

### Investigating Quarantine

1. **Get quarantine statistics:**
```bash
curl http://localhost:8000/api/v1/quarantine
```

Response:
```json
{
  "total_quarantined": 150,
  "pending_count": 5,
  "file_count": 3,
  "reasons_breakdown": {
    "missing_source_provenance": 45,
    "missing_content_hash": 30,
    "missing_timestamp": 0,
    "validation_error": 75
  }
}
```

2. **List quarantined records:**
```bash
curl "http://localhost:8000/api/v1/quarantine/records?limit=10"
```

3. **Attempt recovery:**
```bash
curl -X POST http://localhost:8000/api/v1/quarantine/recover/{record_id}
```

### Common Quarantine Issues

#### Missing Source Provenance

**Cause:** Record created without proper source tracking.

**Fix:**
```python
# Ensure provenance is always set
provenance = SourceProvenance(
    url=response.url,
    domain=urlparse(response.url).netloc,
    discovery_method="shadow_api_interception",
    retrieval_tier=FallbackTier.SHADOW_API,
)

record = MinedRecord(
    source_provenance=provenance,  # Required!
    ...
)
```

#### Missing Content Hash

**Cause:** Content hash not computed before record creation.

**Fix:**
```python
content_hash = MinedRecord.compute_content_hash(content)

record = MinedRecord(
    content_hash=content_hash,  # Required!
    ...
)
```

## Evasion System Debugging

### Proxy Issues

#### High Failure Rate

1. **Check proxy stats:**
```python
from src.core.evasion import ProxyManager

manager = ProxyManager(proxies)
stats = manager.get_stats()
print(stats)
# {
#   "total_proxies": 10,
#   "active_proxies": 3,  # ⚠️ Low active count
#   "burned_proxies": 7,
#   "avg_success_rate": 0.45
# }
```

2. **Investigate burned proxies:**
```python
for proxy_id, health in manager._proxies.items():
    if health.status == ProxyStatus.BURNED:
        print(f"{proxy_id}: Failed {health.consecutive_failures} times")
        print(f"  Last failure: {health.last_failure}")
        print(f"  Cooldown until: {health.cooldown_until}")
```

3. **Solutions:**
- Add more proxies to the pool
- Check if proxies are blocked by target
- Reduce request rate
- Rotate fingerprints more frequently

#### Fingerprint Detection

**Symptoms:**
- Consistent 403/429 responses
- CAPTCHAs appearing
- Requests blocked after initial success

**Debugging:**
```python
from src.core.evasion import FingerprintGenerator

gen = FingerprintGenerator(rotation_threshold=25)  # Lower threshold
fingerprint = gen.generate()

print(f"Screen: {fingerprint.screen_width}x{fingerprint.screen_height}")
print(f"GPU: {fingerprint.gpu_vendor}")
print(f"UA: {fingerprint.user_agent}")
```

**Solutions:**
- Lower `fingerprint_rotation_requests` setting
- Diversify GPU profiles
- Use residential proxies
- Add more behavioral noise

### Cascading Fallback Debugging

**Check fallback progression in logs:**
```
[INFO] fallback_tier_1 trace_id=xxx url=https://target.com tier=shadow_api
[DEBUG] tier_1_failed error=ConnectionError
[INFO] fallback_tier_2 trace_id=xxx url=https://target.com tier=headless
[DEBUG] tier_2_failed error=TimeoutError
[INFO] fallback_tier_3 trace_id=xxx url=https://target.com tier=wayback
```

**If all tiers fail:**
1. Check if URL is accessible manually
2. Verify Wayback Machine has archived the URL
3. Check Google Cache availability
4. Consider the URL might be genuinely inaccessible

## Mining Module Debugging

### Shadow API Interception

**No APIs discovered:**

1. **Check if site uses APIs:**
```python
interceptor = ShadowAPIInterceptor()
await interceptor.start()
await interceptor.navigate_and_intercept(url, wait_for="networkidle", additional_wait_ms=5000)

print(f"Requests captured: {len(interceptor._intercepted_requests)}")
print(f"Responses captured: {len(interceptor._intercepted_responses)}")
```

2. **Common issues:**
- Site uses server-side rendering (no APIs)
- APIs are loaded before interception starts
- Content is embedded in HTML (not fetched via XHR)

**Solutions:**
- Increase `additional_wait_ms`
- Scroll page to trigger lazy loading
- Check for WebSocket connections (not captured by default)

### Pattern Fuzzer

**No patterns detected:**
```python
from src.miners.pattern_fuzzer import URLPatternAnalyzer

analyzer = URLPatternAnalyzer()
patterns = analyzer.analyze("https://example.com/static/file.pdf")
print(patterns)
# [] - No fuzzable patterns found
```

**High false positive rate:**
```python
fuzzer = PatternFuzzer()
results = await fuzzer.fuzz_url(url, max_variants=10)

hits = [r for r in results if r.discovered]
misses = [r for r in results if not r.discovered]

print(f"Hit rate: {len(hits)}/{len(results)}")
# If very low, patterns might be too aggressive
```

### Cloud Bucket Sniffer

**No buckets found:**

1. **Check permutations generated:**
```python
from src.miners.cloud_sniffer import BrandPermutationGenerator

gen = BrandPermutationGenerator("acme")
perms = gen.generate_permutations()
print(f"Generated {len(perms)} permutations")
print(perms[:20])
```

2. **Verify bucket URL format:**
```python
# AWS S3
https://acme.s3.amazonaws.com
https://acme.s3.us-east-1.amazonaws.com

# Azure
https://acme.blob.core.windows.net

# GCS
https://storage.googleapis.com/acme
```

## Storage Debugging

### DuckDB Index Issues

**Query performance:**
```python
import time
from src.storage.duckdb_index import get_index

index = get_index()

start = time.perf_counter()
result = index.lookup_by_hash(content_hash)
latency = (time.perf_counter() - start) * 1000

print(f"Lookup latency: {latency:.2f}ms")
# Should be < 10ms for indexed queries
```

**Index corruption:**
```python
# Check table counts
stats = index.get_global_stats()
print(stats)

# Verify indexes exist
results = index.execute_raw("PRAGMA table_info(record_index)")
print(results)
```

### Parquet File Issues

**Verify file integrity:**
```python
import pyarrow.parquet as pq

# List parquet files
from pathlib import Path
parquet_dir = Path("data/parquet")

for f in parquet_dir.glob("*.parquet"):
    try:
        table = pq.read_table(f)
        print(f"{f.name}: {len(table)} rows")
    except Exception as e:
        print(f"{f.name}: CORRUPTED - {e}")
```

## Log Analysis

### Enable Debug Logging

```python
import structlog

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
)
```

Or via environment:
```bash
export AETHER_LOG_LEVEL=DEBUG
```

### Key Log Patterns

**Successful mining:**
```
[INFO] navigation_started trace_id=xxx url=https://target.com
[DEBUG] request_intercepted url=https://target.com/api type=xhr
[INFO] api_schema_extracted endpoint=/api method=GET auth_type=Bearer
[INFO] navigation_complete trace_id=xxx apis_discovered=5
[INFO] parquet_batch_written batch_id=xxx record_count=100
```

**Failed request:**
```
[INFO] fallback_tier_1 trace_id=xxx url=https://target.com tier=shadow_api
[ERROR] stealth_request_failed trace_id=xxx url=https://target.com error=ConnectionError
[WARNING] proxy_burned proxy_id=proxy_0 failures=3
```

**Quarantine:**
```
[WARNING] record_quarantined record_id=xxx reasons=['missing_source_provenance']
[WARNING] quarantine_batch_written batch_id=xxx record_count=5
```

## Health Checks

### API Health
```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

### Worker Health (Celery)
```bash
celery -A src.workers.celery_app inspect ping
celery -A src.workers.celery_app inspect active
celery -A src.workers.celery_app inspect stats
```

### Redis Health
```bash
redis-cli ping
redis-cli info memory
```

## Performance Profiling

### Request Latency Analysis

```python
from src.core.telemetry import get_telemetry

telemetry = get_telemetry()
stats = telemetry.get_stats()

print(f"Avg latency: {stats['avg_latency_ms']:.2f}ms")
print(f"Success rate: {stats['success_rate']:.2%}")
print(f"Requests by tier: {stats['requests_by_tier']}")
```

### Memory Usage

```python
import tracemalloc

tracemalloc.start()

# ... run operations ...

current, peak = tracemalloc.get_traced_memory()
print(f"Current: {current / 1024 / 1024:.2f} MB")
print(f"Peak: {peak / 1024 / 1024:.2f} MB")
```

## Common Error Codes

| Error | Likely Cause | Solution |
|-------|--------------|----------|
| `missing_source_provenance` | Record created without URL info | Always set `source_provenance` |
| `missing_content_hash` | Hash not computed | Call `compute_content_hash()` |
| `proxy_burned` | Proxy failed 3+ times | Add more proxies, reduce rate |
| `tier_5_reached` | All fallbacks failed | Manual investigation needed |
| `batch_flush_failed` | Disk/permission issue | Check disk space, permissions |
