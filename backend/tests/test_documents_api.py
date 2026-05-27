"""documents 上传接口测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.api.deps import get_db
from app.api.v1.documents import upload_router
from app.models.enums import DocumentStatus
from fastapi import FastAPI
from fastapi.testclient import TestClient

_DOC_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 512


class _ScalarResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class _FakeSession:
    def __init__(self) -> None:
        self.added = None

    async def execute(self, _stmt: Any) -> _ScalarResult:
        return _ScalarResult(None)

    def add(self, obj: Any) -> None:
        self.added = obj

    async def commit(self) -> None:
        return None

    async def refresh(self, obj: Any) -> None:
        if getattr(obj, "status", None) is None:
            obj.status = DocumentStatus.UPLOADED.value
        now = datetime.now(UTC)
        if getattr(obj, "created_at", None) is None:
            obj.created_at = now
        if getattr(obj, "updated_at", None) is None:
            obj.updated_at = now


def _build_test_client(fake_db: _FakeSession) -> TestClient:
    app = FastAPI()
    app.include_router(upload_router, prefix="/api/v1")

    async def _override_get_db():
        yield fake_db

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


def test_upload_accepts_legacy_doc_with_octet_stream(monkeypatch) -> None:
    fake_db = _FakeSession()

    async def _fake_upload_bytes(bucket: str, key: str, data: bytes, content_type: str) -> str:
        assert bucket == "kg-documents"
        assert key.endswith(".doc")
        assert data == _DOC_MAGIC
        assert content_type == "application/msword"
        return f"minio://{bucket}/{key}"

    monkeypatch.setattr("app.api.v1.documents.upload_bytes", _fake_upload_bytes)

    with _build_test_client(fake_db) as client:
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("legacy.doc", _DOC_MAGIC, "application/octet-stream")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["already_exists"] is False
    assert body["document"]["file_name"] == "legacy.doc"
    assert body["document"]["mime_type"] == "application/msword"
    assert fake_db.added is not None
    assert fake_db.added.mime_type == "application/msword"


def test_upload_rejects_non_word_file_even_if_named_doc(monkeypatch) -> None:
    fake_db = _FakeSession()

    async def _fake_upload_bytes(*_args, **_kwargs) -> str:  # pragma: no cover - defensive
        raise AssertionError("upload_bytes should not be called for invalid files")

    monkeypatch.setattr("app.api.v1.documents.upload_bytes", _fake_upload_bytes)

    with _build_test_client(fake_db) as client:
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("fake.doc", b"not-a-word-file", "application/octet-stream")},
        )

    assert response.status_code == 415
    assert "Word" in response.json()["detail"]
