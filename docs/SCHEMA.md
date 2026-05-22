# SCHEMA.md · 8D 知识图谱本体定义

**Schema 版本**：v0.1.0
**对应 PRD 版本**：v1.5
**最后更新**：2026-05-22
**文件路径**：docs/SCHEMA.md

本文档定义 8D 报告知识图谱的完整本体（Ontology）：实体类型、事件类型、概念类型、关系类型、公共属性、Pydantic 模型、Neo4j 约束。所有 Pipeline 组件必须严格遵守本文档定义的 schema。

---

## 1. 设计原则

1. **三层 LLMFriSPG 类型分层**：EntityType（实体）、EventType（事件）、ConceptType（概念）。
2. **强制溯源**：每个节点必须带 `supporting_chunks` 与 `source_doc_id`。
3. **互索引**：所有实体通过 `MENTIONED_IN` 边与 Chunk 双向关联。
4. **Schema 版本化**：每个节点带 `schema_version`，支持后续演进。
5. **v0.1 简化**：Part 暂不拆分 Type/Instance，序列号作为属性数组；因果链 Schema 完整但 LLM 仅输出扁平结构。
6. **占位符过滤**：识别到 `TBD/xxx/N/A/待定` 等不入图。
7. **审核状态**：v0.1 默认 `review_status=auto_committed`，预留 v0.2 审核字段。

---

## 2. 公共基类

所有图谱节点（Entity / Event）必须继承以下公共属性。

### 2.1 BaseNode（公共基类）

```python
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field
from uuid import UUID

ReviewStatus = Literal[
    "auto_committed",   # v0.1 默认
    "pending_review",   # v0.2+
    "in_review",
    "approved",
    "rejected",
    "modified",
    "on_hold",
    "committed",
]

Sensitivity = Literal["public", "restricted", "confidential"]


class BaseNode(BaseModel):
    """所有图谱节点的公共基类"""

    # 标识
    node_id: UUID = Field(..., description="全局唯一 ID")
    business_key: str = Field(..., description="业务键，用于幂等合并")

    # 溯源（必填）
    supporting_chunks: list[str] = Field(
        default_factory=list,
        description="原文 chunk id 列表，格式 report_id#section_path#para_idx",
    )
    source_doc_id: str = Field(..., description="源文档 ID")
    source_section: list[str] = Field(
        default_factory=list,
        description="所在章节路径，如 ['根本原因分析', '断口分析']",
    )

    # 抽取元信息
    confidence: float = Field(..., ge=0.0, le=1.0, description="抽取置信度")
    extraction_version: str = Field(..., description="抽取流水线版本，如 'pipeline-v0.1.0'")
    schema_version: str = Field(default="v0.1.0")

    # 审核
    review_status: ReviewStatus = Field(default="auto_committed")

    # 描述（可选）
    description: str | None = None
    summary: str | None = None

    # 治理
    owner_id: str
    sensitivity: Sensitivity = "restricted"

    # 时间戳
    created_at: datetime
    updated_at: datetime

    model_config = {"extra": "forbid", "validate_assignment": True}
```

### 2.2 BaseEvent（事件基类）

```python
class BaseEvent(BaseNode):
    """事件类型基类，比 Entity 多了时间属性"""

    occurred_at: datetime | None = Field(None, description="事件发生时间")
    location: str | None = None
    duration_seconds: float | None = None
```

---

## 3. EntityType（实体）

### 3.1 EightDReport · 8D 报告主体

业务键：`report_id`（来自质量通知号或文件 hash）

```python
ClosureStatus = Literal[
    "open",                       # 未关闭
    "closed",                     # 已闭环
    "partially_closed",           # 部分闭环
    "root_cause_unidentified",    # 根因未确认（如样本一）
]


class EightDReport(BaseNode):
    report_id: str                            # 业务键
    title: str
    quality_notification_no: str | None       # 质量通知号
    closure_status: ClosureStatus
    report_date: datetime | None
    report_version: str | None                # 如 "00-zh"、"1.0"
    customer_complaint_no: str | None
    field_completeness: float = Field(
        1.0, ge=0.0, le=1.0,
        description="字段完整度（识别到占位符则降低）",
    )
```

**关系**：
- `BELONGS_TO → Project`（多对多）
- `REPORTED_BY → Customer`
- `OPERATED_BY → Operator`
- `DESCRIBES → DefectOccurrence`
- `INVOLVES_TEAM → Team`

### 3.2 Project · 项目

业务键：`project_no`

```python
class Project(BaseNode):
    project_no: str
    name: str
    line_name: str | None         # 如 "兰州2号线"
    system: str | None            # 如 "制动控制系统"
```

