"""Core data models for AETHER-MINE with strict Pydantic v2 validation.

Implements Zero-Null Policy: All records must have source_provenance, 
timestamp, and content_hash or be routed to quarantine.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from hashlib import sha256
import uuid

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
    ConfigDict,
    computed_field,
)


class RecordStatus(str, Enum):
    """Status of a mined record."""
    VALID = "valid"
    QUARANTINED = "quarantined"
    PENDING_VALIDATION = "pending_validation"
    PROCESSED = "processed"


class RequestMethod(str, Enum):
    """HTTP request methods."""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    OPTIONS = "OPTIONS"
    HEAD = "HEAD"


class FallbackTier(str, Enum):
    """Cascading fallback tiers for data retrieval."""
    SHADOW_API = "shadow_api"
    HEADLESS_BROWSER = "headless_browser"
    WAYBACK_MACHINE = "wayback_machine"
    GOOGLE_CACHE = "google_cache"
    HUMAN_IN_LOOP = "human_in_loop"


class ProxyStatus(str, Enum):
    """Proxy health status."""
    ACTIVE = "active"
    DEGRADED = "degraded"
    BURNED = "burned"
    COOLING_DOWN = "cooling_down"


class IntelligenceCategory(str, Enum):
    """Categories for LLM-processed intelligence."""
    ENTITY_GRAPH = "entity_graph"
    RISK_VECTOR = "risk_vector"
    ASSET_INVENTORY = "asset_inventory"
    FINANCIAL_DATA = "financial_data"
    METADATA = "metadata"
    UNCLASSIFIED = "unclassified"


class SourceProvenance(BaseModel):
    """Provenance tracking for data sources - Required for all records."""
    
    model_config = ConfigDict(frozen=True)
    
    url: str = Field(..., min_length=1, description="Source URL")
    domain: str = Field(..., min_length=1, description="Source domain")
    discovery_method: str = Field(..., min_length=1, description="How the data was discovered")
    retrieval_tier: FallbackTier = Field(..., description="Which fallback tier succeeded")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the data was retrieved"
    )
    proxy_id: str | None = Field(default=None, description="Proxy used for retrieval")
    user_agent: str | None = Field(default=None, description="User agent used")
    
    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL format."""
        if not v.startswith(("http://", "https://", "s3://", "gs://", "azure://")):
            raise ValueError("URL must start with valid protocol")
        return v


class RequestTrace(BaseModel):
    """Telemetry data for every request - links proxy, user-agent, and latency."""
    
    model_config = ConfigDict(frozen=True)
    
    trace_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique trace identifier"
    )
    request_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique request identifier"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    url: str = Field(..., min_length=1)
    method: RequestMethod = Field(default=RequestMethod.GET)
    proxy_ip: str | None = Field(default=None)
    user_agent: str = Field(..., min_length=1)
    latency_ms: float = Field(..., ge=0)
    status_code: int = Field(..., ge=100, le=599)
    success: bool = Field(...)
    error_message: str | None = Field(default=None)
    retry_count: int = Field(default=0, ge=0)
    fallback_tier: FallbackTier = Field(default=FallbackTier.SHADOW_API)
    bytes_transferred: int = Field(default=0, ge=0)
    
    @computed_field
    @property
    def throughput_kbps(self) -> float:
        """Calculate throughput in KB/s."""
        if self.latency_ms <= 0:
            return 0.0
        return (self.bytes_transferred / 1024) / (self.latency_ms / 1000)


class APISchema(BaseModel):
    """Extracted API schema from shadow API interception."""
    
    model_config = ConfigDict(frozen=True)
    
    endpoint: str = Field(..., min_length=1, description="API endpoint path")
    base_url: str = Field(..., min_length=1, description="Base URL")
    method: RequestMethod = Field(default=RequestMethod.GET)
    request_headers: dict[str, str] = Field(default_factory=dict)
    response_headers: dict[str, str] = Field(default_factory=dict)
    query_params: dict[str, str] = Field(default_factory=dict)
    request_body_schema: dict[str, Any] | None = Field(default=None)
    response_body_schema: dict[str, Any] | None = Field(default=None)
    auth_type: str | None = Field(default=None, description="Bearer, API-Key, Cookie, etc.")
    auth_header: str | None = Field(default=None, description="Authorization header name")
    content_type: str = Field(default="application/json")
    discovered_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    
    @computed_field
    @property
    def full_url(self) -> str:
        """Construct full URL."""
        return f"{self.base_url.rstrip('/')}/{self.endpoint.lstrip('/')}"


