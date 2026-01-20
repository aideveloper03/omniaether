# AETHER-MINE System Core Documentation

## Overview

AETHER-MINE is a production-ready, highly-concurrent engine designed for distributed intelligence gathering and adversarial web mining. It extracts "Shadow Data" - unindexed APIs, hidden cloud assets, and non-linear file systems - without relying on surface-level search engine indexing.

## Architecture

### High-Level Components

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           AETHER-MINE Architecture                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────────┐  │
│  │   FastAPI    │───▶│    Celery    │───▶│    Mining Modules        │  │
│  │  Controller  │    │   Workers    │    │  ├─ Shadow API           │  │
│  └──────────────┘    └──────────────┘    │  ├─ Pattern Fuzzer       │  │
│         │                   │            │  ├─ Cloud Sniffer        │  │
│         │                   │            │  └─ Dorking Swarm        │  │
│         ▼                   ▼            └──────────────────────────┘  │
│  ┌──────────────────────────────────┐              │                    │
│  │         Redis/RabbitMQ           │              │                    │
│  │         Message Broker           │              ▼                    │
│  └──────────────────────────────────┘    ┌──────────────────────────┐  │
│                                          │    Evasion Layer         │  │
│                                          │  ├─ curl-cffi (TLS)      │  │
│                                          │  ├─ Behavioral Noise     │  │
│                                          │  ├─ Proxy Manager        │  │
│                                          │  └─ Cascading Fallback   │  │
│                                          └──────────────────────────┘  │
│                                                      │                  │
│                                                      ▼                  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    Storage Layer                                  │  │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────────┐  │  │
│  │  │ Parquet Stream │  │  DuckDB Index  │  │    Quarantine      │  │  │
│  │  │    Writer      │  │                │  │     Manager        │  │  │
│  │  └────────────────┘  └────────────────┘  └────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Core Modules

### 1. Shadow API Interception Engine (`src/miners/shadow_api.py`)

The Shadow API Interceptor uses Playwright's request hooks to capture all network traffic during navigation.

**Key Features:**
- Automatic XHR/Fetch interception
- JSON schema extraction from responses
- Authentication header detection (Bearer, API-Key, Custom)
- High-speed httpx worker cloning for direct API access

**Flow:**
```
Navigate to URL → Intercept Requests → Capture Responses → Extract Schemas
                                                              │
                                                              ▼
                                    Clone to httpx workers for high-speed access
```

### 2. Recursive Pattern-Gap Fuzzing (`src/miners/pattern_fuzzer.py`)

The Pattern Fuzzer analyzes URL structures to discover unindexed resources.

**Pattern Detection:**
- Year patterns (2024, 2023, etc.)
- Date patterns (YYYYMMDD, YYYY-MM-DD)
- Version patterns (v1.0, v2.1.3)
- Numeric sequences
- Financial quarters (Q1, Q2, etc.)

**Recursive Logic:**
```python
# Example: If we find cdn.company.com/assets/v1/report_2024.pdf
# The fuzzer generates:
#   - report_2023.pdf
#   - report_2025.pdf
#   - internal_audit_2024.pdf
#   - quarterly_2024.pdf
#   - etc.
```

### 3. Cloud Bucket Sniffer (`src/miners/cloud_sniffer.py`)

Discovers public cloud storage buckets across AWS S3, Azure Blobs, and GCS.

**Brand Permutation Examples:**
```
For brand "AcmeCorp":
  - acmecorp
  - acmecorp-dev
  - acmecorp-prod
  - acmecorp-backup
  - dev-acmecorp
  - acmecorp-data
  - acmecorp-assets
  - etc.
```

### 4. Dorking Swarm (`src/miners/dorking.py`)

Automated advanced search queries across multiple engines.

**Dork Categories:**
- File exposure (env, sql, log, config)
- Directory listings
- Cloud storage
- Error/debug information
- Admin panels
- API exposure

## Storage Architecture

### Parquet Stream Writer

**Zero-Null Policy Enforcement:**
All records MUST have:
- `source_provenance` - Where the data came from
- `timestamp` - When it was collected
- `content_hash` - SHA-256 hash for deduplication

Records missing required fields are automatically routed to the quarantine shard.

**Batching Logic:**
```
Record arrives → Validate → Buffer
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
      1000 records     50MB reached      60s timeout
            │                 │                 │
            └─────────────────┴─────────────────┘
                              │
                              ▼
                    Flush to Parquet file
```

### DuckDB Metadata Index

Provides sub-millisecond lookups across all Parquet shards.

**Indexed Fields:**
- `record_id` (Primary Key)
- `content_hash` (for deduplication)
- `source_domain`
- `timestamp`
- `intelligence_category`
- `risk_score`