### 3.3 Customer / Operator

业务键：`name`

```python
class Customer(BaseNode):
    name: str
    short_name: str | None


class Operator(BaseNode):
    name: str
    region: str | None
```

### 3.4 Vehicle · 车辆

业务键：`vehicle_no + project_no`

```python
class Vehicle(BaseNode):
    vehicle_no: str               # 如 "T030"
    project_no: str
    vehicle_type: str | None
```

### 3.5 Part · 部件（v0.1 简化版）

> v0.1 不区分 PartType / PartInstance，序列号作为属性数组。v0.2 拆分为两个独立类型。

业务键：`part_no`

```python
class Part(BaseNode):
    part_no: str                          # 克诺尔部件号，如 "G7029/SMF01"
    part_name: str                        # 中文名，如 "EP2002阀"
    serial_numbers: list[str] = Field(
        default_factory=list,
        description="v0.1 临时方案：所有出现过的序列号；v0.2 拆分为 PartInstance",
    )
    batch_numbers: list[str] = Field(default_factory=list)
    parent_part_no: str | None = None     # 父部件
    operating_mileage_km: float | None = None
    quantity_affected: int | None = None
```

**关系**：
- `PART_OF → Part`（递归）
- `MADE_OF → Material`
- `MANUFACTURED_BY → Supplier`

### 3.6 Material · 材料

业务键：`material_grade`

```python
class Material(BaseNode):
    material_grade: str           # 如 "X10CrNi18-8"
    material_type: str | None     # 如 "不锈钢"
    standards: list[str] = Field(
        default_factory=list,
        description="执行标准号列表",
    )
```

### 3.7 Standard · 标准/规范

业务键：`standard_no`

```python
class Standard(BaseNode):
    standard_no: str              # 如 "EN 10270-3:2011"
    standard_name: str | None
    issuing_body: str | None      # 发布机构，如 "EN" / "GB" / "DIN"
```

### 3.8 TestMethod · 检测方法

业务键：`method_name`（受控词表）

```python
class TestMethod(BaseNode):
    method_name: str              # 如 "断口分析" / "硬度试验" / "X-ray"
    method_category: str | None   # 如 "金相" / "化学" / "无损"
    standard_ref: str | None      # 引用的标准号
```

### 3.9 Laboratory · 第三方机构

业务键：`name`

```python
class Laboratory(BaseNode):
    name: str
    is_third_party: bool = True
    accreditation: str | None
```

### 3.10 Person / Team / Supplier

业务键：`Person` 用 `email`，`Team` / `Supplier` 用 `name`

```python
class Person(BaseNode):
    name: str
    email: str
    department: str | None
    role: str | None              # 如 "项目质量工程师"
    phone: str | None


class Team(BaseNode):
    name: str
    team_type: str | None         # 如 "8D 问题解决团队"


class Supplier(BaseNode):
    name: str
    region: str | None
```

### 3.11 Process / Equipment

业务键：`name`

```python
class Process(BaseNode):
    name: str                     # 如 "热处理"
    process_type: str | None


class Equipment(BaseNode):
    name: str
    model: str | None
```

---

## 4. EventType（事件）

### 4.1 DefectOccurrence · 故障发生

业务键：`report_id + vehicle_no + occurred_at`

```python
class DefectOccurrence(BaseEvent):
    report_id: str
    defect_description: str
    defect_location: str | None           # 如 "靠近端部"
    serial_no: str | None                 # 出问题的具体序列号
    operating_mileage_km: float | None
    detection_context: str | None         # 如 "首次自检" / "日检"
    is_first_occurrence: bool | None
```

**关系**：
- `OCCURS_ON → Vehicle`
- `INVOLVES → Part`
- `EXHIBITS → FailureModeConcept`

### 4.2 InspectionEvent · 检测事件

业务键：UUID（每次检测唯一）

```python
class InspectionEvent(BaseEvent):
    inspection_name: str                  # 如 "断口分析"
    sample_id: str | None
    is_third_party: bool = False
    laboratory_name: str | None
    conclusion_text: str | None
```

**关系**：
- `APPLIES → TestMethod`
- `PERFORMED_BY → Laboratory`
- `PRODUCES → Measurement`
- `CONCLUDES → Finding`
- `EXAMINES → Part`

### 4.3 Experiment · 验证型实验

业务键：UUID

```python
class Experiment(BaseEvent):
    experiment_name: str                  # 如 "对比实验" / "加速老化试验"
    hypothesis: str                       # 假设描述
    method_description: str
    control_group: str | None             # 对照组描述
    test_group: str | None                # 实验组描述
    conclusion: str
    cycle_count: int | None               # 如疲劳试验 700 万次
```

