"""v0.2 KGtestV2 精简版实体定义（8 个 EntityType + 治理层）。

设计原则：
- 所有实体继承 BaseNode（保留治理字段）
- ProductEvent 继承 BaseEvent
- 字段命名 snake_case
- 只有 business_key 主键字段必填，其余业务字段均可选（LLM 抽不到就为 None）
"""

from __future__ import annotations

from datetime import datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.schemas.base import BaseEvent, BaseNode

# =============================================================================
# 核心实体（每份 8D 报告至少 1 个）
# =============================================================================


class EightDReport(BaseNode):
    """8D 报告。business_key 约定填充 report_no。"""

    report_no: str = Field(..., description="8D 编号，对应 business_key")
    issue_title: str | None = Field(None, description="问题标题")
    report_date: datetime | None = Field(None, description="报告日期")
    closed_at: datetime | None = Field(None, description="报告关闭时间；原文未明确则为空")
    report_status: str | None = Field(None, description="报告状态：草稿/进行中/关闭")
    d2_problem_statement: str | None = Field(None, description="D2 问题描述")
    d4_root_cause_summary: str | None = Field(None, description="D4 根因分析摘要")
    d5_permanent_correction_summary: str | None = Field(None, description="D5 永久纠正摘要")
    d7_prevention_summary: str | None = Field(None, description="D7 防再发摘要")
    owner_name: str | None = Field(None, description="负责人姓名")
    owner_role: str | None = Field(None, description="负责人角色")


class ProductEvent(BaseEvent):
    """产品事件。business_key 约定填充 event_id（代码生成 EVT-{report_no}）。"""

    event_id: str = Field(..., description="事件 ID，对应 business_key")
    event_code: str | None = Field(None, description="客户系统的事件编码")
    event_type: str | None = Field(None, description="故障/异常/客诉/试验")
    severity: str | None = Field(None, description="严重级别")
    symptom: str | None = Field(None, description="现象描述")
    occurred_at: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("occurred_at", "event_time"),
        description="事件发生时间",
    )
    status: str | None = Field(None, description="处理状态")
    reporter_name: str | None = Field(None, description="上报人姓名")


class FailureMode(BaseNode):
    """失效模式。business_key 约定填充 mode_code。"""

    mode_code: str = Field(..., description="失效模式编码，对应 business_key")
    mode_name: str | None = Field(None, description="LLM 抽取的原始失效描述")
    category: str | None = Field(None, description="失效大类：机械/电气/软件/工艺")


class CauseItem(BaseNode):
    """原因项。business_key 约定填充 cause_id（代码生成 CAU-{report_no}-{idx}）。"""

    cause_id: str = Field(..., description="原因 ID，对应 business_key")
    title: str | None = Field(None, description="原因标题")
    cause_type: str | None = Field(None, description="原因类型：根本原因/中间原因/直接原因")
    is_verified: bool | None = Field(None, description="是否已验证")
    evidence: str | None = Field(None, description="证据描述")


class ActionItem(BaseNode):
    """措施项。business_key 约定填充 action_id（代码生成 ACT-{report_no}-{idx}）。"""

    action_id: str = Field(..., description="措施 ID，对应 business_key")
    title: str | None = Field(None, description="措施标题")
    action_type: str | None = Field(None, description="措施类型：临时D3/纠正D5/预防D7/根因分析D4")
    status: str | None = Field(None, description="状态：计划中/进行中/完成")
    owner_name: str | None = Field(None, description="负责人姓名")
    due_date: datetime | None = Field(None, description="计划完成日期")
    completed_at: datetime | None = Field(None, description="实际完成时间；原文未明确则为空")


# =============================================================================
# 可选实体（LLM 抽不出来时不创建）
# =============================================================================


class ProductInstance(BaseNode):
    """产品实例。business_key 约定填充 serial_number。"""

    serial_number: str = Field(..., description="产品序列号，对应 business_key")
    asset_code: str | None = None
    commission_date: datetime | None = Field(None, description="投运日期")
    status: str | None = None
    owner_name: str | None = Field(None, description="所属客户名称")
    site_city: str | None = None
    site_country: str | None = None
    site_code: str | None = None


class PartSerial(BaseNode):
    """部件序列件。business_key 约定填充 part_key。"""

    part_key: str = Field(..., description="拼接键，对应 business_key")
    serial_number: str | None = None
    batch_no: str | None = None
    status: str | None = None
    supplier_name: str | None = None


class Organization(BaseNode):
    """组织机构。business_key 约定填充 org_code。"""

    org_code: str = Field(..., description="组织编码，对应 business_key")
    org_name: str | None = Field(None, description="组织名称")
    org_type: str | None = Field(None, description="制造商/供应商/客户/运营商/部门/项目组")


class Person(BaseNode):
    """人员。business_key 约定填充 person_id（通常为报告内局部键）。"""

    person_id: str = Field(..., description="人员 ID，对应 business_key")
    person_name: str | None = Field(None, description="人员姓名或带称谓的人名")
    title: str | None = Field(None, description="岗位/称谓")
    department: str | None = Field(None, description="部门/职能")
    email: str | None = Field(None, description="邮件地址")


class FailureProduct(BaseNode):
    """失效产品规范节点（跨报告归一）。"""

    canonical_name: str = Field(..., description="规范化产品名")
    family_code: str | None = Field(None, description="产品族编码（如 EP2002）")
    KBPartName: str | None = Field(None, description="代表性部件名称")
    KBPartNumber: str | None = Field(None, description="代表性部件号")
    aliases: list[str] = Field(default_factory=list, description="别名集合")
    kb_part_numbers: list[str] = Field(default_factory=list, description="观测到的部件号集合")


class FailureProductMention(BaseNode):
    """报告内失效产品提及节点（保留原文事实）。"""

    failure_product_key: str | None = Field(None, description="关联 FailureProduct.business_key")
    report_no: str | None = Field(None, description="所属报告号")
    KBPartName: str | None = Field(None, description="原文部件名称")
    KBPartNumber: str | None = Field(None, description="原文部件号")
    Amount: str | None = Field(None, description="原文数量（如 5 pcs / 4pcs）")
    amount_value: float | None = Field(None, description="归一化数量值")
    amount_unit: str | None = Field(None, description="归一化数量单位")


# =============================================================================
# 治理实体
# =============================================================================


class Chunk(BaseModel):
    """文档分块。治理实体，字段沿用 v1 命名以保持 s2_split 与 pg_writer 兼容。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    chunk_id: str = Field(
        ..., description="对应 business_key，格式 {report_id}#{section}#{para_idx}"
    )
    report_id: str = Field(..., description="所属报告 ID（业务键，等于 EightDReport.report_no）")
    section_path: list[str] = Field(default_factory=list)
    para_idx: int = Field(..., description="段落索引")
    chunk_role: str | None = Field(None, description="action/conclusion/finding/measurement/etc.")
    text: str = Field(..., description="段落文本")
    token_count: int = Field(0, description="tiktoken cl100k_base 计数")
    is_table: bool = False
    is_placeholder: bool = False
    table_type: str | None = None
    has_referenced_image: bool = False
    created_at: datetime | None = None
