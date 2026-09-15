from app.core.security import (
    admin_refresh_token_redis_key,
    create_platform_admin_token,
    decode_access_token,
)


def test_create_platform_admin_token_carries_account_type() -> None:
    token = create_platform_admin_token("11111111-1111-1111-1111-111111111111")
    payload = decode_access_token(token)
    assert payload["sub"] == "11111111-1111-1111-1111-111111111111"
    assert payload["account_type"] == "platform_admin"
    assert payload["type"] == "access"
    assert "org_id" not in payload
    assert "role" not in payload


def test_admin_refresh_token_redis_key_is_namespaced_separately() -> None:
    key = admin_refresh_token_redis_key("abc-123")
    assert key == "admin_refresh:abc-123"