**关系**：
- `TESTS → RootCause`（验证某个根因假设）
- `PRODUCES → Measurement`

### 4.4 Action 系列事件

业务键：UUID

```python
ActionType = Literal["containment", "corrective", "preventive"]
ResponsibleParty = Literal["KB", "Supplier", "Customer", "Operator", "Other"]
ActionStatus = Literal["planned", "in_progress", "verified", "closed", "tbd"]


class ActionEvent(BaseEvent):
    """统一的 Action 事件，通过 action_type 区分 D3/D5/D6/D7"""

    action_type: ActionType
    action_description: str
    responsible_party: ResponsibleParty
    responsible_person: str | None
    deadline: datetime | None
    status: ActionStatus = "planned"
    verification_result: str | None
```

**关系**：
- `ADDRESSES → RootCause`
- `EXECUTED_BY → Person | Supplier`

> 注：v0.1 用统一 `ActionEvent` + `action_type` 区分；v0.3 视需要拆分为 `ContainmentExecution / CorrectiveExecution / PreventiveExecution`。

### 4.5 VerificationEvent · 验证事件

```python
class VerificationEvent(BaseEvent):
    verification_method: str
    verification_result: Literal["passed", "failed", "inconclusive", "tbd"]
    verified_action_id: UUID
```

### 4.6 ClosureEvent · 报告关闭

```python
class ClosureEvent(BaseEvent):
    closure_decision: str
    final_meeting_date: datetime | None
    attendees: list[str] = Field(default_factory=list)
```

---

## 5. ConceptType（概念分类树）

> 概念是受控词表，**不从原文抽取生成新节点**，只通过 Aligner 链接。v0.1 由 `domain_lexicon.yaml` 维护初始树，v0.3 由 Aligner 自动扩充候选项。

### 5.1 FailureModeConcept · 失效模式

```python
class FailureModeConcept(BaseNode):
    concept_name: str             # 如 "疲劳断裂"
    parent_concept: str | None    # 上位概念，如 "断裂"
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None
```

初始树（节选）：
```
失效模式
├── 断裂
│   ├── 疲劳断裂
│   ├── 脆性断裂
│   └── 应力腐蚀开裂
├── 变形
│   ├── 弹性变形超限
│   └── 塑性变形
├── 磨损
└── 腐蚀
```

### 5.2 FractographicFeatureConcept · 断口特征

```python
class FractographicFeatureConcept(BaseNode):
    concept_name: str             # 如 "海滩花样" / "韧窝形貌" / "疲劳条带"
    aliases: list[str] = Field(default_factory=list)
```

### 5.3 MetallurgicalDefectConcept · 冶金缺陷

```python
class MetallurgicalDefectConcept(BaseNode):
    concept_name: str             # 如 "夹杂" / "气孔" / "疏松" / "脱碳"
    aliases: list[str] = Field(default_factory=list)
```

### 5.4 RootCauseConcept · 根因分类

```python
class RootCauseConcept(BaseNode):
    concept_name: str             # 如 "外部过载" / "材料缺陷" / "设计不足"
    parent_concept: str | None
    aliases: list[str] = Field(default_factory=list)
```

### 5.5 ActionTypeConcept · 对策类型

```python
class ActionTypeConcept(BaseNode):
    concept_name: str             # 如 "100%全检" / "工艺改进" / "模具更换"
    aliases: list[str] = Field(default_factory=list)
```

---

## 6. 辅助类型

### 6.1 Measurement · 测量值（三元组扩展）

业务键：`inspection_event_id + quantity + sample_id`

```python
JudgementResult = Literal["pass", "fail", "marginal", "inconclusive", "n/a"]


class Measurement(BaseNode):
    quantity: str                         # 如 "硬度 HV10" / "二级调节器压力"
    target_value: float | None            # 设定值
    tolerance_upper: float | None
    tolerance_lower: float | None
    actual_value: float | str             # 实测值（数值或如"700万次"等文本）
    unit: str | None                      # 如 "bar" / "HV" / "μm"
    judgement: JudgementResult = "n/a"
    sample_id: str | None
    method_name: str | None
    is_incomplete: bool = False           # 来自空单元格
```

### 6.2 Finding · 发现/结论

业务键：UUID

```python
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


class Finding(BaseNode):
    finding_text: str                     # 原文表达
    polarity: Polarity                    # 关键：识别"未见 X / 不存在 X"
    evidence_source: EvidenceSource
    evidence_strength: EvidenceStrength
    referenced_concept: str | None        # 涉及的概念名（如"夹杂"）
```

