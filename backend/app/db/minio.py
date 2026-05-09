"""MinIO 同步客户端（minio SDK 无原生 async）。"""

import asyncio

from minio import Minio

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_minio_client: Minio | None = None


def get_minio_client() -> Minio:
    """获取全局 MinIO 同步 client。"""
    global _minio_client
    if _minio_client is None:
        _minio_client = Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
    return _minio_client


def ensure_minio_bucket() -> None:
    """确保 bucket 存在，不存在则创建（同步调用）。"""
    client = get_minio_client()
    bucket = settings.minio_bucket
    try:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
            log.info("minio_bucket_created", bucket=bucket)
        else:
            log.info("minio_bucket_exists", bucket=bucket)
    except Exception as e:
        log.error("minio_bucket_check_failed", bucket=bucket, error=str(e))
        raise


async def ping_minio() -> bool:
    """检查 MinIO 连通性（同步调用用 asyncio.to_thread 包装）。"""
    try:
        client = get_minio_client()
        bucket = settings.minio_bucket
        exists = await asyncio.to_thread(client.bucket_exists, bucket)
        if not exists:
            await asyncio.to_thread(client.make_bucket, bucket)
        return True
    except Exception as e:
        log.error("minio_ping_failed", error=str(e))
        return False


# 供 deps.py 直接引用
minio_client = get_minio_client()
