from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel, HttpUrl
from typing import Optional
from src.core.config import settings
from src.core.celery_config import celery_app
from src.core.tasks import shadow_mine_task, fuzz_resource_task, sniff_cloud_task
from src.core.telemetry import logger

app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION)

class MiningRequest(BaseModel):
    url: HttpUrl
    mining_type: str = "shadow_api" # shadow_api, fuzz, full

class BrandRequest(BaseModel):
    brand_name: str

@app.get("/")
def health_check():
    return {"status": "active", "version": settings.VERSION}

@app.post("/mine/url")
def trigger_mining(request: MiningRequest):
    """
    Trigger a mining task for a specific URL.
    """
    url_str = str(request.url)
    task = None
    
    if request.mining_type == "shadow_api":
        task = shadow_mine_task.delay(url_str)
    elif request.mining_type == "fuzz":
        task = fuzz_resource_task.delay(url_str)
    else:
        # Full mode: Trigger both
        t1 = shadow_mine_task.delay(url_str)
        t2 = fuzz_resource_task.delay(url_str)
        return {"status": "queued", "task_ids": [str(t1.id), str(t2.id)]}

    return {"status": "queued", "task_id": str(task.id)}

@app.post("/mine/brand")
def trigger_brand_scan(request: BrandRequest):
    """
    Trigger cloud bucket sniffing for a brand.
    """
    task = sniff_cloud_task.delay(request.brand_name)
    return {"status": "queued", "task_id": str(task.id)}