**关系**：
- `SUPPORTS → RootCause`（polarity=positive 且 strength=direct）
- `RULES_OUT → RootCause`（polarity=negative）

### 6.3 RootCause · 根因（含因果链）

业务键：UUID

```python
class RootCause(BaseNode):
    cause_text: str
    cause_category: str | None            # 链接到 RootCauseConcept
    is_root: bool = False                 # 链起点（最底层根因）
    is_symptom: bool = False              # 链终点（最终现象）
    is_confirmed: bool = False            # 是否已被证据确认
    causal_narrative: str | None          # v0.1 LLM 输出的完整因果链文本
    chain_id: UUID | None                 # 所属因果链 ID
```

**关系**：
- `LEADS_TO → RootCause`，边属性：

```python
class LeadsToEdge(BaseModel):
    sequence_order: int                   # 在链中的位置（1-based）
    chain_id: UUID
    confidence: float
    created_by: Literal["llm", "human"]   # v0.1 仅 human 通过审核创建
    created_at: datetime
```

> v0.1 抽取层只输出扁平 RootCause + `causal_narrative`，不自动建 LEADS_TO 边。审核员在 v0.2 UI 中手动连线。v0.3 启用自动抽取。

### 6.4 RiskAssessment · 风险评估

业务键：`report_id + scope`

```python
SafetyImpact = Literal["none", "minor", "moderate", "major", "critical"]
OperationalImpact = Literal["none", "minor", "moderate", "major", "stoppage"]


class RiskAssessment(BaseNode):
    scope: str                            # 如 "深圳14号线项目AW3工况"
    severity_level: str                   # 如 "维护等级"
    safety_impact: SafetyImpact
    operational_impact: OperationalImpact
    affects_normal_operation: bool
    risk_description: str
    detection_capability: str | None      # 如 "制动自检时能监测"
```

### 6.5 Chunk · 原文片段

业务键：`chunk_id`（格式：`report_id#section_path#para_idx`）

```python
ChunkRole = Literal[
    "metadata",      # 项目简介、变更记录
    "background",    # 结构功能介绍等领域知识
    "evidence",      # 检测结果、实验数据
    "hypothesis",    # 待验证的假设
    "conclusion",    # 根因结论
    "action",        # 对策
    "unknown",
]


class Chunk(BaseModel):
    chunk_id: str                         # report_id#section_path#para_idx
    report_id: str
    section_path: list[str]
    para_idx: int
    chunk_role: ChunkRole
    text: str
    token_count: int

    # 表格特征
    is_table: bool = False
    table_type: str | None = None         # project_intro / team / defect_list / measurement / change_log
    table_metadata: dict | None = None    # 原始列数、合并单元格等

    # 占位符与图片
    is_placeholder: bool = False
    has_referenced_image: bool = False

    # 向量
    embedding: list[float] | None = None  # v0.2 启用

    # 时间
    created_at: datetime
```

---

## 7. 关系总览

### 7.1 关系定义表

| 关系名 | 起点类型 | 终点类型 | 基数 | 备注 |
|---|---|---|---|---|
| `BELONGS_TO` | EightDReport | Project | M:N | 一报告多项目 |
| `REPORTED_BY` | EightDReport | Customer | M:1 | |
| `OPERATED_BY` | EightDReport | Operator | M:N | |
| `INVOLVES_TEAM` | EightDReport | Team | M:N | |
| `DESCRIBES` | EightDReport | DefectOccurrence | 1:N | |
| `OCCURS_ON` | DefectOccurrence | Vehicle | M:N | |
| `INVOLVES` | DefectOccurrence | Part | M:N | |
| `EXHIBITS` | DefectOccurrence | FailureModeConcept | M:N | |
| `PART_OF` | Part | Part | M:1 | 递归 |
| `MADE_OF` | Part | Material | M:N | |
| `MANUFACTURED_BY` | Part | Supplier | M:N | |
| `COMPLIES_WITH` | Material | Standard | M:N | |
| `APPLIES` | InspectionEvent | TestMethod | M:N | |
| `PERFORMED_BY` | InspectionEvent | Laboratory | M:1 | |
| `EXAMINES` | InspectionEvent | Part | M:N | |
| `PRODUCES` | InspectionEvent / Experiment | Measurement | 1:N | |
| `CONCLUDES` | InspectionEvent | Finding | 1:N | |
| `TESTS` | Experiment | RootCause | M:N | 验证假设 |
| `SUPPORTS` | Finding | RootCause | M:N | polarity=positive |
| `RULES_OUT` | Finding | RootCause | M:N | polarity=negative |
| `LEADS_TO` | RootCause | RootCause | M:N | 因果链 |
| `ADDRESSES` | ActionEvent | RootCause | M:N | |
| `EXECUTED_BY` | ActionEvent | Person / Supplier | M:1 | |
| `VERIFIES` | VerificationEvent | ActionEvent | M:1 | |
| `ASSESSES_RISK_OF` | RiskAssessment | DefectOccurrence | M:1 | |
| `MENTIONED_IN` | (任意 Entity/Event) | Chunk | M:N | **必建双向边** |

