from __future__ import annotations

import os
from typing import Any, Dict, List

from celery import Celery

from core.config import AppConfig
from core.orchestrator import IngestionOrchestrator


def _broker_url() -> str:
    return os.getenv("AETHER_BROKER_URL", "redis://localhost:6379/0")


def _result_backend() -> str:
    return os.getenv("AETHER_RESULT_BACKEND", "redis://localhost:6379/1")


celery_app = Celery("aether_mine", broker=_broker_url(), backend=_result_backend())
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


@celery_app.task(name="process_batch")
def process_batch(records: List[Dict[str, Any]], batch_id: str) -> Dict[str, Any]:
    config = AppConfig.from_env()
    orchestrator = IngestionOrchestrator(config)
    try:
        report = orchestrator.ingest_records(records, batch_id)
        return {
            "batch_id": report.batch_id,
            "received": report.received,
            "stored": report.stored,
            "quarantined": report.quarantined,
            "parquet_files": report.parquet_files,
        }
    finally:
        orchestrator.close()
