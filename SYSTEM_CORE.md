# System Core Architecture

## Overview
AETHER-MINE is a distributed intelligence engine designed for adversarial web mining. It operates by bypassing traditional indexing mechanisms and directly interacting with "Shadow APIs" and unindexed resources.

## Architecture Components

### 1. Orchestration (Core)
- **FastAPI**: Serves as the Control Plane for triggering tasks.
- **Celery**: Distributed task queue handling high-concurrency mining operations.
- **Redis**: Message broker and state management.

### 2. Mining Engine
- **Shadow API Interceptor**: Uses `Playwright` to execute headless browser sessions, intercepting `XHR` and `Fetch` requests to reverse-engineer private APIs.
- **Recursive Fuzzer**: Analyzes URL patterns (e.g., `id=100`, `year=2024`) and autonomously probes for adjacent resources (`id=101`, `year=2023`).
- **Cloud Sniffer**: Generates permutations of brand names to discover open AWS S3, Azure Blob, and GCP buckets.

### 3. Storage & Indexing
- **Parquet-Stream**: Data is written in strictly validated `Pydantic` schemas to Parquet files. "No Null" policy is enforced.
- **DuckDB**: Maintains a global, queryable index of all ingested content hashes and primary keys, enabling rapid lookups without loading full datasets.
- **Quarantine**: Invalid records are diverted to JSON quarantine files for manual inspection.

## Data Flow
1. **Ingest**: User triggers URL or Brand scan via API.
2. **Dispatch**: Task is sent to Celery worker.
3. **Execution**:
    - **Shadow**: Browser loads -> Intercepts Traffic -> Extracts JSON -> Validates -> Buffer.
    - **Fuzz/Sniff**: Generates URLs -> HTTPX Probe -> Validates -> Buffer.
4. **Storage**: Buffer flushes to Parquet (chunks). Metadata registered in DuckDB.