### 7.2 互索引规则（强制）

每次写入实体节点时，必须为该实体的 `supporting_chunks` 中每个 chunk_id 建立 `MENTIONED_IN` 双向边：

```cypher
MATCH (e {node_id: $node_id})
UNWIND $supporting_chunks AS cid
MATCH (c:Chunk {chunk_id: cid})
MERGE (e)-[:MENTIONED_IN]->(c)
MERGE (c)-[:MENTIONS]->(e)
```

---

## 8. Neo4j 约束与索引

### 8.1 唯一约束

```cypher
// 业务键唯一约束
CREATE CONSTRAINT report_business_key IF NOT EXISTS
  FOR (n:EightDReport) REQUIRE n.report_id IS UNIQUE;

CREATE CONSTRAINT project_business_key IF NOT EXISTS
  FOR (n:Project) REQUIRE n.project_no IS UNIQUE;

CREATE CONSTRAINT part_business_key IF NOT EXISTS
  FOR (n:Part) REQUIRE n.part_no IS UNIQUE;

CREATE CONSTRAINT vehicle_business_key IF NOT EXISTS
  FOR (n:Vehicle) REQUIRE (n.vehicle_no, n.project_no) IS UNIQUE;

CREATE CONSTRAINT chunk_business_key IF NOT EXISTS
  FOR (n:Chunk) REQUIRE n.chunk_id IS UNIQUE;

CREATE CONSTRAINT material_business_key IF NOT EXISTS
  FOR (n:Material) REQUIRE n.material_grade IS UNIQUE;

CREATE CONSTRAINT standard_business_key IF NOT EXISTS
  FOR (n:Standard) REQUIRE n.standard_no IS UNIQUE;

CREATE CONSTRAINT person_business_key IF NOT EXISTS
  FOR (n:Person) REQUIRE n.email IS UNIQUE;

CREATE CONSTRAINT customer_business_key IF NOT EXISTS
  FOR (n:Customer) REQUIRE n.name IS UNIQUE;

CREATE CONSTRAINT supplier_business_key IF NOT EXISTS
  FOR (n:Supplier) REQUIRE n.name IS UNIQUE;

// node_id 全局唯一
CREATE CONSTRAINT global_node_id IF NOT EXISTS
  FOR (n) REQUIRE n.node_id IS UNIQUE;
```

### 8.2 索引

```cypher
// 时间索引
CREATE INDEX report_date_idx IF NOT EXISTS FOR (n:EightDReport) ON (n.report_date);
CREATE INDEX defect_occurred_at_idx IF NOT EXISTS FOR (n:DefectOccurrence) ON (n.occurred_at);

// closure_status 过滤
CREATE INDEX closure_status_idx IF NOT EXISTS FOR (n:EightDReport) ON (n.closure_status);

// review_status 过滤
CREATE INDEX review_status_idx IF NOT EXISTS FOR (n) ON (n.review_status);

// Chunk 检索
CREATE INDEX chunk_report_idx IF NOT EXISTS FOR (n:Chunk) ON (n.report_id);
CREATE INDEX chunk_role_idx IF NOT EXISTS FOR (n:Chunk) ON (n.chunk_role);
```

---

## 9. PostgreSQL 镜像表

> Neo4j 存图谱关系，PostgreSQL 存元数据、staging、Chunk 全文。两者通过 `node_id` 同步。

### 9.1 核心表

