"""ExtractionResult 容器（SCHEMA.md §11）。"""

from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.entity import (
    ActionEvent,
    Chunk,
    ClosureEvent,
    Customer,
    DefectOccurrence,
    EightDReport,
    Equipment,
    Experiment,
    Finding,
    InspectionEvent,
    Laboratory,
    Material,
    Measurement,
    Operator,
    Part,
    Person,
    Process,
    Project,
    RiskAssessment,
    RootCause,
    Standard,
    Supplier,
    Team,
    TestMethod,
    Vehicle,
    VerificationEvent,
)


class ExtractionResult(BaseModel):
    """单份文档抽取的完整结果（SCHEMA.md §11.1）。

    由 Pipeline 写入 entity_mirror 与 Neo4j。
    """

    doc_id: UUID = Field(..., description="文档 ID")
    report_id: str = Field(..., description="报告 ID（业务键）")
    extraction_version: str = Field(..., description="抽取流水线版本")
    schema_version: str = Field(default="v0.1.0")

    # 实体
    report: EightDReport | None = None
    projects: list[Project] = Field(default_factory=list)
    customers: list[Customer] = Field(default_factory=list)
    operators: list[Operator] = Field(default_factory=list)
    vehicles: list[Vehicle] = Field(default_factory=list)
    parts: list[Part] = Field(default_factory=list)
    materials: list[Material] = Field(default_factory=list)
    standards: list[Standard] = Field(default_factory=list)
    test_methods: list[TestMethod] = Field(default_factory=list)
    laboratories: list[Laboratory] = Field(default_factory=list)
    persons: list[Person] = Field(default_factory=list)
    teams: list[Team] = Field(default_factory=list)
    suppliers: list[Supplier] = Field(default_factory=list)
    processes: list[Process] = Field(default_factory=list)
    equipment: list[Equipment] = Field(default_factory=list)

    # 事件
    defect_occurrences: list[DefectOccurrence] = Field(default_factory=list)
    inspection_events: list[InspectionEvent] = Field(default_factory=list)
    experiments: list[Experiment] = Field(default_factory=list)
    actions: list[ActionEvent] = Field(default_factory=list)
    verifications: list[VerificationEvent] = Field(default_factory=list)
    closure: ClosureEvent | None = None

    # 辅助
    measurements: list[Measurement] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    root_causes: list[RootCause] = Field(default_factory=list)
    risk_assessments: list[RiskAssessment] = Field(default_factory=list)

    # Chunk（必含）
    chunks: list[Chunk] = Field(default_factory=list)

    # 概念引用（不创建新节点，仅链接已存在的）
    concept_references: list[dict] = Field(
        default_factory=list,
        description="格式 [{node_id, concept_type, concept_name}]",
    )

    # 抽取统计
    stats: dict = Field(default_factory=dict)


class RootCauseAnalysisOutput(BaseModel):
    """根因分析章节专用输出（SCHEMA.md §11.2）。"""

    inspection_events: list[InspectionEvent] = Field(default_factory=list)
    experiments: list[Experiment] = Field(default_factory=list)
    measurements: list[Measurement] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    root_causes: list[RootCause] = Field(default_factory=list)
    causal_narrative: str | None = Field(
        None,
        description="v0.1 整段因果链文本；v0.2 由人工补边",
    )
