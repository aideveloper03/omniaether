"""Telemetry system for AETHER-MINE.

Every request carries a trace_id linking:
- Proxy IP
- User-Agent
- Latency
- Success rate
- Performance metrics
"""

import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Generator
from collections import defaultdict
import threading

import structlog
from pydantic import BaseModel

from src.core.models import RequestTrace, FallbackTier, RequestMethod


logger = structlog.get_logger(__name__)


def create_trace_id() -> str:
    """Generate a unique trace ID."""
    return f"aether-{uuid.uuid4().hex[:16]}-{int(time.time() * 1000) % 1000000}"


@dataclass
class PerformanceMetrics:
    """Performance metrics for a trace."""
    
    trace_id: str
    start_time: float = field(default_factory=time.perf_counter)
    end_time: float | None = None
    latency_ms: float = 0.0
    bytes_sent: int = 0
    bytes_received: int = 0
    dns_lookup_ms: float = 0.0
    tcp_connect_ms: float = 0.0
    tls_handshake_ms: float = 0.0
    time_to_first_byte_ms: float = 0.0
    content_download_ms: float = 0.0
    
    def complete(self) -> None:
        """Mark the request as complete."""
        self.end_time = time.perf_counter()
        self.latency_ms = (self.end_time - self.start_time) * 1000
    
    @property
    def throughput_kbps(self) -> float:
        """Calculate throughput in KB/s."""
        if self.latency_ms <= 0:
            return 0.0
        return (self.bytes_received / 1024) / (self.latency_ms / 1000)


class TelemetryContext(BaseModel):
    """Context for a telemetry trace."""
    
    trace_id: str
    parent_trace_id: str | None = None
    span_id: str = ""
    operation: str = ""
    url: str = ""
    method: RequestMethod = RequestMethod.GET
    proxy_ip: str | None = None
    user_agent: str = ""
    fallback_tier: FallbackTier = FallbackTier.SHADOW_API
    started_at: datetime = datetime.now(timezone.utc)
    metadata: dict[str, Any] = {}
    
    def model_post_init(self, __context: Any) -> None:
        """Initialize span_id if not set."""
        if not self.span_id:
            self.span_id = uuid.uuid4().hex[:16]


class TelemetryStore:
    """Thread-safe store for telemetry data."""
    
    def __init__(self, max_traces: int = 10000) -> None:
        self._traces: dict[str, list[RequestTrace]] = defaultdict(list)
        self._metrics: dict[str, PerformanceMetrics] = {}
        self._lock = threading.RLock()
        self._max_traces = max_traces
        
        # Aggregated stats
        self._total_requests: int = 0
        self._successful_requests: int = 0
        self._failed_requests: int = 0
        self._total_latency_ms: float = 0.0
        self._total_bytes: int = 0
        self._requests_by_tier: dict[str, int] = defaultdict(int)
        self._errors_by_type: dict[str, int] = defaultdict(int)
    
    def add_trace(self, trace: RequestTrace) -> None:
        """Add a request trace."""
        with self._lock:
            self._traces[trace.trace_id].append(trace)
            self._metrics[trace.request_id] = PerformanceMetrics(
                trace_id=trace.trace_id,
                latency_ms=trace.latency_ms,
                bytes_received=trace.bytes_transferred,
            )
            
            # Update aggregated stats
            self._total_requests += 1
            self._total_latency_ms += trace.latency_ms
            self._total_bytes += trace.bytes_transferred
            self._requests_by_tier[trace.fallback_tier.value] += 1
            
            if trace.success:
                self._successful_requests += 1
            else:
                self._failed_requests += 1
                if trace.error_message:
                    error_type = trace.error_message.split(":")[0]
                    self._errors_by_type[error_type] += 1
            
            # Cleanup old traces if needed
            if len(self._traces) > self._max_traces:
                oldest_key = next(iter(self._traces))
                del self._traces[oldest_key]
    
    def get_traces(self, trace_id: str) -> list[RequestTrace]:
        """Get all traces for a trace_id."""
        with self._lock:
            return list(self._traces.get(trace_id, []))
    
    def get_stats(self) -> dict[str, Any]:
        """Get aggregated statistics."""
        with self._lock:
            avg_latency = (
                self._total_latency_ms / self._total_requests
                if self._total_requests > 0 else 0.0
            )
            success_rate = (
                self._successful_requests / self._total_requests
                if self._total_requests > 0 else 0.0
            )
            
            return {
                "total_requests": self._total_requests,
                "successful_requests": self._successful_requests,
                "failed_requests": self._failed_requests,
                "success_rate": success_rate,
                "avg_latency_ms": avg_latency,
                "total_bytes_transferred": self._total_bytes,
                "requests_by_tier": dict(self._requests_by_tier),
                "errors_by_type": dict(self._errors_by_type),
            }