```sql
-- 文档元数据
CREATE TABLE documents (
    doc_id UUID PRIMARY KEY,
    report_id VARCHAR(64) UNIQUE NOT NULL,
    file_name VARCHAR(512) NOT NULL,
    file_type VARCHAR(32) NOT NULL,
    file_hash VARCHAR(64) NOT NULL,
    minio_object_key VARCHAR(512) NOT NULL,
    owner_id VARCHAR(64) NOT NULL,
    sensitivity VARCHAR(32) NOT NULL DEFAULT 'restricted',
    upload_status VARCHAR(32) NOT NULL,
    pipeline_status VARCHAR(32) NOT NULL DEFAULT 'pending',
    schema_version VARCHAR(16) NOT NULL,
    extraction_version VARCHAR(32),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Chunk 表（全文 + 向量预留）
CREATE TABLE chunks (
    chunk_id VARCHAR(256) PRIMARY KEY,
    report_id VARCHAR(64) NOT NULL REFERENCES documents(report_id),
    section_path TEXT[] NOT NULL,
    para_idx INT NOT NULL,
    chunk_role VARCHAR(32) NOT NULL,
    text TEXT NOT NULL,
    token_count INT,
    is_table BOOLEAN DEFAULT FALSE,
    table_type VARCHAR(64),
    table_metadata JSONB,
    is_placeholder BOOLEAN DEFAULT FALSE,
    has_referenced_image BOOLEAN DEFAULT FALSE,
    embedding vector(1024),  -- PGVector，v0.2 启用
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX chunks_report_idx ON chunks(report_id);
CREATE INDEX chunks_role_idx ON chunks(chunk_role);

-- 实体镜像表（用于审计、回溯、staging）
CREATE TABLE entity_mirror (
    node_id UUID PRIMARY KEY,
    entity_type VARCHAR(64) NOT NULL,
    business_key VARCHAR(512) NOT NULL,
    payload JSONB NOT NULL,             -- 完整 Pydantic 序列化
    review_status VARCHAR(32) NOT NULL,
    confidence FLOAT NOT NULL,
    extraction_version VARCHAR(32) NOT NULL,
    schema_version VARCHAR(16) NOT NULL,
    source_doc_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX entity_mirror_type_idx ON entity_mirror(entity_type);
CREATE INDEX entity_mirror_doc_idx ON entity_mirror(source_doc_id);
CREATE INDEX entity_mirror_review_idx ON entity_mirror(review_status);

-- LLM 调用日志（成本归因）
CREATE TABLE llm_usage_log (
    id BIGSERIAL PRIMARY KEY,
    request_id UUID NOT NULL,
    caller_module VARCHAR(128) NOT NULL,
    related_doc_id VARCHAR(64),
    related_task_id UUID,
    model_name VARCHAR(64) NOT NULL,
    prompt_tokens INT NOT NULL,
    completion_tokens INT NOT NULL,
    total_tokens INT NOT NULL,
    cost_usd DECIMAL(10, 6),
    latency_ms INT,
    status VARCHAR(16) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX llm_usage_doc_idx ON llm_usage_log(related_doc_id);
CREATE INDEX llm_usage_created_idx ON llm_usage_log(created_at);

-- 审计日志
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    action VARCHAR(64) NOT NULL,
    target_type VARCHAR(64) NOT NULL,
    target_id VARCHAR(256) NOT NULL,
    before_value JSONB,
    after_value JSONB,
    ip VARCHAR(64),
    user_agent VARCHAR(512),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX audit_user_idx ON audit_log(user_id);
CREATE INDEX audit_target_idx ON audit_log(target_type, target_id);
```

---

## 10. JSON Schema 导出

所有 Pydantic 模型支持 `.model_json_schema()` 导出。建议在仓库 `backend/app/schemas/exported/` 下生成：

- `entity_schemas.json`：所有 EntityType
- `event_schemas.json`：所有 EventType
- `concept_schemas.json`：所有 ConceptType
- `auxiliary_schemas.json`：Measurement / Finding / RootCause / RiskAssessment / Chunk

CI 阶段必须校验：实际写入的实体数据 `validate_python` 不抛异常。

---

## 11. 抽取契约（Pipeline 输出）

### 11.1 抽取结果总容器

```python
class ExtractionResult(BaseModel):
    """单份文档抽取的完整结果，由 Pipeline 写入 entity_mirror 与 Neo4j"""

    doc_id: UUID
    report_id: str
    extraction_version: str
    schema_version: str

    # 实体
    report: EightDReport
    projects: list[Project] = []
    customers: list[Customer] = []
    operators: list[Operator] = []
    vehicles: list[Vehicle] = []
    parts: list[Part] = []
    materials: list[Material] = []
    standards: list[Standard] = []
    test_methods: list[TestMethod] = []
    laboratories: list[Laboratory] = []
    persons: list[Person] = []
    teams: list[Team] = []
    suppliers: list[Supplier] = []

    # 事件
    defect_occurrences: list[DefectOccurrence] = []
    inspection_events: list[InspectionEvent] = []
    experiments: list[Experiment] = []
    actions: list[ActionEvent] = []
    verifications: list[VerificationEvent] = []
    closure: ClosureEvent | None = None

    # 辅助
    measurements: list[Measurement] = []
    findings: list[Finding] = []
    root_causes: list[RootCause] = []
    risk_assessments: list[RiskAssessment] = []

    # Chunk（必含）
    chunks: list[Chunk]

    # 概念引用（不创建新概念，仅链接已存在的）
    concept_references: list[dict] = Field(
        default_factory=list,
        description="格式 [{node_id, concept_type, concept_name}]",
    )

    # 抽取统计
    stats: dict = Field(default_factory=dict)
```

