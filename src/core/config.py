"""Configuration management for AETHER-MINE using Pydantic v2 Settings."""

from pathlib import Path
from typing import Literal
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global configuration settings for AETHER-MINE."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="AETHER_",
        case_sensitive=False,
    )
    
    # Application Settings
    app_name: str = "AETHER-MINE"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    
    # Data Paths
    data_dir: Path = Field(default=Path("data"))
    parquet_dir: Path = Field(default=Path("data/parquet"))
    quarantine_dir: Path = Field(default=Path("data/quarantine"))
    index_dir: Path = Field(default=Path("data/index"))
    logs_dir: Path = Field(default=Path("logs"))
    
    # Batch Settings
    batch_max_records: int = Field(default=1000, ge=1, le=10000)
    batch_max_size_mb: int = Field(default=50, ge=1, le=500)
    batch_flush_interval_seconds: int = Field(default=60, ge=10)
    
    # Redis Settings
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None
    
    # Celery Settings
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    celery_task_default_queue: str = "aether_mine"
    
    # Proxy Settings
    proxy_pool_size: int = Field(default=10, ge=1)
    proxy_rotation_threshold: int = Field(default=50, ge=1)
    proxy_burn_timeout_hours: int = Field(default=24, ge=1)
    proxy_max_failures: int = Field(default=3, ge=1)
    
    # Browser Settings
    browser_headless: bool = True
    browser_timeout_ms: int = Field(default=30000, ge=5000)
    fingerprint_rotation_requests: int = Field(default=50, ge=10)
    
    # API Rate Limiting
    rate_limit_requests_per_minute: int = Field(default=60, ge=1)
    rate_limit_burst: int = Field(default=10, ge=1)
    
    # Stealth Settings
    human_delay_min_ms: int = Field(default=500, ge=100)
    human_delay_max_ms: int = Field(default=3000, ge=500)
    behavioral_noise_enabled: bool = True
    
    # Cloud Bucket Settings
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_region: str = "us-east-1"
    azure_connection_string: str | None = None
    gcp_credentials_path: str | None = None
    
    # LLM Settings
    llm_provider: Literal["openai", "ollama", "local"] = "ollama"
    openai_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    
    # Vector Database
    vector_db_path: Path = Field(default=Path("data/chromadb"))
    embedding_model: str = "all-MiniLM-L6-v2"
    
    # DuckDB Settings
    duckdb_path: Path = Field(default=Path("data/index/metadata.duckdb"))
    duckdb_memory_limit: str = "4GB"
    
    @field_validator("data_dir", "parquet_dir", "quarantine_dir", "index_dir", "logs_dir", mode="after")
    @classmethod
    def ensure_dir_exists(cls, v: Path) -> Path:
        """Ensure directory exists."""
        v.mkdir(parents=True, exist_ok=True)
        return v
    
    @property
    def redis_url(self) -> str:
        """Construct Redis URL."""
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
