"""Celery application configuration for AETHER-MINE."""

from celery import Celery

from src.core.config import get_settings


settings = get_settings()

celery_app = Celery(
    "aether_mine",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["src.workers.tasks"],
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    
    # Task execution settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=3600,  # 1 hour max
    task_soft_time_limit=3300,  # 55 minutes soft limit
    
    # Worker settings
    worker_prefetch_multiplier=1,
    worker_concurrency=4,
    worker_max_tasks_per_child=100,
    
    # Queue settings
    task_default_queue=settings.celery_task_default_queue,
    task_queues={
        "aether_mine": {
            "exchange": "aether_mine",
            "routing_key": "aether_mine",
        },
        "mining": {
            "exchange": "mining",
            "routing_key": "mining.#",
        },
        "analysis": {
            "exchange": "analysis",
            "routing_key": "analysis.#",
        },
        "storage": {
            "exchange": "storage",
            "routing_key": "storage.#",
        },
    },
    
    # Task routes
    task_routes={
        "src.workers.tasks.mine_*": {"queue": "mining"},
        "src.workers.tasks.analyze_*": {"queue": "analysis"},
        "src.workers.tasks.flush_*": {"queue": "storage"},
    },
    
    # Result settings
    result_expires=86400,  # 24 hours
    
    # Beat schedule for periodic tasks
    beat_schedule={
        "flush-batch-every-minute": {
            "task": "src.workers.tasks.flush_batch_task",
            "schedule": 60.0,
        },
        "health-check-every-5-minutes": {
            "task": "src.workers.tasks.health_check_task",
            "schedule": 300.0,
        },
    },
)
