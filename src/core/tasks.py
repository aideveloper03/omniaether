import asyncio
from typing import Optional
from celery import Task
from playwright.async_api import async_playwright
from src.core.celery_config import celery_app
from src.core.telemetry import generate_trace_id, set_trace_id, logger
from src.core.evasion import EvasionProfile
from src.miners.shadow_api import ShadowApiMiner
from src.miners.recursive_fuzzer import RecursiveFuzzer
from src.miners.cloud_sniffer import CloudBucketSniffer

class BaseMiningTask(Task):
    abstract = True
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(f"Task {task_id} failed: {exc}")

@celery_app.task(base=BaseMiningTask, bind=True, name="tasks.shadow_mine")
def shadow_mine_task(self, url: str):
    trace_id = generate_trace_id()
    logger.info(f"Starting Shadow Mine for {url} [Trace: {trace_id}]")
    
    async def _run():
        async with async_playwright() as p:
            # Launch browser with evasion
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            
            # Apply Stealth
            await EvasionProfile.configure_playwright_context(context)
            
            page = await context.new_page()
            miner = ShadowApiMiner()
            
            await miner.start_interception(page, url)
            await browser.close()

    try:
        asyncio.run(_run())
        return {"status": "success", "url": url, "trace_id": trace_id}
    except Exception as e:
        logger.error(f"Shadow mine failed: {e}")
        raise e

@celery_app.task(base=BaseMiningTask, bind=True, name="tasks.fuzz_resource")
def fuzz_resource_task(self, url: str):
    trace_id = generate_trace_id()
    logger.info(f"Starting Fuzzer for {url}")
    
    async def _run():
        fuzzer = RecursiveFuzzer()
        await fuzzer.fuzz_resource(url)

    asyncio.run(_run())
    return {"status": "success", "trace_id": trace_id}

@celery_app.task(base=BaseMiningTask, bind=True, name="tasks.sniff_cloud")
def sniff_cloud_task(self, brand_name: str):
    trace_id = generate_trace_id()
    logger.info(f"Starting Cloud Sniff for {brand_name}")
    
    async def _run():
        sniffer = CloudBucketSniffer()
        await sniffer.sniff_brand(brand_name)

    asyncio.run(_run())
    return {"status": "success", "trace_id": trace_id}