class MinedRecord(BaseModel):
    """Core record model with Zero-Null policy enforcement.
    
    Any record missing source_provenance, timestamp, or content_hash
    will be automatically marked for quarantine.
    """
    
    model_config = ConfigDict(
        validate_assignment=True,
        use_enum_values=True,
    )
    
    # Primary Key
    record_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique record identifier"
    )
    
    # Required Fields (Zero-Null Policy)
    source_provenance: SourceProvenance = Field(
        ..., description="REQUIRED: Data source provenance"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="REQUIRED: Record creation timestamp"
    )
    content_hash: str = Field(
        ..., min_length=64, max_length=64,
        description="REQUIRED: SHA-256 hash of content"
    )
    
    # Content
    content_type: str = Field(..., min_length=1, description="MIME type of content")
    content: bytes | str = Field(..., description="Raw content data")
    content_size_bytes: int = Field(..., ge=0, description="Content size in bytes")
    
    # Metadata
    title: str | None = Field(default=None)
    description: str | None = Field(default=None)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    # Processing Status
    status: RecordStatus = Field(default=RecordStatus.VALID)
    batch_id: str | None = Field(default=None)
    shard_id: str | None = Field(default=None)
    
    # Intelligence Classification
    intelligence_category: IntelligenceCategory = Field(
        default=IntelligenceCategory.UNCLASSIFIED
    )
    extracted_entities: list[dict[str, Any]] = Field(default_factory=list)
    risk_score: float | None = Field(default=None, ge=0, le=1)
    
    # Trace
    trace_id: str | None = Field(default=None)
    
    @field_validator("content_hash")
    @classmethod
    def validate_hash_format(cls, v: str) -> str:
        """Validate SHA-256 hash format."""
        if not all(c in "0123456789abcdef" for c in v.lower()):
            raise ValueError("content_hash must be a valid hex string")
        return v.lower()
    
    @model_validator(mode="after")
    def validate_zero_null_policy(self) -> "MinedRecord":
        """Enforce Zero-Null policy - quarantine invalid records."""
        quarantine_reasons = []
        
        if not self.source_provenance:
            quarantine_reasons.append("missing_source_provenance")
        if not self.timestamp:
            quarantine_reasons.append("missing_timestamp")
        if not self.content_hash:
            quarantine_reasons.append("missing_content_hash")
        
        if quarantine_reasons:
            self.status = RecordStatus.QUARANTINED
            self.metadata["quarantine_reasons"] = quarantine_reasons
        
        return self
    
    @classmethod
    def compute_content_hash(cls, content: bytes | str) -> str:
        """Compute SHA-256 hash of content."""
        if isinstance(content, str):
            content = content.encode("utf-8")
        return sha256(content).hexdigest()


class QuarantinedRecord(BaseModel):
    """Record that failed Zero-Null validation."""
    
    model_config = ConfigDict(frozen=True)
    
    record_id: str = Field(
        default_factory=lambda: str(uuid.uuid4())
    )
    original_data: dict[str, Any] = Field(...)
    quarantine_reasons: list[str] = Field(...)
    quarantine_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    source_url: str | None = Field(default=None)
    recovery_attempts: int = Field(default=0)


