import sys
import uuid
import time
from loguru import logger
from contextvars import ContextVar
from typing import Optional, Dict, Any

# Context variable to store trace_id for current request/task
TRACE_ID: ContextVar[str] = ContextVar("trace_id", default="SYSTEM")

def get_trace_id() -> str:
    return TRACE_ID.get()

def set_trace_id(trace_id: str):
    TRACE_ID.set(trace_id)

def generate_trace_id() -> str:
    tid = str(uuid.uuid4())
    set_trace_id(tid)
    return tid

# Configure Loguru
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <magenta>{extra[trace_id]}</magenta> - <level>{message}</level>",
    level="INFO",
    enqueue=True
)
logger.configure(extra={"trace_id": "SYSTEM"})

class PerformanceTimer:
    def __init__(self, metric_name: str, tags: Optional[Dict[str, Any]] = None):
        self.metric_name = metric_name
        self.tags = tags or {}
        self.start_time = None

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (time.perf_counter() - self.start_time) * 1000  # ms
        status = "failed" if exc_type else "success"
        
        log_data = {
            "metric": self.metric_name,
            "duration_ms": round(duration, 2),
            "status": status,
            **self.tags
        }
        
        # In a real system, this would go to Prometheus/Datadog
        logger.bind(trace_id=get_trace_id()).info(f"PERFORMANCE_METRIC: {log_data}")

def log_request(trace_id: str, method: str, url: str, status_code: int, duration_ms: float, proxy: Optional[str] = None):
    logger.bind(trace_id=trace_id).info(
        f"HTTP_REQUEST: {method} {url} | Status: {status_code} | Duration: {duration_ms}ms | Proxy: {proxy or 'Direct'}"
    )
