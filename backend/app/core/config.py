from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.models import DEFAULT_BAILIAN_MODEL


class Settings(BaseSettings):
    app_name: str = "Short Drama Agent"
    dashscope_api_key: str | None = None
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    bailian_model: str = DEFAULT_BAILIAN_MODEL
    embedding_provider: str = "dashscope"
    bailian_embedding_model: str = "text-embedding-v4"
    local_embedding_model: str = "BAAI/bge-m3"
    local_embedding_device: str = "auto"
    local_embedding_cache_dir: str | None = None
    bailian_timeout_seconds: float = 60.0
    bailian_max_tokens: int = 1600
    database_url: str = "postgresql+psycopg://drama:drama@localhost:5432/short_drama_agent"
    database_connect_timeout_seconds: int = 3
    storage_backend: str = "auto"
    enable_vector_memory: bool = True
    embedding_dimension: int = 1024
    vector_memory_top_k: int = 6
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    use_mock_llm: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8-sig")


settings = Settings()
