"""Pipeline 上下文数据契约（SCHEMA.md §11 Pipeline 输出）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.entity import Chunk
from app.schemas.extraction import ExtractionResult


class StageMetric(BaseModel):
    """单个 stage 的执行指标。"""

    model_config = ConfigDict(extra="forbid")

    stage_name: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: float | None = None
    ok: bool = False
    error: str | None = None
    output_summary: dict[str, Any] = Field(default_factory=dict)


class PipelineContext(BaseModel):
    """Pipeline 全程共享的可变上下文。

    每个 stage 接收 ctx → 修改 → 返回新 ctx。
    模型允许字段在 stage 间累加（extra="allow"）。
    """

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    # ─── 输入参数 ───
    document_id: UUID = Field(..., description="PG documents.id")
    minio_key: str = Field(..., description="MinIO 对象 key")
    report_id_hint: str | None = Field(None, description="用户提供的 report_id 候选")
    pipeline_version: str = "v0.1.0"
    extraction_run_id: UUID | None = Field(None, description="PG extraction_runs.id，s6 写入时用")

    # ─── s1 Reader 产出 ───
    raw_text: str = ""
    raw_tables: list[dict] = Field(default_factory=list, description="原始表格 JSON，待 s3 解析")
    raw_images: list[dict] = Field(default_factory=list, description="图片占位符列表")

    # ─── s2 Splitter 产出 ───
    chunks: list[Chunk] = Field(default_factory=list)

    # ─── s3 TableExtractor 产出 ───
    parsed_tables: dict[str, list[dict]] = Field(
        default_factory=dict,
        description="key=table_type，值为解析后的行 dict 列表",
    )

    # ─── s4 LLM Extractor 产出 ───
    extraction_result: ExtractionResult | None = None

    # ─── 全程统计 ───
    stage_metrics: list[StageMetric] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    # ─── helpers ───
    def add_metric(self, metric: StageMetric) -> None:
        self.stage_metrics.append(metric)

    def add_error(self, stage_name: str, msg: str) -> None:
        self.errors.append(f"[{stage_name}] {msg}")

    @property
    def report_id(self) -> str:
        """优先用 extraction_result.report_id，否则回退 hint。"""
        if self.extraction_result is not None:
            return self.extraction_result.report_id
        return self.report_id_hint or str(self.document_id)
