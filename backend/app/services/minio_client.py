"""MinIO 客户端封装：上传/下载/桶管理，所有操作经 asyncio.to_thread 避免阻塞。"""

import asyncio
from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlparse

from minio import Minio
from minio.error import S3Error

from app.core.config import settings
import structlog

logger = structlog.get_logger(__name__)


@lru_cache
def get_minio_client() -> Minio:
    """返回 Minio 单例（线程安全，由 lru_cache 缓存）。"""
    return Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


def parse_minio_url(url: str) -> tuple[str, str]:
    """解析 minio://bucket/key，返回 (bucket, key)。"""
    parsed = urlparse(url)
    if parsed.scheme != "minio":
        raise ValueError(f"Invalid scheme: {url}")
    if not parsed.netloc:
        raise ValueError(f"Missing bucket in: {url}")
    if not parsed.path or parsed.path == "/":
        raise ValueError(f"Missing key in: {url}")
    key = parsed.path.lstrip("/")
    return parsed.netloc, key


async def upload_bytes(bucket: str, key: str, data: bytes, content_type: str) -> str:
    """将字节数据上传到 MinIO，返回 minio:// URL。"""
    client = get_minio_client()

    def _upload():
        client.put_object(
            bucket_name=bucket,
            object_name=key,
            data=__import__("io").BytesIO(data),
            length=len(data),
            content_type=content_type,
        )

    await asyncio.to_thread(_upload)
    logger.debug("minio_upload_bytes", bucket=bucket, key=key, size=len(data))
    return f"minio://{bucket}/{key}"


async def upload_file(bucket: str, key: str, local_path: Path) -> str:
    """将本地文件上传到 MinIO，返回 minio:// URL。"""
    client = get_minio_client()
    file_size = local_path.stat().st_size

    def _upload():
        with open(local_path, "rb") as f:
            client.put_object(
                bucket_name=bucket,
                object_name=key,
                data=f,
                length=file_size,
                content_type="application/octet-stream",
            )

    await asyncio.to_thread(_upload)
    logger.debug("minio_upload_file", bucket=bucket, key=key, path=str(local_path))
    return f"minio://{bucket}/{key}"


async def download_to_tempfile(minio_url: str) -> Path:
    """解析 minio://bucket/key，下载到临时文件，返回 Path（调用方负责删除）。"""
    bucket, key = parse_minio_url(minio_url)
    client = get_minio_client()

    tmp = NamedTemporaryFile(delete=False, suffix=Path(key).suffix)
    tmp_path = Path(tmp.name)
    tmp.close()  # fget_object 需要关闭的 fd

    def _download():
        client.fget_object(bucket, key, str(tmp_path))

    await asyncio.to_thread(_download)
    logger.debug("minio_download", bucket=bucket, key=key, tmp=tmp_path)
    return tmp_path


async def ensure_bucket(bucket: str) -> None:
    """幂等创建桶（如果不存在则创建，不报错）。"""
    client = get_minio_client()

    def _ensure():
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
            logger.info("minio_bucket_created", bucket=bucket)
        else:
            logger.debug("minio_bucket_exists", bucket=bucket)

    await asyncio.to_thread(_ensure)
