def test_settings_app_name() -> None:
    from app.core.config import settings

    assert settings.APP_NAME == "IDMS API"


def test_settings_database_url_is_async() -> None:
    from app.core.config import settings

    assert settings.DATABASE_URL.startswith("postgresql+asyncpg://")


def test_settings_redis_url() -> None:
    from app.core.config import settings

    assert settings.REDIS_URL.startswith("redis://")


def test_settings_secret_key_present() -> None:
    from app.core.config import settings

    assert len(settings.SECRET_KEY) >= 8
