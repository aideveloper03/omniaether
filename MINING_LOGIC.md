# MINING_LOGIC

This repository focuses on **authorized** data collection and processing. It
does not include stealth, evasion, dorking, or unsolicited network discovery.
All ingestion is designed for explicit allowlisted inputs.

## Supported Ingestion Paths

1. **Manifest ingestion**
   - Accepts JSON or JSONL files containing fully formed records.
   - Use when you already have a vetted dataset or system-of-record export.

2. **Local file mining**
   - Traverses a local directory and converts files into validated records.
   - Useful for controlled environments (shared drives, offline datasets).

3. **API ingestion (FastAPI)**
   - Allows upstream systems to push records directly.
   - Ideal for a service mesh where source services have authorization.

## Pattern Gap Analysis (Safe Mode)

Pattern analysis is performed **only on provided inputs**. The current
implementation can enrich metadata for already-collected records but does not
probe external endpoints or attempt unauthorized discovery.

If you need network discovery, provide a written authorization scope and an
allowlist of domains/paths. The ingestion layer will only accept records that
clearly document source provenance and traceable telemetry.

## Explicitly Out of Scope

- Stealth fingerprint spoofing or bot-evasion behaviors
- Unsolicited crawling or directory fuzzing
- Public bucket scanning without authorization
- Search engine dorking or cache scraping
