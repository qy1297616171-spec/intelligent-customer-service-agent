from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8080
    log_level: str = "INFO"
    database_url: str = "sqlite:///./data/customer_service.db"
    redis_enabled: bool = False
    redis_url: str = "redis://localhost:6379/0"
    rate_limit_enabled: bool = True
    rate_limit_requests_per_minute: int = 120
    login_rate_limit_per_minute: int = 10
    auth_enabled: bool = False
    auth_jwt_secret: str = ""
    auth_access_token_minutes: int = 480
    auth_cookie_secure: bool = False
    auth_bootstrap_tenant_name: str = "星选商城"
    auth_bootstrap_admin_email: str = ""
    auth_bootstrap_admin_password: str = ""
    auth_bootstrap_admin_name: str = "系统管理员"

    feature_knowledge: bool = True
    feature_conversation: bool = True
    feature_commerce: bool = True
    feature_handoff: bool = True
    feature_analytics: bool = True
    feature_customer: bool = True
    feature_auth: bool = True
    feature_audit: bool = True

    ai_min_evidence_score: float = 0.18
    ai_cache_ttl_seconds: int = 300
    ai_model_provider: str = "mock"
    ai_model_base_url: str = "https://api.deepseek.com"
    ai_model_api_key: str = ""
    ai_model_name: str = "deepseek-v4-flash"
    ai_model_timeout_seconds: float = 12.0
    ai_model_temperature: float = 0.0
    ai_model_max_tokens: int = 600
    ai_model_fallback_enabled: bool = True
    embedding_dimensions: int = 256
    embedding_provider: str = "hash"
    embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-v4"
    embedding_timeout_seconds: float = 10.0
    retrieval_vector_weight: float = 0.55
    retrieval_keyword_weight: float = 0.45
    vector_store_provider: str = "auto"
    pgvector_dimensions: int = 256
    rerank_provider: str = "heuristic"
    rerank_base_url: str = "https://dashscope.aliyuncs.com/compatible-api/v1"
    rerank_api_key: str = ""
    rerank_model: str = "qwen3-rerank"
    rerank_timeout_seconds: float = 8.0
    rerank_candidate_limit: int = 20
    rerank_top_n: int = 5
    oms_provider: str = "memory"
    oms_base_url: str = "http://mock-oms:8090"
    oms_api_key: str = ""
    oms_timeout_seconds: float = 3.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
