from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # App
    APP_NAME: str = "IDMS API"
    DEBUG: bool = False
    SECRET_KEY: str

    # Database
    DATABASE_URL: str

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Sentry (empty = disabled)
    SENTRY_DSN: str = ""

    # JWT — JWT_SECRET_KEY has no default; Pydantic will reject startup if missing
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Cloudflare R2
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET: str = ""
    R2_ENDPOINT: str = ""

    # Mistral (OCR)
    MISTRAL_API_KEY: str = ""

    # Google AI (Gemini)
    GOOGLE_AI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    AI_MAX_CONTEXT_CHUNKS: int = 10
    AI_MAX_RESPONSE_TOKENS: int = 2048

    # Embeddings
    EMBED_MODEL: str = "mistral-embed"
    EMBED_DIM: int = 1024
    EMBED_BATCH_SIZE: int = 32

    # Upload limits
    MAX_UPLOAD_BYTES: int = 52_428_800  # 50 MB
    ALLOWED_MIME_TYPES: list[str] = [
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/tiff",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]


settings = Settings()
