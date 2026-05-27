"""Entity / Event / Auxiliary 类型全量定义。

严格按 SCHEMA.md §3/§4/§6 字段名，不得改名、不得补字段、不得删字段。
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import BaseEvent, BaseNode

# ──────────────────────────────────────────────────────────────
# 枚举统一定义
# ──────────────────────────────────────────────────────────────

ClosureStatus = Literal[
    "open",
    "closed",
    "partially_closed",
    "root_cause_unidentified",
]

ActionType = Literal["containment", "corrective", "preventive"]

ResponsibleParty = Literal["KB", "Supplier", "Customer", "Operator", "Other"]

ActionStatus = Literal["planned", "in_progress", "verified", "closed", "tbd"]

VerificationResult = Literal["passed", "failed", "inconclusive", "tbd"]

JudgementResult = Literal["pass", "fail", "marginal", "inconclusive", "n/a"]

Polarity = Literal["positive", "negative", "neutral"]

EvidenceSource = Literal[
    "internal_inspection",
    "third_party_lab",
    "customer_report",
    "field_observation",
    "simulation",
    "experiment",
]

EvidenceStrength = Literal["direct", "indirect", "ruled_out"]

SafetyImpact = Literal["none", "minor", "moderate", "major", "critical"]

OperationalImpact = Literal["none", "minor", "moderate", "major", "stoppage"]

ChunkRole = Literal[
    "metadata",
    "background",
    "evidence",
    "hypothesis",
    "conclusion",
    "action",
    "unknown",
]


# ──────────────────────────────────────────────────────────────
# 核心层 EntityType（§3）
# ──────────────────────────────────────────────────────────────


class EightDReport(BaseNode):
    """8D 报告主体。业务键：report_id。"""

    report_id: str = Field(..., description="业务键，来自质量通知号或文件 hash")
    title: str = Field(..., description="报告标题")
    quality_notification_no: str | None = Field(None, description="质量通知号")
    closure_status: ClosureStatus = Field(..., description="闭环状态")
    report_date: datetime | None = Field(None, description="报告日期")
    report_version: str | None = Field(None, description="报告版本，如 '00-zh'/'1.0'")
    customer_complaint_no: str | None = Field(None, description="客户投诉号")
    field_completeness: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="字段完整度，识别到占位符则降低",
    )

    model_config = ConfigDict(from_attributes=True)


class Project(BaseNode):
    """项目。业务键：project_no。"""

    project_no: str = Field(..., description="项目编号")
    name: str = Field(..., description="项目名称")
    line_name: str | None = Field(None, description="线路名，如 '兰州2号线'")
    system: str | None = Field(None, description="系统，如 '制动控制系统'")

    model_config = ConfigDict(from_attributes=True)


class Customer(BaseNode):
    """客户。业务键：name。"""

    name: str = Field(..., description="客户名称")
    short_name: str | None = Field(None, description="简称")

    model_config = ConfigDict(from_attributes=True)


class Operator(BaseNode):
    """运营方。业务键：name。"""

    name: str = Field(..., description="运营方名称")
    region: str | None = Field(None, description="区域")

    model_config = ConfigDict(from_attributes=True)


class Part(BaseNode):
    """部件（v0.1 简化版，不拆分 Type/Instance）。业务键：part_no。"""

    part_no: str = Field(..., description="克诺尔部件号，如 'G7029/SMF01'")
    part_name: str = Field(..., description="中文名，如 'EP2002阀'")
    serial_numbers: list[str] = Field(
        default_factory=list, description="v0.1 临时序列号列表；v0.2 拆分为 PartInstance"
    )
    batch_numbers: list[str] = Field(default_factory=list, description="批次号列表")
    parent_part_no: str | None = Field(None, description="父部件号")
    operating_mileage_km: float | None = Field(None, description="操作里程（km）")
    quantity_affected: int | None = Field(None, description="受影响数量")

    model_config = ConfigDict(from_attributes=True)


class Material(BaseNode):
    """材料。业务键：material_grade。"""

    material_grade: str = Field(..., description="材料牌号，如 'X10CrNi18-8'")
    material_type: str | None = Field(None, description="材料类型，如 '不锈钢'")
    standards: list[str] = Field(default_factory=list, description="执行标准号列表")

    model_config = ConfigDict(from_attributes=True)


class Standard(BaseNode):
    """标准/规范。业务键：standard_no。"""

    standard_no: str = Field(..., description="标准号，如 'EN 10270-3:2011'")
    standard_name: str | None = Field(None, description="标准名称")
    issuing_body: str | None = Field(None, description="发布机构，如 'EN'/'GB'/'DIN'")

    model_config = ConfigDict(from_attributes=True)


class TestMethod(BaseNode):
    """检测方法。业务键：method_name（受控词表）。"""

    method_name: str = Field(..., description="方法名称，如 '断口分析'/'硬度试验'/'X-ray'")
    method_category: str | None = Field(None, description="方法类别，如 '金相'/'化学'/'无损'")
    standard_ref: str | None = Field(None, description="引用的标准号")

    model_config = ConfigDict(from_attributes=True)


class Process(BaseNode):
    """工艺/工序（SCHEMA.md §3.11）。业务键：name。"""

    name: str = Field(..., description="工序名，如 '热处理'")
    process_type: str | None = Field(None, description="工序类型")

    model_config = ConfigDict(from_attributes=True)


class Equipment(BaseNode):
    """设备（SCHEMA.md §3.11）。业务键：name。"""

    name: str = Field(..., description="设备名")
    model: str | None = Field(None, description="设备型号")

    model_config = ConfigDict(from_attributes=True)


# ──────────────────────────────────────────────────────────────
# 次要层 EntityType（§3，仅 BaseNode + 业务键，TODO: v0.2 补充字段）
# ──────────────────────────────────────────────────────────────


class Vehicle(BaseNode):
    """车辆。业务键：vehicle_no + project_no（复合键）。"""

    vehicle_no: str = Field(..., description="车辆编号，如 'T030'")
    project_no: str = Field(..., description="所属项目编号")
    vehicle_type: str | None = Field(None, description="车型")
    # TODO: v0.2 补充字段


class Laboratory(BaseNode):
    """第三方检测机构。业务键：name。"""

    name: str = Field(..., description="实验室名称")
    is_third_party: bool = Field(default=True, description="是否第三方")
    accreditation: str | None = Field(None, description="认证信息")
    # TODO: v0.2 补充字段


class Person(BaseNode):
    """人员。业务键：email。"""

    name: str = Field(..., description="姓名")
    email: str = Field(..., description="邮箱（业务键）")
    department: str | None = Field(None, description="部门")
    role: str | None = Field(None, description="角色，如 '项目质量工程师'")
    phone: str | None = Field(None, description="电话")
    # TODO: v0.2 补充字段


class Team(BaseNode):
    """团队。业务键：name。"""

    name: str = Field(..., description="团队名称")
    team_type: str | None = Field(None, description="团队类型，如 '8D 问题解决团队'")
    # TODO: v0.2 补充字段


class Supplier(BaseNode):
    """供应商。业务键：name。"""

    name: str = Field(..., description="供应商名称")
    region: str | None = Field(None, description="地区")
    # TODO: v0.2 补充字段


# ──────────────────────────────────────────────────────────────
# 核心层 EventType（§4）
# ──────────────────────────────────────────────────────────────


class DefectOccurrence(BaseEvent):
    """故障发生事件。业务键：report_id + vehicle_no + occurred_at。"""

    report_id: str = Field(..., description="所属报告 ID")
    defect_description: str = Field(..., description="故障描述")
    defect_location: str | None = Field(None, description="故障位置，如 '靠近端部'")
    serial_no: str | None = Field(None, description="出问题的具体序列号")
    operating_mileage_km: float | None = Field(None, description="故障发生时里程（km）")
    detection_context: str | None = Field(None, description="检测场景，如 '首次自检'/'日检'")
    is_first_occurrence: bool | None = Field(None, description="是否首次发生")

    model_config = ConfigDict(from_attributes=True)


class InspectionEvent(BaseEvent):
    """检测事件。业务键：UUID。"""

    inspection_name: str = Field(..., description="检测名称，如 '断口分析'")
    sample_id: str | None = Field(None, description="样本 ID")
    is_third_party: bool = Field(default=False, description="是否第三方检测")
    laboratory_name: str | None = Field(None, description="实验室名称")
    conclusion_text: str | None = Field(None, description="结论文本")

    model_config = ConfigDict(from_attributes=True)


class Experiment(BaseEvent):
    """验证型实验。业务键：UUID。"""

    experiment_name: str = Field(..., description="实验名称，如 '对比实验'/'加速老化试验'")
    hypothesis: str = Field(..., description="假设描述")
    method_description: str = Field(..., description="实验方法描述")
    control_group: str | None = Field(None, description="对照组描述")
    test_group: str | None = Field(None, description="实验组描述")
    conclusion: str = Field(..., description="实验结论")
    cycle_count: int | None = Field(None, description="循环次数，如疲劳试验 700 万次")

    model_config = ConfigDict(from_attributes=True)


class ActionEvent(BaseEvent):
    """统一 Action 事件，通过 action_type 区分 D3/D5/D6/D7。业务键：UUID。"""

    action_type: ActionType = Field(..., description="行动类型：containment/corrective/preventive")
    action_description: str = Field(..., description="行动描述")
    responsible_party: ResponsibleParty = Field(..., description="责任方")
    responsible_person: str | None = Field(None, description="责任人")
    deadline: datetime | None = Field(None, description="截止日期")
    status: ActionStatus = Field(default="planned", description="执行状态")
    verification_result: str | None = Field(None, description="验证结果")

    model_config = ConfigDict(from_attributes=True)


class VerificationEvent(BaseEvent):
    """验证事件。业务键：UUID。"""

    verification_method: str = Field(..., description="验证方法")
    verification_result: VerificationResult = Field(..., description="验证结果")
    verified_action_id: UUID = Field(..., description="被验证的 ActionEvent ID")

    model_config = ConfigDict(from_attributes=True)


class ClosureEvent(BaseEvent):
    """报告关闭事件。业务键：UUID。"""

    closure_decision: str = Field(..., description="关闭决策")
    final_meeting_date: datetime | None = Field(None, description="最终会议日期")
    attendees: list[str] = Field(default_factory=list, description="出席人员列表")

    model_config = ConfigDict(from_attributes=True)


# ──────────────────────────────────────────────────────────────
# 辅助类型（§6）
# ──────────────────────────────────────────────────────────────


class Measurement(BaseNode):
    """测量值（三元组扩展）。业务键：inspection_event_id + quantity + sample_id。"""

    inspection_event_id: str = Field(..., description="所属检测事件 ID")
    quantity: str = Field(..., description="测量量名称，如 '硬度 HV10'/'二级调节器压力'")
    target_value: float | None = Field(None, description="设定值")
    tolerance_upper: float | None = Field(None, description="上限公差")
    tolerance_lower: float | None = Field(None, description="下限公差")
    actual_value: float | str = Field(..., description="实测值，数值或文本如 '700万次'")
    unit: str | None = Field(None, description="单位，如 'bar'/'HV'/'μm'")
    judgement: JudgementResult = Field(default="n/a", description="判定结果")
    sample_id: str | None = Field(None, description="样本 ID")
    method_name: str | None = Field(None, description="检测方法名")
    is_incomplete: bool = Field(default=False, description="是否来自空单元格")

    model_config = ConfigDict(from_attributes=True)


class Finding(BaseNode):
    """发现/结论。业务键：UUID。"""

    finding_text: str = Field(..., description="原文表达")
    polarity: Polarity = Field(..., description="关键：识别 '未见 X / 不存在 X'")
    evidence_source: EvidenceSource = Field(..., description="证据来源")
    evidence_strength: EvidenceStrength = Field(..., description="证据强度")
    referenced_concept: str | None = Field(None, description="涉及的概念名，如 '夹杂'")

    model_config = ConfigDict(from_attributes=True)


class RootCause(BaseNode):
    """根因（含因果链）。业务键：UUID。"""

    cause_text: str = Field(..., description="根因描述文本")
    cause_category: str | None = Field(None, description="链接到 RootCauseConcept 的分类")
    is_root: bool = Field(default=False, description="链起点（最底层根因）")
    is_symptom: bool = Field(default=False, description="链终点（最终现象）")
    is_confirmed: bool = Field(default=False, description="是否已被证据链确认")
    causal_narrative: str | None = Field(
        None,
        description="v0.1 LLM 输出完整因果链文本；v0.2 由人工补边",
    )
    chain_id: UUID | None = Field(None, description="所属因果链 ID")

    model_config = ConfigDict(from_attributes=True)


class RiskAssessment(BaseNode):
    """风险评估。业务键：report_id + scope。"""

    scope: str = Field(..., description="评估范围，如 '深圳14号线项目AW3工况'")
    severity_level: str = Field(..., description="严重等级，如 '维护等级'")
    safety_impact: SafetyImpact = Field(..., description="安全影响")
    operational_impact: OperationalImpact = Field(..., description="运营影响")
    affects_normal_operation: bool = Field(..., description="是否影响正常运营")
    risk_description: str = Field(..., description="风险描述")
    detection_capability: str | None = Field(
        None,
        description="检测能力，如 '制动自检时能监测'",
    )

    model_config = ConfigDict(from_attributes=True)


# ──────────────────────────────────────────────────────────────
# 独立模型（不继承 BaseNode）
# ──────────────────────────────────────────────────────────────


class Chunk(BaseModel):
    """原文片段（SCHEMA.md §6.5），不继承 BaseNode。"""

    chunk_id: str = Field(..., description="格式 report_id#section_path#para_idx")
    report_id: str = Field(..., description="所属报告 ID")
    section_path: list[str] = Field(default_factory=list, description="章节路径")
    para_idx: int = Field(..., description="段落序号")
    chunk_role: ChunkRole = Field(..., description="片段角色分类")
    text: str = Field(..., description="原文文本")
    token_count: int = Field(..., description="token 计数")

    # 表格特征
    is_table: bool = Field(default=False, description="是否来自表格")
    table_type: str | None = Field(
        None,
        description="表格类型：project_intro/team/defect_list/measurement/change_log",
    )
    table_metadata: dict | None = Field(None, description="原始列数、合并单元格等")

    # 占位符与图片
    is_placeholder: bool = Field(default=False, description="是否占位符片段")
    has_referenced_image: bool = Field(default=False, description="是否引用图片")

    # 向量（v0.2 启用；v0.1 Vectorizer 是 noop，此字段永远为 None）
    embedding: list[float] | None = Field(default=None, description="v0.2 接入 pgvector")

    # 时间戳
    created_at: datetime

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LeadsToEdge(BaseModel):
    """RootCause LEADS_TO 边属性（SCHEMA.md §6.3）。"""

    sequence_order: int = Field(..., description="在链中的位置（1-based）")
    chain_id: UUID = Field(..., description="所属因果链 ID")
    confidence: float = Field(..., ge=0.0, le=1.0)
    created_by: Literal["llm", "human"] = Field(
        ...,
        description="v0.1 仅 human 通过审核创建",
    )
    created_at: datetime

    model_config = ConfigDict(extra="forbid")