class TelemetryManager:
    """Central telemetry management for AETHER-MINE."""
    
    _instance: "TelemetryManager | None" = None
    _lock = threading.Lock()
    
    def __new__(cls) -> "TelemetryManager":
        """Singleton pattern."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self) -> None:
        if self._initialized:
            return
        self._store = TelemetryStore()
        self._logger = structlog.get_logger("telemetry")
        self._current_context: dict[str, TelemetryContext] = {}
        self._context_lock = threading.RLock()
        self._initialized = True
    
    def create_context(
        self,
        operation: str,
        url: str = "",
        method: RequestMethod = RequestMethod.GET,
        proxy_ip: str | None = None,
        user_agent: str = "",
        parent_trace_id: str | None = None,
        fallback_tier: FallbackTier = FallbackTier.SHADOW_API,
        metadata: dict[str, Any] | None = None,
    ) -> TelemetryContext:
        """Create a new telemetry context."""
        trace_id = create_trace_id()
        ctx = TelemetryContext(
            trace_id=trace_id,
            parent_trace_id=parent_trace_id,
            operation=operation,
            url=url,
            method=method,
            proxy_ip=proxy_ip,
            user_agent=user_agent,
            fallback_tier=fallback_tier,
            metadata=metadata or {},
        )
        
        with self._context_lock:
            self._current_context[trace_id] = ctx
        
        self._logger.debug(
            "telemetry_context_created",
            trace_id=trace_id,
            operation=operation,
            url=url,
        )
        
        return ctx
    
    def record_request(
        self,
        ctx: TelemetryContext,
        status_code: int,
        latency_ms: float,
        success: bool,
        bytes_transferred: int = 0,
        error_message: str | None = None,
        retry_count: int = 0,
    ) -> RequestTrace:
        """Record a request trace."""
        trace = RequestTrace(
            trace_id=ctx.trace_id,
            url=ctx.url,
            method=ctx.method,
            proxy_ip=ctx.proxy_ip,
            user_agent=ctx.user_agent,
            latency_ms=latency_ms,
            status_code=status_code,
            success=success,
            error_message=error_message,
            retry_count=retry_count,
            fallback_tier=ctx.fallback_tier,
            bytes_transferred=bytes_transferred,
        )
        
        self._store.add_trace(trace)
        
        log_method = self._logger.info if success else self._logger.warning
        log_method(
            "request_recorded",
            trace_id=ctx.trace_id,
            url=ctx.url,
            status_code=status_code,
            latency_ms=latency_ms,
            success=success,
            tier=ctx.fallback_tier.value,
        )
        
        return trace
    
    @contextmanager
    def trace_sync(
        self,
        operation: str,
        url: str = "",
        method: RequestMethod = RequestMethod.GET,
        proxy_ip: str | None = None,
        user_agent: str = "",
        fallback_tier: FallbackTier = FallbackTier.SHADOW_API,
    ) -> Generator[TelemetryContext, None, None]:
        """Synchronous context manager for tracing."""
        ctx = self.create_context(
            operation=operation,
            url=url,
            method=method,
            proxy_ip=proxy_ip,
            user_agent=user_agent,
            fallback_tier=fallback_tier,
        )
        
        start_time = time.perf_counter()
        error: Exception | None = None
        
        try:
            yield ctx
        except Exception as e:
            error = e
            raise
        finally:
            latency_ms = (time.perf_counter() - start_time) * 1000
            
            if error:
                self.record_request(
                    ctx=ctx,
                    status_code=0,
                    latency_ms=latency_ms,
                    success=False,
                    error_message=str(error),
                )
            
            with self._context_lock:
                self._current_context.pop(ctx.trace_id, None)
    
    @asynccontextmanager
    async def trace_async(
        self,
        operation: str,
        url: str = "",
        method: RequestMethod = RequestMethod.GET,
        proxy_ip: str | None = None,
        user_agent: str = "",
        fallback_tier: FallbackTier = FallbackTier.SHADOW_API,
    ) -> AsyncGenerator[TelemetryContext, None]:
        """Async context manager for tracing."""
        ctx = self.create_context(
            operation=operation,
            url=url,
            method=method,
            proxy_ip=proxy_ip,
            user_agent=user_agent,
            fallback_tier=fallback_tier,
        )
        
        start_time = time.perf_counter()
        error: Exception | None = None
        
        try:
            yield ctx
        except Exception as e:
            error = e
            raise
        finally:
            latency_ms = (time.perf_counter() - start_time) * 1000
            
            if error:
                self.record_request(
                    ctx=ctx,
                    status_code=0,
                    latency_ms=latency_ms,
                    success=False,
                    error_message=str(error),
                )
            
            with self._context_lock:
                self._current_context.pop(ctx.trace_id, None)
    
    def get_stats(self) -> dict[str, Any]:
        """Get aggregated telemetry statistics."""
        return self._store.get_stats()
    
    def get_traces(self, trace_id: str) -> list[RequestTrace]:
        """Get all traces for a trace_id."""
        return self._store.get_traces(trace_id)


# Global telemetry instance
_telemetry: TelemetryManager | None = None


def get_telemetry() -> TelemetryManager:
    """Get the global telemetry manager instance."""
    global _telemetry
    if _telemetry is None:
        _telemetry = TelemetryManager()
    return _telemetry