### 11.2 LLM Extractor 子模块输出（按章节路由）

每个 chunk_role / 章节对应独立的 Pydantic schema：

| 章节路由 | 输出 Pydantic 类 |
|---|---|
| metadata（项目简介/变更记录/团队） | TableExtractor 直接产出，无 LLM |
| 故障描述（D2）+ 故障清单表 | `list[DefectOccurrence]` |
| 临时措施（D3） | `list[ActionEvent]`（action_type=containment） |
| 根本原因分析（D4） | `RootCauseAnalysisOutput` |
| 风险分析 | `list[RiskAssessment]` |
| 纠正措施（D5/D6/D7） | `list[ActionEvent]` |
| 验证（D8） | `list[VerificationEvent]` + `ClosureEvent` |

```python
class RootCauseAnalysisOutput(BaseModel):
    """根因分析章节专用输出"""

    inspection_events: list[InspectionEvent]
    experiments: list[Experiment]
    measurements: list[Measurement]
    findings: list[Finding]
    root_causes: list[RootCause]              # 扁平
    causal_narrative: str | None              # v0.1 整段因果链文本
```

---

## 12. 占位符与 polarity 处理规则

### 12.1 占位符黑名单

Reader 层匹配以下值（去除空格、大小写归一后）：

```python
PLACEHOLDER_VALUES = {
    "tbd", "xxx", "n/a", "na",
    "待定", "需增加内容", "未确定", "暂无",
    "/", "-", "—", "",
}
```

匹配命中时：
- Chunk 标记 `is_placeholder=True`
- 不传给 LLM Extractor
- 实体属性命中时设为 `None` 并降低 `field_completeness`

### 12.2 polarity 抽取规则

LLM prompt 必须为 Finding 显式输出 polarity：

| 原文表达 | polarity |
|---|---|
| "X 存在 / 发现 X / 检测到 X" | positive |
| "未见 X / 未发现 X / 排除 X / 不存在 X / 正常" | negative |
| "可能存在 / 疑似" | neutral |

举例（样本一弹簧报告）：

> "源区附近未见夹杂、气孔和疏松等冶金缺陷"

应抽出 3 个 Finding，每个 polarity=`negative`，`evidence_strength=ruled_out`，分别 RULES_OUT 三个 RootCause（夹杂导致疲劳、气孔导致疲劳、疏松导致疲劳）。

---

## 13. 版本演进策略

### 13.1 Schema 版本号

`schema_version` 采用语义化版本：

- v0.1.x：MVP 版本，Part 不拆分，因果链人工补边
- v0.2.x：拆分 PartType / PartInstance；启用人工审核
- v0.3.x：双轨抽取 + Aligner，启用因果链自动抽取
- v0.4.x：Action 拆分为 Containment/Corrective/Preventive 子类型

### 13.2 兼容性

- 节点必带 `schema_version` 字段
- 升级 schema 时必须提供迁移脚本：`backend/alembic/versions/` + `backend/scripts/migrate_graph_schema.py`
- 旧版本节点保留，不强制升级；查询时按 `schema_version` 过滤或兼容处理

#### 13.2.1 运行时 Organization 兼容约定（迁移复用）

为兼容当前抽取运行时（`ExtractionResult.organizations`）并降低跨框架迁移成本，新增以下约定：

- 允许把旧本体中的 `Operator / Customer / Supplier` 映射为统一 `Organization` 节点。
- `Organization.org_type` 推荐受控值：
  - `公司`
  - `供应商`
  - `客户`
  - `运营商`
  - `部门`
  - `项目组`
- 旧关系映射建议：
  - `EightDReport -[:OPERATED_BY]-> Operator`
    → `EightDReport -[:RESPONSIBLE_ORG]-> Organization(org_type="运营商")`
  - `Part -[:MANUFACTURED_BY]-> Supplier`
    → `PartSerial -[:SUPPLIED_BY]-> Organization(org_type="供应商")`（在运行时投影层）
- 迁移实现建议：
  - 保留旧标签节点，不强制删除；
  - 在写入层做标签兼容投影（或离线迁移脚本一次性归并）；
  - 业务查询优先按 `Organization` + `org_type` 兼容读取。