## Evasion System

### Tier 1: Stealth (curl-cffi)

Uses curl-cffi to impersonate Chrome 130+ TLS/JA3 fingerprints.

**Browser Profiles:**
- chrome120, chrome119, chrome116, chrome110
- safari17_2_ios, safari17_0, safari15_5

### Tier 2: Behavioral Noise

Pollutes bot-detection telemetry with human-like actions:
- Bézier curve mouse movements
- Random scrolling patterns
- Element hovering
- Variable delays

### Tier 3: Cascading Fallbacks

```
1. Direct Shadow API Fetch
         │ fail
         ▼
2. Stealth Headless Browser
         │ fail
         ▼
3. Wayback Machine Archive
         │ fail
         ▼
4. Google Cache
         │ fail
         ▼
5. Human-in-the-Loop Notification
```

### Proxy Circuit Breaker

```python
# After 3 consecutive failures:
proxy.status = BURNED
proxy.cooldown_until = now + 24 hours
```

### Fingerprint Rotation

Device fingerprints rotate every 50 requests:
- Screen resolution
- GPU vendor/renderer
- Timezone
- Language
- User agent
- Canvas/WebGL hashes

## Telemetry System

Every request carries a `trace_id` linking:
- Proxy IP used
- User-Agent string
- Request latency
- Status code
- Fallback tier
- Bytes transferred

**Metrics Tracked:**
- Total requests
- Success rate
- Average latency
- Requests by tier
- Errors by type

## Intelligence Transformation

### LLM Integration

Supports both local (Ollama) and cloud (OpenAI) providers.

**Analysis Categories:**
- **Entity_Graph**: Relationships between organizations/people
- **Risk_Vectors**: Financial anomalies, legal red flags
- **Asset_Inventory**: Technologies, servers, infrastructure
- **Financial_Data**: Reports, statements
- **Metadata**: Document metadata

### Entity Extraction

Combined regex + LLM approach:
1. Fast regex extraction for common patterns (email, phone, URL, IP)
2. LLM extraction for semantic entities (organizations, people, legal terms)

## API Endpoints

### Mining Operations

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/mining/task` | POST | Create mining task |
| `/api/v1/mining/shadow-api` | POST | Mine shadow APIs |
| `/api/v1/mining/pattern-fuzz` | POST | Fuzz URL patterns |
| `/api/v1/mining/cloud-sniff` | POST | Sniff cloud buckets |
| `/api/v1/mining/dorking` | POST | Run dorking swarm |

### Data Retrieval

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/search` | POST | Search indexed records |
| `/api/v1/record/{id}` | GET | Get specific record |
| `/api/v1/domains` | GET | List indexed domains |

### System Monitoring

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/stats` | GET | System statistics |
| `/api/v1/telemetry` | GET | Telemetry stats |
| `/api/v1/quarantine` | GET | Quarantine stats |

## Configuration

Key environment variables:

```bash
# Application
AETHER_ENVIRONMENT=production
AETHER_LOG_LEVEL=INFO

# Batch Settings
AETHER_BATCH_MAX_RECORDS=1000
AETHER_BATCH_MAX_SIZE_MB=50

# Redis
AETHER_REDIS_HOST=localhost
AETHER_REDIS_PORT=6379

# Proxy Settings
AETHER_PROXY_MAX_FAILURES=3
AETHER_PROXY_BURN_TIMEOUT_HOURS=24

# LLM
AETHER_LLM_PROVIDER=ollama
AETHER_OLLAMA_BASE_URL=http://localhost:11434
AETHER_OLLAMA_MODEL=llama3.2
```

## Running the System

### Start API Server

```bash
uvicorn src.api.controller:app --host 0.0.0.0 --port 8000
```

### Start Celery Workers

```bash
# Mining workers
celery -A src.workers.celery_app worker -Q mining -c 4

# Analysis workers
celery -A src.workers.celery_app worker -Q analysis -c 2

# Storage workers
celery -A src.workers.celery_app worker -Q storage -c 1

# Beat scheduler
celery -A src.workers.celery_app beat
```

### Docker Compose (Recommended)

```yaml
version: '3.8'
services:
  api:
    build: .
    ports:
      - "8000:8000"
    command: uvicorn src.api.controller:app --host 0.0.0.0

  worker-mining:
    build: .
    command: celery -A src.workers.celery_app worker -Q mining

  worker-analysis:
    build: .
    command: celery -A src.workers.celery_app worker -Q analysis

  redis:
    image: redis:7

  beat:
    build: .
    command: celery -A src.workers.celery_app beat
```
