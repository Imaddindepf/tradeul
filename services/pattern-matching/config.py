"""
Pattern Matching Service - Configuration
"""

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service configuration"""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow"
    )
    
    # Service
    service_name: str = "pattern-matching"
    service_port: int = 8025
    debug: bool = False
    
    # Polygon Flat Files (S3)
    polygon_s3_access_key: str = ""
    polygon_s3_secret_key: str = ""
    polygon_s3_endpoint: str = "https://files.massive.com"
    polygon_s3_bucket: str = "flatfiles"
    
    # Polygon REST API (for real-time data)
    polygon_api_key: str = ""
    
    # Redis
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: Optional[str] = None
    redis_db: int = 0
    
    # PostgreSQL (for metadata storage)
    db_host: str = "timescaledb"
    db_port: int = 5432
    db_name: str = "tradeul"
    db_user: str = "tradeul_user"
    db_password: str = ""
    
    # Pattern Matching Config
    window_size: int = 45          # Default pattern window (minutes)
    future_size: int = 15          # Forecast horizon (minutes)
    step_size: int = 5             # Sliding window step (minutes)
    default_k: int = 50            # Default number of neighbors
    max_k: int = 200               # Maximum neighbors to return
    
    # FAISS Index Config
    index_type: str = "IVF4096,PQ32"  # IVF clusters + Product Quantization
    index_nprobe: int = 64            # Number of clusters to search
    use_gpu: bool = False             # Use GPU acceleration
    
    # Data Paths
    data_dir: str = "/app/data"
    index_dir: str = "/app/indexes"
    
    # Cache TTLs
    cache_ttl_realtime: int = 60      # Real-time prices cache (seconds)
    cache_ttl_forecast: int = 300     # Forecast results cache (5 min)
    
    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
    
    @property
    def database_url(self) -> str:
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"


settings = Settings()