说明：以上为“迁移兼容层”约定，不改变本章旧本体历史定义；用于确保 Codex skills 与运行时代码在跨版本/跨框架迁移时语义一致。

#### 13.2.2 FailureProduct 两层建模兼容约定（迁移复用）

为兼容当前运行时在跨报告产品归一上的实现，补充以下迁移约定：

- 允许在运行时投影层引入两层结构：
  - `FailureProduct`：跨报告规范化产品节点（canonical）
  - `FailureProductMention`：单报告内原文事实节点（mention）
- 推荐关系链：
  - `EightDReport -[:MENTIONS_FAILURE_PRODUCT]-> FailureProductMention`
  - `FailureProductMention -[:INSTANCE_OF_FAILURE_PRODUCT]-> FailureProduct`
- 字段语义建议：
  - `FailureProduct` 侧保留：`canonical_name`、`family_code`、`aliases`、`kb_part_numbers`
  - `FailureProductMention` 侧保留：`KBPartName`、`KBPartNumber`、`Amount`、`report_no`
- 键策略建议：
  - canonical 节点优先按产品族/部件号做稳定归一；
  - mention 节点按“报告范围 + 原文字段”生成局部唯一键；
  - 避免把所有报告事实直接写到 canonical 节点导致覆盖。

说明：此约定用于补足 v0.1 文档未覆盖的运行时能力，确保后续迁移时保留“跨报告归一 + 报告内事实”双重语义。

#### 13.2.3 图治理与重抽清理兼容约定（迁移复用）

为避免历史脏数据导致单报告图分裂，新增治理兼容约定：

- 报告与 chunk 的主归属关系建议固定为：
  - `Chunk -[:CHUNK_OF_REPORT]-> EightDReport`
- 所有业务节点应携带：
  - `source_doc_id`
  - 可选 `filename`（用于历史兼容清理）
- 重抽写入建议先做“同文档清理”再写入：
  - 按 `source_doc_id` 清理；
  - 兜底按 `filename` 清理；
  - 对历史 `UNKNOWN` / `FS-UNKNOWN` / `EVT-UNKNOWN` 键做兼容修复或迁移。
- 对历史 `UNKNOWN#...` chunk，建议先迁移其 `MENTIONED_IN` 关系到 canonical chunk，再删除旧 chunk，避免证据链断裂。
- 组织抽取治理建议（尤其 `org_type="运营商"`）：
  - 不创建泛化占位组织（如 `org_name="供应商"`）；仅在有可识别主体名称时建组织节点；
  - 对“句子型片段”做过滤，避免把完整叙述句误建为组织名；
  - 若候选名称包含明显动作/描述词（如“运用于/分析/调查/故障”等）或以“且/并/而/与”等连接词起始，默认判为噪声；
  - 噪声组织不入图，避免污染责任组织关系。

说明：以上属于运行时写入治理契约，建议在跨框架迁移时保持等价策略，以防出现“孤立子图”与重复节点。

### 13.3 重抽接口预留

虽然 v0.1 不实现重抽，但所有节点必须带 `extraction_version`，Writer 必须支持按 `extraction_version` 删除/覆盖。

---

## 14. 检查清单（Schema 实现完成时）

实现 Schema 模块后，必须确认：

- [ ] 所有 Pydantic 模型继承 BaseNode / BaseEvent，extra=forbid
- [ ] 所有节点必带 supporting_chunks、source_doc_id、confidence、schema_version
- [ ] Organization 兼容映射（含 `org_type=运营商`）在 schema 与 skills 一致
- [ ] FailureProduct / FailureProductMention 双层语义在 schema 与 skills 一致
- [ ] 报告重抽遵循 `CHUNK_OF_REPORT + source_doc_id/filename + UNKNOWN 兼容修复` 治理约定
- [ ] Neo4j 唯一约束已创建（业务键）
- [ ] PostgreSQL Alembic 迁移已生成
- [ ] entity_mirror 表与 Neo4j 节点 1:1 同步
- [ ] 所有实体写入时自动建 MENTIONED_IN 双向边
- [ ] 占位符黑名单生效（Chunk.is_placeholder）
- [ ] Finding 必带 polarity，evidence_source，evidence_strength
- [ ] RootCause 支持 LEADS_TO 自关联（v0.1 不强抽）
- [ ] ExtractionResult 容器通过 Pydantic 校验
- [ ] JSON Schema 导出文件存在于 backend/app/schemas/exported/
- [ ] 单元测试覆盖每个 Pydantic 模型的合法/非法输入

---

**文档版本**：v1.0（基于 PRD v1.5）
**最后更新**：2026-05-22
**维护者**：项目团队
