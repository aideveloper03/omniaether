from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

from core.config import AppConfig
from core.orchestrator import IngestionOrchestrator
from core.tasks import process_batch


class IngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    records: List[Dict[str, Any]]
    batch_id: Optional[str] = None


def create_app() -> FastAPI:
    config = AppConfig.from_env()
    orchestrator = IngestionOrchestrator(config)
    app = FastAPI(title="Aether-Mine Ingestion API")

    @app.on_event("shutdown")
    def _shutdown() -> None:
        orchestrator.close()

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/ingest")
    def ingest(request: IngestRequest, sync: bool = True) -> Dict[str, Any]:
        batch_id = request.batch_id or str(uuid4())
        if sync:
            report = orchestrator.ingest_records(request.records, batch_id)
            return {
                "batch_id": report.batch_id,
                "received": report.received,
                "stored": report.stored,
                "quarantined": report.quarantined,
                "parquet_files": report.parquet_files,
            }
        try:
            task = process_batch.apply_async(args=[request.records, batch_id])
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {
            "batch_id": batch_id,
            "task_id": task.id,
            "status": "queued",
        }

    return app


app = create_app()
