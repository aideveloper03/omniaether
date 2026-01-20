# omniaether

Compliance-first ingestion and storage backbone for structured records.

## Highlights

- Pydantic v2 zero-null validation with quarantine routing
- Chunked Parquet streaming (1,000 records or 50MB per shard)
- DuckDB metadata index for primary key and content hash lookup
- FastAPI + Celery ingestion controller
- Telemetry logging with traceability fields

## Quickstart

```bash
python -m pip install -r requirements.txt
```

Run the API:

```bash
PYTHONPATH=src uvicorn core.app:app --host 0.0.0.0 --port 8000
```

Ingest a manifest:

```bash
PYTHONPATH=src python -m core.cli ingest-manifest --path /path/to/records.jsonl
```

Ingest local files:

```bash
PYTHONPATH=src python -m core.cli ingest-local --path /path/to/dataset
```

## Documentation

- SYSTEM_CORE.md
- DEBUGGING.md
- MINING_LOGIC.md
- DATA_DICTIONARY.md