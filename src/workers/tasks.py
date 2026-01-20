"""Celery tasks for AETHER-MINE mining operations."""

import asyncio
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from celery import shared_task
from celery.utils.log import get_task_logger

from src.core.config import get_settings
from src.core.telemetry import create_trace_id, get_telemetry
from src.storage.parquet_stream import ParquetStreamWriter
from src.storage.duckdb_index import get_index
from src.storage.quarantine import QuarantineManager


logger = get_task_logger(__name__)


def run_async(coro):
    """Helper to run async code in sync context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def mine_shadow_api_task(
    self,
    target_url: str,
    recursive: bool = True,
    max_depth: int = 2,
) -> dict[str, Any]:
    """Task to mine shadow APIs from a target URL."""
    trace_id = create_trace_id()
    logger.info(f"Starting shadow API mining: {target_url} (trace: {trace_id})")
    
    try:
        from src.miners.shadow_api import ShadowAPIInterceptor
        
        async def run():
            interceptor = ShadowAPIInterceptor()
            writer = ParquetStreamWriter()
            index = get_index()
            
            try:
                await interceptor.start()
                apis = await interceptor.navigate_and_intercept(target_url)
                
                domain = urlparse(target_url).netloc
                records = await interceptor.extract_to_records(domain)
                
                # Store records
                stored_count = 0
                for record in records:
                    record.trace_id = trace_id
                    batch_meta = writer.add_record(record)
                    
                    if batch_meta:
                        index.index_batch(batch_meta)
                    
                    # Index record
                    index.index_record(
                        record_id=record.record_id,
                        content_hash=record.content_hash,
                        batch_id=record.batch_id or "",
                        shard_id=record.shard_id or "",
                        file_path="",
                        source_url=record.source_provenance.url,
                        source_domain=domain,
                        content_type=record.content_type,
                        content_size_bytes=record.content_size_bytes,
                        timestamp=record.timestamp,
                        intelligence_category=record.intelligence_category.value,
                        risk_score=record.risk_score,
                    )
                    stored_count += 1
                
                # Final flush
                final_batch = writer.flush()
                if final_batch.record_count > 0:
                    index.index_batch(final_batch)
                
                return {
                    "status": "success",
                    "trace_id": trace_id,
                    "target_url": target_url,
                    "apis_discovered": len(apis),
                    "records_stored": stored_count,
                    "api_schemas": [
                        {
                            "endpoint": api.endpoint,
                            "method": api.method.value,
                            "auth_type": api.auth_type,
                        }
                        for api in apis
                    ],
                }
                
            finally:
                await interceptor.stop()
        
        return run_async(run())
        
    except Exception as e:
        logger.error(f"Shadow API mining failed: {e}")
        self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def mine_pattern_fuzz_task(
    self,
    url: str,
    max_variants: int = 20,
    recursive_depth: int = 1,
) -> dict[str, Any]:
    """Task to fuzz URL patterns."""
    trace_id = create_trace_id()
    logger.info(f"Starting pattern fuzzing: {url} (trace: {trace_id})")
    
    try:
        from src.miners.pattern_fuzzer import PatternFuzzer
        
        async def run():
            fuzzer = PatternFuzzer()
            writer = ParquetStreamWriter()
            index = get_index()
            
            results = await fuzzer.fuzz_url(url, max_variants, recursive_depth)
            discoveries = fuzzer.get_discoveries()
            
            # Download discoveries
            records = await fuzzer.download_discoveries()
            
            stored_count = 0
            for record in records:
                record.trace_id = trace_id
                batch_meta = writer.add_record(record)
                
                if batch_meta:
                    index.index_batch(batch_meta)
                
                index.index_record(
                    record_id=record.record_id,
                    content_hash=record.content_hash,
                    batch_id=record.batch_id or "",
                    shard_id=record.shard_id or "",
                    file_path="",
                    source_url=record.source_provenance.url,
                    source_domain=record.source_provenance.domain,
                    content_type=record.content_type,
                    content_size_bytes=record.content_size_bytes,
                    timestamp=record.timestamp,
                )
                stored_count += 1
            
            final_batch = writer.flush()
            if final_batch.record_count > 0:
                index.index_batch(final_batch)
            
            return {
                "status": "success",
                "trace_id": trace_id,
                "original_url": url,
                "urls_checked": len(results),
                "discoveries": len(discoveries),
                "records_stored": stored_count,
                "discovered_urls": discoveries[:20],  # First 20
            }
        
        return run_async(run())
        
    except Exception as e:
        logger.error(f"Pattern fuzzing failed: {e}")
        self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def mine_cloud_buckets_task(
    self,
    brand_name: str,
    providers: list[str] | None = None,
    max_permutations: int = 200,
) -> dict[str, Any]:
    """Task to sniff for public cloud buckets."""
    trace_id = create_trace_id()
    logger.info(f"Starting cloud bucket sniffing: {brand_name} (trace: {trace_id})")
    
    try:
        from src.miners.cloud_sniffer import CloudBucketSniffer
        
        async def run():
            sniffer = CloudBucketSniffer()
            writer = ParquetStreamWriter()
            index = get_index()
            
            results = await sniffer.sniff_brand(
                brand_name,
                providers=providers or ["aws", "azure", "gcp"],
                max_permutations=max_permutations,
            )
            
            public_buckets = sniffer.get_public_buckets()
            stored_count = 0
            
            # Download contents from public buckets
            for bucket in public_buckets[:10]:  # Limit to 10 buckets
                objects = await sniffer.enumerate_bucket(bucket.url, bucket.provider)
                records = await sniffer.download_objects(objects[:50])  # 50 objects per bucket
                
                for record in records:
                    record.trace_id = trace_id
                    batch_meta = writer.add_record(record)
                    
                    if batch_meta:
                        index.index_batch(batch_meta)
                    
                    index.index_record(
                        record_id=record.record_id,
                        content_hash=record.content_hash,
                        batch_id=record.batch_id or "",
                        shard_id=record.shard_id or "",
                        file_path="",
                        source_url=record.source_provenance.url,
                        source_domain=record.source_provenance.domain,
                        content_type=record.content_type,
                        content_size_bytes=record.content_size_bytes,
                        timestamp=record.timestamp,
                    )
                    stored_count += 1
            
            final_batch = writer.flush()
            if final_batch.record_count > 0:
                index.index_batch(final_batch)
            
            return {
                "status": "success",
                "trace_id": trace_id,
                "brand_name": brand_name,
                "buckets_checked": len(results),
                "public_buckets_found": len(public_buckets),
                "records_stored": stored_count,
                "public_bucket_urls": [b.url for b in public_buckets],
            }
        
        return run_async(run())
        
    except Exception as e:
        logger.error(f"Cloud bucket sniffing failed: {e}")
        self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def mine_dorking_task(
    self,
    target: str,
    categories: list[str] | None = None,
    min_risk_level: str = "medium",
    engines: list[str] | None = None,
) -> dict[str, Any]:
    """Task to run dorking swarm."""
    trace_id = create_trace_id()
    logger.info(f"Starting dorking swarm: {target} (trace: {trace_id})")
    
    try:
        from src.miners.dorking import DorkingSwarm
        
        async def run():
            swarm = DorkingSwarm()
            writer = ParquetStreamWriter()
            index = get_index()
            
            results = await swarm.swarm_target(
                target,
                categories=categories,
                min_risk_level=min_risk_level,
                engines=engines or ["duckduckgo"],
            )
            
            all_results = swarm.get_all_results()
            records = await swarm.verify_and_download(all_results)
            
            stored_count = 0
            for record in records:
                record.trace_id = trace_id
                batch_meta = writer.add_record(record)
                
                if batch_meta:
                    index.index_batch(batch_meta)
                
                index.index_record(
                    record_id=record.record_id,
                    content_hash=record.content_hash,
                    batch_id=record.batch_id or "",
                    shard_id=record.shard_id or "",
                    file_path="",
                    source_url=record.source_provenance.url,
                    source_domain=record.source_provenance.domain,
                    content_type=record.content_type,
                    content_size_bytes=record.content_size_bytes,
                    timestamp=record.timestamp,
                )
                stored_count += 1
            
            final_batch = writer.flush()
            if final_batch.record_count > 0:
                index.index_batch(final_batch)
            
            return {
                "status": "success",
                "trace_id": trace_id,
                "target": target,
                "total_results": len(all_results),
                "records_stored": stored_count,
                "results_by_category": {
                    cat: len(res) for cat, res in results.items()
                },
            }
        
        return run_async(run())
        
    except Exception as e:
        logger.error(f"Dorking swarm failed: {e}")
        self.retry(exc=e)


@shared_task(bind=True, max_retries=2)
def analyze_intelligence_task(
    self,
    record_id: str,
) -> dict[str, Any]:
    """Task to analyze a record with LLM intelligence parser."""
    trace_id = create_trace_id()
    logger.info(f"Starting intelligence analysis: {record_id} (trace: {trace_id})")
    
    try:
        from src.core.intelligence import IntelligenceParser
        from src.storage.parquet_stream import ParquetReader
        
        async def run():
            parser = IntelligenceParser()
            reader = ParquetReader()
            index = get_index()
            
            # Get record from index
            record_data = index.lookup_by_id(record_id)
            if not record_data:
                return {"status": "error", "message": "Record not found"}
            
            # Read the actual record from Parquet
            # (In production, would load from the correct batch file)
            
            # For now, return a placeholder
            return {
                "status": "success",
                "trace_id": trace_id,
                "record_id": record_id,
                "message": "Analysis queued",
            }
        
        return run_async(run())
        
    except Exception as e:
        logger.error(f"Intelligence analysis failed: {e}")
        self.retry(exc=e)


@shared_task
def flush_batch_task() -> dict[str, Any]:
    """Periodic task to flush pending records to Parquet."""
    trace_id = create_trace_id()
    logger.info(f"Running batch flush (trace: {trace_id})")
    
    try:
        writer = ParquetStreamWriter()
        index = get_index()
        
        if writer.pending_records > 0:
            batch_meta = writer.flush()
            
            if batch_meta.record_count > 0:
                index.index_batch(batch_meta)
                
                return {
                    "status": "success",
                    "trace_id": trace_id,
                    "records_flushed": batch_meta.record_count,
                    "batch_id": batch_meta.batch_id,
                }
        
        return {
            "status": "success",
            "trace_id": trace_id,
            "records_flushed": 0,
            "message": "No pending records",
        }
        
    except Exception as e:
        logger.error(f"Batch flush failed: {e}")
        return {"status": "error", "error": str(e)}


@shared_task
def health_check_task() -> dict[str, Any]:
    """Periodic health check task."""
    trace_id = create_trace_id()
    
    try:
        index = get_index()
        stats = index.get_global_stats()
        telemetry = get_telemetry()
        telemetry_stats = telemetry.get_stats()
        
        return {
            "status": "healthy",
            "trace_id": trace_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "index_stats": stats,
            "telemetry_stats": telemetry_stats,
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "trace_id": trace_id,
            "error": str(e),
        }
