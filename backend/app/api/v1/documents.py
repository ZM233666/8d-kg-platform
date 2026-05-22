"""Document 上传 / 查询端点。"""

import hashlib
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.document import Document
from app.schemas.api import DocumentListResponse, DocumentResponse, UploadResponse
from app.services.doc_format import INVALID_DOCX_MSG, sniff_word_format
from app.services.minio_client import upload_bytes

# ---------- upload ----------
upload_router = APIRouter(prefix="/documents", tags=["documents-upload"])
list_router = APIRouter(prefix="", tags=["documents-query"])

SYSTEM_USER_UUID = UUID("00000000-0000-0000-0000-000000000000")
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
DETECTED_MIME_BY_FMT = {
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@upload_router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> UploadResponse:
    """上传 Word 文档（.doc / .docx）到 MinIO，记录到 PG documents 表。"""
    data = await file.read()

    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(413, "File too large (max 50MB)")

    fmt = sniff_word_format(data)
    if fmt not in ("docx", "doc"):
        raise HTTPException(415, INVALID_DOCX_MSG)
    normalized_content_type = DETECTED_MIME_BY_FMT[fmt]

    sha256 = hashlib.sha256(data).hexdigest()

    # sha256 去重
    stmt = select(Document).where(Document.sha256 == sha256)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing is not None:
        return UploadResponse(
            document=DocumentResponse.model_validate(existing),
            already_exists=True,
        )

    # 不命中：上传 MinIO
    document_id = uuid4()
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    object_key = f"uploads/{today}/{document_id}/{file.filename}"
    await upload_bytes("kg-documents", object_key, data, normalized_content_type)
    minio_url = f"minio://kg-documents/{object_key}"

    doc = Document(
        id=document_id,
        file_name=file.filename,
        file_size=len(data),
        mime_type=normalized_content_type,
        sha256=sha256,
        minio_key=minio_url,
        upload_user_id=SYSTEM_USER_UUID,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    return UploadResponse(
        document=DocumentResponse.model_validate(doc),
        already_exists=False,
    )


# ---------- query ----------
@list_router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """根据 document_id 查询单个文档。"""
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(404, "document not found")
    return DocumentResponse.model_validate(doc)


@list_router.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """删除文档（硬删除）。"""
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(404, "document not found")
    await db.delete(doc)
    await db.commit()


@list_router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> DocumentListResponse:
    """分页查询文档列表。"""
    total_result = await db.execute(select(func.count()).select_from(Document))
    total = total_result.scalar_one()

    items_result = await db.execute(
        select(Document)
        .order_by(Document.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    items = [DocumentResponse.model_validate(doc) for doc in items_result.scalars().all()]

    return DocumentListResponse(items=items, total=total, offset=offset, limit=limit)
