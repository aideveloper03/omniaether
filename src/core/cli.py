from __future__ import annotations

import argparse
from typing import Any, Dict, List
from uuid import uuid4

from core.config import AppConfig
from core.orchestrator import IngestionOrchestrator
from miners.local_file_miner import LocalFileMiner
from miners.manifest_ingester import load_manifest


def _ingest_manifest(path: str, batch_id: str) -> None:
    records = load_manifest(path)
    orchestrator = IngestionOrchestrator(AppConfig.from_env())
    try:
        report = orchestrator.ingest_records(records, batch_id)
    finally:
        orchestrator.close()
    _print_report(report)


def _ingest_local(path: str, batch_id: str) -> None:
    miner = LocalFileMiner(path, batch_id=batch_id)
    records: List[Dict[str, Any]] = list(miner.iter_records())
    orchestrator = IngestionOrchestrator(AppConfig.from_env())
    try:
        report = orchestrator.ingest_records(records, batch_id)
    finally:
        orchestrator.close()
    _print_report(report)


def _print_report(report: Any) -> None:
    print(f"batch_id={report.batch_id}")
    print(f"received={report.received}")
    print(f"stored={report.stored}")
    print(f"quarantined={report.quarantined}")
    print("parquet_files:")
    for path in report.parquet_files:
        print(f"  - {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Aether-Mine ingestion CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    manifest_cmd = subparsers.add_parser("ingest-manifest", help="Ingest JSON/JSONL")
    manifest_cmd.add_argument("--path", required=True, help="Path to manifest file")
    manifest_cmd.add_argument(
        "--batch-id", default=str(uuid4()), help="Batch ID override"
    )

    local_cmd = subparsers.add_parser("ingest-local", help="Ingest local files")
    local_cmd.add_argument("--path", required=True, help="Path to local directory")
    local_cmd.add_argument("--batch-id", default=str(uuid4()), help="Batch ID override")

    args = parser.parse_args()
    if args.command == "ingest-manifest":
        _ingest_manifest(args.path, args.batch_id)
    elif args.command == "ingest-local":
        _ingest_local(args.path, args.batch_id)
    else:
        raise SystemExit("unknown command")


if __name__ == "__main__":
    main()
