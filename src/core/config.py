from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    PROJECT_NAME: str = "AETHER-MINE"
    VERSION: str = "0.1.0"
    
    # Storage
    PARQUET_OUTPUT_DIR: str = "/workspace/data/parquet"
    QUARANTINE_DIR: str = "/workspace/data/quarantine"
    DUCKDB_PATH: str = "/workspace/data/index.duckdb"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Proxies (Comma separated or json list)
    PROXY_LIST: str = "" 
    
    # Rate Limiting
    REQUESTS_PER_MINUTE: int = 60
    
    # Concurrency
    MAX_WORKERS: int = 10

settings = Settings()
