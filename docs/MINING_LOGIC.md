# AETHER-MINE Mining Logic Documentation

## Overview

This document explains the recursive discovery logic and bypass strategies used by AETHER-MINE to discover non-indexed data.

## Shadow API Interception Logic

### How It Works

The Shadow API Interceptor operates at the protocol level, capturing all network traffic during page navigation.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Shadow API Interception Flow                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   Browser Navigation                                                 │
│         │                                                            │
│         ▼                                                            │
│   ┌─────────────────┐                                               │
│   │ Page.route(**/*) │  ◄─── Intercept ALL requests                 │
│   └────────┬────────┘                                               │
│            │                                                         │
│            ▼                                                         │
│   ┌─────────────────────────────────────────────┐                   │
│   │ Filter by resource_type: ["xhr", "fetch"]   │                   │
│   └────────┬────────────────────────────────────┘                   │
│            │                                                         │
│            ▼                                                         │
│   ┌─────────────────────────────────────────────┐                   │
│   │ Capture Request Details:                     │                   │
│   │  - URL, Method, Headers                      │                   │
│   │  - POST data (if any)                        │                   │
│   │  - Authentication tokens                     │                   │
│   └────────┬────────────────────────────────────┘                   │
│            │                                                         │
│            ▼                                                         │
│   route.continue() ───► Request proceeds to server                  │
│            │                                                         │
│            ▼                                                         │
│   ┌─────────────────────────────────────────────┐                   │
│   │ Capture Response:                            │                   │
│   │  - Status code                               │                   │
│   │  - Response headers                          │                   │
│   │  - JSON body (if applicable)                 │                   │
│   └────────┬────────────────────────────────────┘                   │
│            │                                                         │
│            ▼                                                         │
│   ┌─────────────────────────────────────────────┐                   │
│   │ Schema Extraction:                           │                   │
│   │  - Infer request/response JSON schemas      │                   │
│   │  - Detect auth type (Bearer, API-Key, etc.) │                   │
│   │  - Extract query parameters                  │                   │
│   └────────┬────────────────────────────────────┘                   │
│            │                                                         │
│            ▼                                                         │
│   Clone to httpx worker for direct API access                       │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Schema Inference Algorithm

```python
def infer_json_schema(data, max_depth=5):
    """
    Recursively infer JSON schema from data.
    
    Examples:
    
    Input: {"name": "John", "age": 30}
    Output: {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"}
        }
    }
    
    Input: [{"id": 1}, {"id": 2}]
    Output: {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {"id": {"type": "integer"}}
        }
    }
    """
```

### Authentication Detection

The system automatically detects authentication patterns:

| Pattern | Detection Method | Auth Type |
|---------|------------------|-----------|
| `Authorization: Bearer xxx` | Header prefix | Bearer Token |
| `Authorization: Basic xxx` | Header prefix | Basic Auth |
| `X-API-Key: xxx` | Header name | API Key |
| `X-Auth-Token: xxx` | Header name | Custom Token |
| `Cookie: session=xxx` | Cookie presence | Session Cookie |

## Recursive Pattern-Gap Fuzzing

### Pattern Detection Engine

The fuzzer analyzes URLs to detect fuzzable patterns:

```
URL: https://cdn.company.com/reports/annual_report_2024.pdf

Detected Patterns:
├── Year: "2024" at position 45
│   └── Variants: 2020, 2021, 2022, 2023, 2025, 2026
├── Type: "annual" prefix detected
│   └── Variants: quarterly, monthly, internal
└── Extension: ".pdf"
    └── Variants: .xlsx, .doc, .docx
```

### Fuzzing Algorithm

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Pattern Fuzzing Algorithm                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   Input URL: https://example.com/data/report_2024_Q1.pdf            │
│                                                                      │
│   Step 1: Pattern Analysis                                          │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │ Regex Matching:                                              │   │
│   │  - Year: (20\d{2}) → "2024"                                 │   │
│   │  - Quarter: ([Qq][1-4]) → "Q1"                              │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│   Step 2: Template Generation                                       │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │ Template: https://example.com/data/report_{year}_{quarter}.pdf │ │
│   └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│   Step 3: Variant Generation                                        │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │ Years: [2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]     │   │
│   │ Quarters: [Q1, Q2, Q3, Q4]                                   │   │
│   │ Combinations: 8 × 4 = 32 URLs                                │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│   Step 4: Parallel Verification                                     │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │ HEAD requests to all variants                                │   │
│   │ Success criteria: status in [200, 301, 302]                  │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│   Step 5: Recursive Discovery (if enabled)                          │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │ For each discovered URL:                                     │   │
│   │   - Re-analyze for new patterns                              │   │
│   │   - Generate new variants                                    │   │
│   │   - Verify (depth - 1)                                       │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Document Pattern Library

Pre-built patterns for common document types:

```python
DOCUMENT_PATTERNS = [
    # Annual reports
    ("annual_report_{year}.pdf", range(2015, 2027)),
    ("{year}_annual_report.pdf", range(2015, 2027)),
    
    # Quarterly reports
    ("{year}Q{quarter}_report.pdf", ...),
    ("Q{quarter}_{year}_report.pdf", ...),
    
    # SEC filings
    ("10K_{year}.pdf", range(2015, 2027)),
    ("10Q_Q{quarter}_{year}.pdf", ...),
    
    # Internal documents
    ("internal_audit_{year}.pdf", ...),
    ("budget_{year}.xlsx", ...),
]
```

## Cloud Bucket Discovery Logic

### Brand Permutation Algorithm

```
┌─────────────────────────────────────────────────────────────────────┐
│                   Brand Permutation Generation                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   Input: "Acme Corporation"                                         │
│                                                                      │
│   Step 1: Normalization                                             │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │ "Acme Corporation" → "acme-corporation"                      │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│   Step 2: Variation Generation                                      │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │ Variations:                                                  │   │
│   │  - acme-corporation                                          │   │
│   │  - acmecorporation (no hyphen)                              │   │
│   │  - acme (first word)                                        │   │
│   │  - ac (initials)                                            │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│   Step 3: Suffix/Prefix Addition                                    │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │ For each variation, add:                                     │   │
│   │  Suffixes: -dev, -prod, -backup, -data, -assets, -public    │   │
│   │  Prefixes: dev-, prod-, staging-, backup-                    │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│   Step 4: Cloud-Specific Patterns                                   │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │ Additional patterns:                                         │   │
│   │  - {brand}-s3                                                │   │
│   │  - {brand}-bucket                                            │   │
│   │  - s3-{brand}                                                │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│   Output: ~200-500 bucket name candidates                           │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Multi-Cloud Verification

```
For each bucket candidate:

AWS S3:
├── https://{bucket}.s3.amazonaws.com
├── https://{bucket}.s3.{region}.amazonaws.com (10 regions)
└── https://s3.amazonaws.com/{bucket}

Azure Blob:
└── https://{bucket}.blob.core.windows.net

Google Cloud Storage:
├── https://storage.googleapis.com/{bucket}
└── https://{bucket}.storage.googleapis.com

Verification:
1. HEAD request to check existence
2. If 200: Check if public (try to list)
3. If 403: Exists but private
4. If 404: Does not exist
```

## Dorking Swarm Logic

### Query Construction

```python
# Template-based dork construction
dork_template = 'site:{target} filetype:env'
target = "example.com"
query = dork_template.format(target=target)
# Result: "site:example.com filetype:env"
```

### Multi-Engine Strategy

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Dorking Swarm Execution                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   Dork Categories (by risk level):                                  │
│                                                                      │
│   CRITICAL:                                                          │
│   ├── site:{target} filetype:env                                    │
│   ├── site:{target} filetype:sql                                    │
│   └── intitle:"phpMyAdmin"                                          │
│                                                                      │
│   HIGH:                                                              │
│   ├── site:{target} filetype:log                                    │
│   ├── site:{target} intitle:"index of /"                            │
│   └── site:{target} "debug" OR "DEBUG=True"                         │
│                                                                      │
│   MEDIUM:                                                            │
│   ├── site:{target} filetype:xlsx OR filetype:csv                   │
│   ├── site:s3.amazonaws.com "{target}"                              │
│   └── site:{target} inurl:swagger                                   │
│                                                                      │
│   Execution:                                                         │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │ For each dork:                                               │   │
│   │   For each engine (Google, Bing, DuckDuckGo):               │   │
│   │     1. Execute search query                                  │   │
│   │     2. Parse results (URLs, titles, snippets)               │   │
│   │     3. Deduplicate URLs                                      │   │
│   │     4. Rate limit (2s delay between requests)               │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Result Verification

```python
# Verify discovered URLs
async def verify_and_download(results):
    for result in results:
        # 1. HEAD request to check availability
        head_response = await client.head(result.url)
        
        # 2. Check size constraints
        if content_length > max_size:
            continue
            
        # 3. Download content
        response = await client.get(result.url)
        
        # 4. Create MinedRecord with provenance
        record = MinedRecord(
            source_provenance=SourceProvenance(
                url=result.url,
                domain=urlparse(result.url).netloc,
                discovery_method=f"dorking_{result.search_engine}",
                retrieval_tier=FallbackTier.SHADOW_API,
            ),
            content_hash=compute_hash(response.content),
            content=response.content,
            ...
        )
```

## Evasion-Aware Mining

### Request Flow with Evasion

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Evasion-Aware Request Flow                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   1. Pre-Request Setup                                              │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │ a. Check fingerprint rotation (every 50 requests)           │   │
│   │ b. Select active proxy from pool                             │   │
│   │ c. Prepare stealth headers (TLS impersonation)              │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│   2. Request Execution                                              │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │ a. Use curl-cffi with Chrome 130+ fingerprint               │   │
│   │ b. Add behavioral noise (delays, mouse movements)           │   │
│   │ c. Execute request through selected proxy                    │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│   3. Response Handling                                              │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │ If success (200):                                            │   │
│   │   - Record proxy success                                     │   │
│   │   - Process response                                         │   │
│   │                                                              │   │
│   │ If blocked (403/429):                                        │   │
│   │   - Record proxy failure                                     │   │
│   │   - Trigger fallback cascade                                 │   │
│   │   - Try next tier                                            │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│   4. Fallback Cascade                                               │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │ Tier 1: Direct API (curl-cffi) → FAIL                       │   │
│   │         ↓                                                    │   │
│   │ Tier 2: Headless Browser → FAIL                             │   │
│   │         ↓                                                    │   │
│   │ Tier 3: Wayback Machine → FAIL                              │   │
│   │         ↓                                                    │   │
│   │ Tier 4: Google Cache → FAIL                                 │   │
│   │         ↓                                                    │   │
│   │ Tier 5: Human-in-the-loop notification                      │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Bypassing Non-Indexation

### Why Content Isn't Indexed

1. **Robots.txt Exclusion**: Search engines honor robots.txt
2. **No Inbound Links**: Pages with no links aren't crawled
3. **JavaScript-Only Content**: Dynamic content not indexed
4. **Authentication Required**: Login-protected content
5. **Noindex Meta Tags**: Explicit exclusion
6. **Recent Content**: Not yet crawled

### AETHER-MINE Bypass Strategies

| Blocker | Traditional Crawler | AETHER-MINE Strategy |
|---------|---------------------|----------------------|
| robots.txt | Honors exclusion | Ignores (direct access) |
| No links | Can't discover | Pattern fuzzing discovers |
| JS content | Misses dynamic data | Shadow API captures |
| Auth required | Blocked | Extracts auth from intercept |
| Noindex | Skips | Direct access bypasses |
| New content | Waits for index | Real-time discovery |

### Discovery Priority

```
1. Shadow API Interception (highest priority)
   - Captures live API calls
   - Extracts authentication
   - Gets real-time data
   
2. Pattern Fuzzing (second priority)
   - Discovers unlinked resources
   - Finds historical versions
   - Locates related files
   
3. Cloud Bucket Sniffing (parallel)
   - Finds misconfigured storage
   - Discovers backup data
   - Locates development assets
   
4. Dorking (supplementary)
   - Leverages existing indices
   - Finds indexed but hidden content
   - Discovers related domains
```
