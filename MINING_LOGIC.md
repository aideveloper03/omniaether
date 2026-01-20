# Mining Logic & Evasion

## Shadow API Interception
Instead of scraping HTML, we target the data source directly.
1. **Hook**: `page.on('response')`.
2. **Filter**: Content-Type `application/json`, `xhr`, `fetch`.
3. **Extraction**:
    - Captures pure JSON payload.
    - Identifies `Authorization` headers (Bearer, API Keys).
    - Infers schema structure.

## Recursive Pattern Fuzzing
Algorithms used to discover unlinked content:
1. **Numeric Iteration**: Detects integers in URL path/query. Scans +/- N range.
2. **Date Permutation**: Detects years (2020-2030) and attempts traversal.
3. **Version Increment**: Detects `v1`, `v2` and probes higher versions.

## Cloud Bucket Discovery
Brand-based generation for S3/Azure/GCP:
- `{brand}`
- `{brand}-assets`
- `{brand}-internal`
- `dev-{brand}`

## Evasion Techniques (Tier 2/3)
- **TLS Fingerprinting**: `curl_cffi` mimics Chrome/Safari TLS Client Hello to bypass JA3 blocking.
- **Navigator Overrides**: Playwright scripts mask `navigator.webdriver`.
- **Random Delays**: "Human-think" pauses before critical actions.
