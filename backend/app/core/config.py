"""应用配置：所有环境变量通过 Pydantic Settings 集中读取。"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根 .env 绝对路径
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"
assert _ENV_FILE.exists(), f"Missing .env at {_ENV_FILE}"


class PipelineSettings(BaseSettings):
    """Pipeline 各阶段配置（通过 PIPELINE_* 前缀注入）。

    注意：.env 中通过 PIPELINE_XXX 覆盖，如 PIPELINE_LLM_MODEL_DEFAULT。
    """

    pipeline_version: str = "pipeline-v0.1.0"
    schema_version: str = "v0.1.0"
    max_file_size_mb: int = 50
    enable_ocr: bool = False
    section_dict_path: str = "backend/app/pipeline/section_dict.yaml"
    chunk_max_tokens: int = 1500
    table_match_threshold: int = 70
    llm_model_default: str = "claude-haiku-4-5"
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 3
    llm_max_prompt_tokens: int = 8000
    domain_lexicon_path: str = "backend/app/lexicon/domain_lexicon.yaml"
    enable_vectorizer: bool = False
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024
    writer_batch_size: int = 100
    enforce_concept_existence: bool = True

    model_config = SettingsConfigDict(env_prefix="PIPELINE_")


class Settings(BaseSettings):
    """全局配置，从 .env 读取。"""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # === PostgreSQL（工具字段，URL 直接从 .env 读取）===
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "postgres"

    # === URL（直接从 .env 读取，不做拼接）===
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"
    alembic_database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/postgres"

    # === Neo4j ===
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "neo4j"
    neo4j_database: str = "neo4j"

    # === Redis（工具字段，URL 直接从 .env 读取）===
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""

    redis_url: str = "redis://localhost:6379/0"

    # === Celery ===
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # === MinIO ===
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "kg-documents"
    minio_secure: bool = False

    # === LLM ===
    llm_provider: str = "codex"  # mock | codex | litellm
    llm_fallback_provider: str | None = None
    llm_primary_soft_timeout_seconds: int | None = 30

    # === Codex Extractor Service ===
    codex_base_url: str = "http://127.0.0.1:8787"
    codex_extract_path: str = "/extract"
    codex_timeout_seconds: int = 120
    codex_max_retries: int = 2
    codex_skill_name: str = "8d-report-extraction-core"
    codex_skill_version: str = "draft"
    codex_executor_label: str = "codex-local"
    codex_cli_path: str = "codex"
    codex_exec_workdir: str = ""
    codex_exec_model: str | None = None

    # === LiteLLM (OpenAI-compatible; Azure model gateway) ===
    litellm_api_key: str = ""
    litellm_base_url: str = "http://117.62.232.51:14000/v1"
    litellm_model: str = "gpt-5.4"
    litellm_timeout_seconds: int = 60
    litellm_max_retries: int = 3

    # === JWT / Auth ===
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # === CORS ===
    cors_origins_raw: str = (
        "http://localhost:5172,http://127.0.0.1:5172,http://localhost:5173,http://127.0.0.1:5173"
    )

    @property
    def cors_allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins_raw.split(",") if o.strip()]

    # === Pipeline ===
    pipeline: PipelineSettings = Field(default_factory=PipelineSettings)

    # === 杂项 ===
    debug: bool = False
    log_level: str = "INFO"
    strict_startup: bool = False


settings = Settings()
