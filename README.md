# AETHER-MINE

**Distributed Intelligence & Adversarial Web Mining Engine**

AETHER-MINE is a production-ready, highly-concurrent engine that extracts "Shadow Data" — unindexed APIs, hidden cloud assets, and non-linear file systems — without relying on surface-level search engine indexing.

## Features

### 🔍 Shadow API Interception
- Protocol-level request interception using Playwright
- Automatic XHR/Fetch traffic capture
- JSON schema extraction and authentication header detection
- High-speed httpx worker cloning for direct API access

### 🔄 Recursive Pattern-Gap Fuzzing
- Intelligent URL pattern analysis (dates, versions, sequences)
- Automatic variant generation for unindexed resources
- Recursive discovery of unlinked files
- Document-specific pattern libraries

### ☁️ Cloud Bucket Discovery
- Brand name permutation generation
- Multi-cloud support (AWS S3, Azure Blob, Google Cloud Storage)
- Public bucket enumeration and content indexing
- Circuit-breaker protected scanning

### 🔎 Dorking Swarm
- Automated advanced search query generation
- Multi-engine support (Google, Bing, DuckDuckGo)
- Risk-categorized dork libraries
- Result verification and download

### 🛡️ Adversarial Evasion System
- **Tier 1**: curl-cffi for Chrome 130+ TLS/JA3 fingerprint impersonation
- **Tier 2**: Behavioral noise (Bézier mouse movements, scrolling, delays)
- **Tier 3**: Cascading fallbacks (Shadow API → Headless → Wayback → Cache → Human)
- Proxy circuit breaker with automatic rotation
- Device fingerprint rotation every 50 requests

### 🧠 Intelligence Transformation
- LLM integration (Ollama/OpenAI) for content analysis
- Entity extraction (regex + semantic)
- Risk vector identification
- Asset inventory extraction

### 💾 Data Architecture
- **Zero-Null Policy**: Strict Pydantic v2 validation
- **Parquet Streaming**: Chunked writes (1,000 records / 50MB batches)
- **DuckDB Index**: Sub-millisecond lookups across all shards
- **Quarantine System**: Automatic routing of invalid records

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/aether-mine.git
cd aether-mine

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

### Configuration

Create a `.env` file:

```bash
# Environment
AETHER_ENVIRONMENT=development
AETHER_LOG_LEVEL=INFO

# Redis (for Celery)
AETHER_REDIS_HOST=localhost
AETHER_REDIS_PORT=6379

# LLM (optional)
AETHER_LLM_PROVIDER=ollama
AETHER_OLLAMA_BASE_URL=http://localhost:11434
AETHER_OLLAMA_MODEL=llama3.2

# Or for OpenAI
# AETHER_LLM_PROVIDER=openai
# AETHER_OPENAI_API_KEY=sk-...
```

### Usage

#### CLI

```bash
# Start API server
python -m src.core.cli serve

# Mine a target URL
python -m src.core.cli mine https://example.com --method shadow_api

# Fuzz URL patterns
python -m src.core.cli fuzz "https://cdn.example.com/reports/annual_2024.pdf"

# Sniff cloud buckets
python -m src.core.cli sniff-buckets "acme-corp" --providers aws azure gcp

# View statistics
python -m src.core.cli stats

# View configuration
python -m src.core.cli config
```

#### API

```bash
# Start the API server
uvicorn src.api.controller:app --host 0.0.0.0 --port 8000

# Create a mining task
curl -X POST http://localhost:8000/api/v1/mining/shadow-api \
  -H "Content-Type: application/json" \
  -d '{"target_url": "https://example.com"}'

# Search indexed records
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query_type": "domain", "query_value": "example.com"}'

# Get system stats
curl http://localhost:8000/api/v1/stats
```

#### Celery Workers

```bash
# Start mining workers
celery -A src.workers.celery_app worker -Q mining -c 4

# Start analysis workers
celery -A src.workers.celery_app worker -Q analysis -c 2

# Start storage workers
celery -A src.workers.celery_app worker -Q storage -c 1

# Start beat scheduler
celery -A src.workers.celery_app beat
```

## Project Structure

```
aether-mine/
├── src/
│   ├── core/           # Core orchestration
│   │   ├── config.py       # Configuration management
│   │   ├── models.py       # Pydantic data models
│   │   ├── telemetry.py    # Telemetry & tracing
│   │   ├── evasion.py      # Stealth & evasion system
│   │   ├── intelligence.py # LLM integration
│   │   └── cli.py          # Command-line interface
│   ├── miners/         # Discovery modules
│   │   ├── shadow_api.py   # Shadow API interception
│   │   ├── pattern_fuzzer.py # URL pattern fuzzing
│   │   ├── cloud_sniffer.py  # Cloud bucket discovery
│   │   └── dorking.py      # Search engine dorking
│   ├── storage/        # Data storage
│   │   ├── parquet_stream.py # Parquet streaming writer
│   │   ├── duckdb_index.py   # DuckDB metadata index
│   │   └── quarantine.py     # Quarantine management
│   ├── api/            # FastAPI controller
│   │   └── controller.py
│   └── workers/        # Celery tasks
│       ├── celery_app.py
│       └── tasks.py
├── docs/               # Documentation
│   ├── SYSTEM_CORE.md
│   ├── DEBUGGING.md
│   ├── MINING_LOGIC.md
│   └── DATA_DICTIONARY.md
├── data/               # Data storage
│   ├── parquet/        # Parquet shards
│   ├── quarantine/     # Quarantined records
│   └── index/          # DuckDB index
├── tests/              # Test suite
├── requirements.txt
├── pyproject.toml
└── README.md
```

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
| `/health` | GET | Health check |
| `/ready` | GET | Readiness check |

## Documentation

- [SYSTEM_CORE.md](docs/SYSTEM_CORE.md) - Architecture and recursive logic
- [DEBUGGING.md](docs/DEBUGGING.md) - Debugging and troubleshooting
- [MINING_LOGIC.md](docs/MINING_LOGIC.md) - Mining strategies and bypass techniques
- [DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md) - Unified data schema

## Requirements

- Python 3.11+
- Redis (for Celery)
- Playwright (chromium)
- Optional: Ollama or OpenAI API key (for LLM features)

## License

MIT License