class BatchMetadata(BaseModel):
    """Metadata for a Parquet batch/shard."""
    
    model_config = ConfigDict(frozen=True)
    
    batch_id: str = Field(
        default_factory=lambda: str(uuid.uuid4())
    )
    shard_id: str = Field(
        default_factory=lambda: str(uuid.uuid4())
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    record_count: int = Field(..., ge=0)
    size_bytes: int = Field(..., ge=0)
    file_path: str = Field(...)
    content_hashes: list[str] = Field(default_factory=list)
    primary_keys: list[str] = Field(default_factory=list)
    min_timestamp: datetime | None = Field(default=None)
    max_timestamp: datetime | None = Field(default=None)
    compression: str = Field(default="snappy")
    is_finalized: bool = Field(default=False)


class ProxyHealth(BaseModel):
    """Proxy health tracking with circuit breaker logic."""
    
    proxy_id: str = Field(...)
    proxy_url: str = Field(...)
    status: ProxyStatus = Field(default=ProxyStatus.ACTIVE)
    total_requests: int = Field(default=0, ge=0)
    successful_requests: int = Field(default=0, ge=0)
    failed_requests: int = Field(default=0, ge=0)
    consecutive_failures: int = Field(default=0, ge=0)
    last_used: datetime | None = Field(default=None)
    last_failure: datetime | None = Field(default=None)
    burned_at: datetime | None = Field(default=None)
    cooldown_until: datetime | None = Field(default=None)
    avg_latency_ms: float = Field(default=0.0, ge=0)
    
    @computed_field
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests
    
    def record_success(self, latency_ms: float) -> None:
        """Record a successful request."""
        self.total_requests += 1
        self.successful_requests += 1
        self.consecutive_failures = 0
        self.last_used = datetime.now(timezone.utc)
        # Rolling average
        self.avg_latency_ms = (
            (self.avg_latency_ms * (self.total_requests - 1) + latency_ms)
            / self.total_requests
        )
    
    def record_failure(self, max_failures: int = 3, burn_hours: int = 24) -> None:
        """Record a failed request with circuit breaker logic."""
        self.total_requests += 1
        self.failed_requests += 1
        self.consecutive_failures += 1
        self.last_failure = datetime.now(timezone.utc)
        
        if self.consecutive_failures >= max_failures:
            self.status = ProxyStatus.BURNED
            self.burned_at = datetime.now(timezone.utc)
            self.cooldown_until = datetime.now(timezone.utc).replace(
                hour=datetime.now(timezone.utc).hour + burn_hours
            )


class DeviceFingerprint(BaseModel):
    """Device fingerprint for evasion."""
    
    model_config = ConfigDict(frozen=True)
    
    fingerprint_id: str = Field(
        default_factory=lambda: str(uuid.uuid4())
    )
    screen_width: int = Field(..., ge=800, le=7680)
    screen_height: int = Field(..., ge=600, le=4320)
    color_depth: int = Field(default=24, ge=8, le=48)
    pixel_ratio: float = Field(default=1.0, ge=1.0, le=4.0)
    platform: str = Field(default="Win32")
    gpu_vendor: str = Field(default="Google Inc. (NVIDIA)")
    gpu_renderer: str = Field(default="ANGLE (NVIDIA GeForce RTX 3080)")
    timezone: str = Field(default="America/New_York")
    language: str = Field(default="en-US")
    webgl_hash: str | None = Field(default=None)
    canvas_hash: str | None = Field(default=None)
    audio_hash: str | None = Field(default=None)
    fonts: list[str] = Field(default_factory=list)
    plugins: list[str] = Field(default_factory=list)
    user_agent: str = Field(...)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    requests_used: int = Field(default=0, ge=0)


class FuzzPattern(BaseModel):
    """Pattern for recursive URL fuzzing."""
    
    model_config = ConfigDict(frozen=True)
    
    pattern_id: str = Field(
        default_factory=lambda: str(uuid.uuid4())
    )
    base_url: str = Field(...)
    pattern_type: str = Field(..., description="numeric, date, version, etc.")
    pattern_template: str = Field(..., description="URL template with {placeholder}")
    discovered_values: list[str] = Field(default_factory=list)
    fuzzed_values: list[str] = Field(default_factory=list)
    hits: list[str] = Field(default_factory=list)
    misses: list[str] = Field(default_factory=list)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class CloudBucketTarget(BaseModel):
    """Target for cloud bucket discovery."""
    
    model_config = ConfigDict(frozen=True)
    
    target_id: str = Field(
        default_factory=lambda: str(uuid.uuid4())
    )
    brand_name: str = Field(...)
    permutations: list[str] = Field(default_factory=list)
    provider: str = Field(..., description="aws, azure, gcp")
    discovered_buckets: list[str] = Field(default_factory=list)
    public_buckets: list[str] = Field(default_factory=list)
    checked_at: datetime | None = Field(default=None)
