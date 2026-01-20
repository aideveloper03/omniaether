"""FastAPI Controller for AETHER-MINE.

Provides REST API for:
- Mining task management
- Data retrieval
- System monitoring
- Configuration
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.core.config import get_settings, Settings
from src.core.telemetry import get_telemetry
from src.storage.duckdb_index import get_index
from src.storage.parquet_stream import ParquetStreamWriter
from src.storage.quarantine import QuarantineManager


# Request/Response Models
class MiningTaskRequest(BaseModel):
    """Request to create a mining task."""
    
    target_url: str = Field(..., description="URL to mine")
    discovery_method: str = Field(
        default="shadow_api",
        description="Method: shadow_api, pattern_fuzz, cloud_sniff, dorking"
    )
    recursive: bool = Field(default=True, description="Enable recursive discovery")
    max_depth: int = Field(default=2, ge=1, le=5, description="Max recursion depth")
    enable_stealth: bool = Field(default=True, description="Enable stealth mode")


class MiningTaskResponse(BaseModel):
    """Response for a mining task."""
    
    task_id: str
    status: str
    target_url: str
    created_at: datetime
    message: str


class BrandSniffRequest(BaseModel):
    """Request to sniff cloud buckets for a brand."""
    
    brand_name: str = Field(..., min_length=2, description="Brand name to search")
    providers: list[str] = Field(
        default=["aws", "azure", "gcp"],
        description="Cloud providers to check"
    )
    max_permutations: int = Field(default=200, ge=10, le=1000)


class DorkingRequest(BaseModel):
    """Request for dorking swarm."""
    
    target: str = Field(..., description="Target domain or brand")
    categories: list[str] | None = Field(
        default=None,
        description="Dork categories to use"
    )
    min_risk_level: str = Field(
        default="medium",
        description="Minimum risk level: low, medium, high, critical"
    )
    engines: list[str] = Field(
        default=["duckduckgo"],
        description="Search engines to use"
    )


class SearchRequest(BaseModel):
    """Request to search indexed records."""
    
    query_type: str = Field(
        ..., description="Type: hash, domain, category, risk_score"
    )
    query_value: str = Field(..., description="Value to search for")
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class SystemStats(BaseModel):
    """System statistics response."""
    
    total_records: int
    unique_content_hashes: int
    unique_domains: int
    finalized_batches: int
    total_storage_bytes: int
    duplicate_rate: float
    quarantine_count: int
    telemetry_stats: dict[str, Any]


# Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    settings = get_settings()
    app.state.settings = settings
    app.state.telemetry = get_telemetry()
    app.state.index = get_index()
    app.state.writer = ParquetStreamWriter()
    app.state.quarantine = QuarantineManager()
    
    yield
    
    # Shutdown
    app.state.writer.flush()
    app.state.index.close()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    
    app = FastAPI(
        title="AETHER-MINE API",
        description="Distributed Intelligence & Adversarial Web Mining Engine",
        version="1.0.0",
        lifespan=lifespan,
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    return app


app = create_app()


# Health endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/ready")
async def readiness_check():
    """Readiness check endpoint."""
    try:
        # Check critical components
        index = get_index()
        stats = index.get_global_stats()
        return {
            "status": "ready",
            "components": {
                "index": "healthy",
                "records": stats["total_records"],
            }
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# Mining endpoints
@app.post("/api/v1/mining/task", response_model=MiningTaskResponse)
async def create_mining_task(
    request: MiningTaskRequest,
    background_tasks: BackgroundTasks,
):
    """Create a new mining task."""
    import uuid
    
    task_id = str(uuid.uuid4())
    
    # Queue the task (would normally go to Celery)
    # For now, return acknowledgment
    
    return MiningTaskResponse(
        task_id=task_id,
        status="queued",
        target_url=request.target_url,
        created_at=datetime.now(timezone.utc),
        message=f"Mining task created with method: {request.discovery_method}",
    )


@app.post("/api/v1/mining/shadow-api")
async def mine_shadow_api(
    request: MiningTaskRequest,
    background_tasks: BackgroundTasks,
):
    """Mine shadow APIs from a target URL."""
    from src.miners.shadow_api import ShadowAPIInterceptor
    
    async def run_mining():
        interceptor = ShadowAPIInterceptor()
        try:
            await interceptor.start()
            apis = await interceptor.navigate_and_intercept(request.target_url)
            records = await interceptor.extract_to_records(
                urlparse(request.target_url).netloc
            )
            
            # Store records
            writer = app.state.writer
            for record in records:
                writer.add_record(record)
            
            writer.flush()
        finally:
            await interceptor.stop()
    
    from urllib.parse import urlparse
    
    background_tasks.add_task(run_mining)
    
    return {
        "status": "started",
        "target": request.target_url,
        "method": "shadow_api",
    }


@app.post("/api/v1/mining/pattern-fuzz")
async def mine_pattern_fuzz(
    url: str = Query(..., description="URL to fuzz"),
    max_variants: int = Query(default=20, ge=5, le=100),
    recursive_depth: int = Query(default=1, ge=0, le=3),
    background_tasks: BackgroundTasks = None,
):
    """Fuzz URL patterns to discover unindexed resources."""
    from src.miners.pattern_fuzzer import PatternFuzzer
    
    async def run_fuzzing():
        fuzzer = PatternFuzzer()
        results = await fuzzer.fuzz_url(url, max_variants, recursive_depth)
        records = await fuzzer.download_discoveries()
        
        writer = app.state.writer
        for record in records:
            writer.add_record(record)
        
        writer.flush()
    
    background_tasks.add_task(run_fuzzing)
    
    return {
        "status": "started",
        "target": url,
        "method": "pattern_fuzz",
        "max_variants": max_variants,
    }


@app.post("/api/v1/mining/cloud-sniff")
async def mine_cloud_buckets(
    request: BrandSniffRequest,
    background_tasks: BackgroundTasks,
):
    """Sniff for public cloud buckets related to a brand."""
    from src.miners.cloud_sniffer import CloudBucketSniffer
    
    async def run_sniffing():
        sniffer = CloudBucketSniffer()
        results = await sniffer.sniff_brand(
            request.brand_name,
            providers=request.providers,
            max_permutations=request.max_permutations,
        )
        
        # Download public bucket contents
        public_buckets = sniffer.get_public_buckets()
        for bucket in public_buckets:
            objects = await sniffer.enumerate_bucket(bucket.url)
            records = await sniffer.download_objects(objects[:100])
            
            writer = app.state.writer
            for record in records:
                writer.add_record(record)
        
        writer.flush()
    
    background_tasks.add_task(run_sniffing)
    
    return {
        "status": "started",
        "brand": request.brand_name,
        "providers": request.providers,
        "method": "cloud_sniff",
    }


@app.post("/api/v1/mining/dorking")
async def mine_with_dorks(
    request: DorkingRequest,
    background_tasks: BackgroundTasks,
):
    """Run dorking swarm against a target."""
    from src.miners.dorking import DorkingSwarm
    
    async def run_dorking():
        swarm = DorkingSwarm()
        results = await swarm.swarm_target(
            request.target,
            categories=request.categories,
            min_risk_level=request.min_risk_level,
            engines=request.engines,
        )
        
        # Download and verify discovered URLs
        all_results = swarm.get_all_results()
        records = await swarm.verify_and_download(all_results)
        
        writer = app.state.writer
        for record in records:
            writer.add_record(record)
        
        writer.flush()
    
    background_tasks.add_task(run_dorking)
    
    return {
        "status": "started",
        "target": request.target,
        "method": "dorking",
        "categories": request.categories,
    }


# Data retrieval endpoints
@app.post("/api/v1/search")
async def search_records(request: SearchRequest):
    """Search indexed records."""
    index = app.state.index
    
    if request.query_type == "hash":
        result = index.lookup_by_hash(request.query_value)
        return {"results": [result] if result else [], "total": 1 if result else 0}
    
    elif request.query_type == "domain":
        results = index.search_by_domain(
            request.query_value,
            limit=request.limit,
            offset=request.offset,
        )
        return {"results": results, "total": len(results)}
    
    elif request.query_type == "category":
        results = index.search_by_category(
            request.query_value,
            limit=request.limit,
            offset=request.offset,
        )
        return {"results": results, "total": len(results)}
    
    elif request.query_type == "risk_score":
        min_score = float(request.query_value)
        results = index.search_by_risk_score(min_score, limit=request.limit)
        return {"results": results, "total": len(results)}
    
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown query_type: {request.query_type}"
        )


@app.get("/api/v1/record/{record_id}")
async def get_record(record_id: str):
    """Get a specific record by ID."""
    index = app.state.index
    result = index.lookup_by_id(record_id)
    
    if not result:
        raise HTTPException(status_code=404, detail="Record not found")
    
    return result


@app.get("/api/v1/domains")
async def list_domains():
    """List all indexed domains with statistics."""
    index = app.state.index
    return {"domains": index.get_domain_stats()}


# System monitoring endpoints
@app.get("/api/v1/stats", response_model=SystemStats)
async def get_system_stats():
    """Get system statistics."""
    index = app.state.index
    quarantine = app.state.quarantine
    telemetry = app.state.telemetry
    
    index_stats = index.get_global_stats()
    quarantine_stats = quarantine.get_quarantine_stats()
    telemetry_stats = telemetry.get_stats()
    
    return SystemStats(
        total_records=index_stats["total_records"],
        unique_content_hashes=index_stats["unique_content_hashes"],
        unique_domains=index_stats["unique_domains"],
        finalized_batches=index_stats["finalized_batches"],
        total_storage_bytes=index_stats["total_storage_bytes"],
        duplicate_rate=index_stats["duplicate_rate"],
        quarantine_count=quarantine_stats["total_quarantined"],
        telemetry_stats=telemetry_stats,
    )


@app.get("/api/v1/quarantine")
async def get_quarantine_stats():
    """Get quarantine statistics."""
    quarantine = app.state.quarantine
    return quarantine.get_quarantine_stats()


@app.get("/api/v1/quarantine/records")
async def list_quarantined_records(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """List quarantined records."""
    quarantine = app.state.quarantine
    records = quarantine.list_quarantined(limit=limit, offset=offset)
    return {"records": records, "total": len(records)}


@app.post("/api/v1/quarantine/recover/{record_id}")
async def recover_quarantined_record(record_id: str):
    """Attempt to recover a quarantined record."""
    quarantine = app.state.quarantine
    recovered = quarantine.attempt_recovery(record_id)
    
    if recovered:
        writer = app.state.writer
        writer.add_record(recovered)
        return {"status": "recovered", "record_id": record_id}
    else:
        raise HTTPException(
            status_code=400,
            detail="Recovery failed - record cannot be fixed automatically"
        )


@app.get("/api/v1/telemetry")
async def get_telemetry_stats():
    """Get telemetry statistics."""
    telemetry = app.state.telemetry
    return telemetry.get_stats()


@app.get("/api/v1/telemetry/traces/{trace_id}")
async def get_traces(trace_id: str):
    """Get all traces for a trace ID."""
    telemetry = app.state.telemetry
    traces = telemetry.get_traces(trace_id)
    return {"traces": [t.model_dump() for t in traces]}


# Configuration endpoint
@app.get("/api/v1/config")
async def get_config():
    """Get current configuration (non-sensitive)."""
    settings: Settings = app.state.settings
    return {
        "app_name": settings.app_name,
        "environment": settings.environment,
        "batch_max_records": settings.batch_max_records,
        "batch_max_size_mb": settings.batch_max_size_mb,
        "proxy_pool_size": settings.proxy_pool_size,
        "browser_headless": settings.browser_headless,
        "behavioral_noise_enabled": settings.behavioral_noise_enabled,
        "llm_provider": settings.llm_provider,
    }


# Error handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    import structlog
    logger = structlog.get_logger(__name__)
    logger.error("unhandled_exception", error=str(exc), path=request.url.path)
    
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)},
    )
