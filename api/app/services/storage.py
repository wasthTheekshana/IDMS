"""Cloudflare R2 storage service (S3-compatible API)."""

import hashlib
import uuid

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]

from app.core.config import settings

_PRESIGN_EXPIRY = 900  # 15 minutes


def _client():  # type: ignore[no-untyped-def]
    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def make_r2_key(org_id: uuid.UUID, doc_id: uuid.UUID, filename: str) -> str:
    safe = filename.replace("/", "_").replace("..", "_")
    return f"orgs/{org_id}/docs/{doc_id}/{safe}"


def presign_upload(r2_key: str, content_type: str) -> str:
    """Return a presigned PUT URL for direct client upload to R2."""
    client = _client()
    return client.generate_presigned_url(  # type: ignore[no-any-return]
        "put_object",
        Params={
            "Bucket": settings.R2_BUCKET,
            "Key": r2_key,
            "ContentType": content_type,
        },
        ExpiresIn=_PRESIGN_EXPIRY,
    )


def object_exists(r2_key: str) -> bool:
    client = _client()
    try:
        client.head_object(Bucket=settings.R2_BUCKET, Key=r2_key)
        return True
    except Exception:
        return False


def get_object_bytes(r2_key: str) -> bytes:
    client = _client()
    response = client.get_object(Bucket=settings.R2_BUCKET, Key=r2_key)
    return response["Body"].read()  # type: ignore[no-any-return]


def sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def delete_objects(r2_keys: list[str]) -> None:
    if not r2_keys:
        return
    client = _client()
    objects = [{"Key": k} for k in r2_keys]
    client.delete_objects(
        Bucket=settings.R2_BUCKET, Delete={"Objects": objects, "Quiet": True}
    )


def presign_download(r2_key: str) -> str:
    client = _client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.R2_BUCKET, "Key": r2_key},
        ExpiresIn=_PRESIGN_EXPIRY,
    )
