from celery import Celery
from src.core.config import settings

celery_app = Celery(
    "aether_mine",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["src.core.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1, # Fair dispatch
    task_acks_late=True,
)
