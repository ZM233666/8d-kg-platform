# PIPELINE.md · Pipeline 组件契约

**Pipeline 版本**：v0.1.0
**对应 PRD 版本**：v1.5
**对应 Schema 版本**：v0.1.0
**最后更新**：2026-05-07
**文件路径**：docs/PIPELINE.md

本文档定义 8D 知识图谱构建 Pipeline 各组件的输入输出契约、错误处理策略、幂等性要求、Celery 任务编排。所有实现必须严格遵守本文档定义的接口。

---

## 1. Pipeline 总览

```
┌──────────┐   ┌──────────┐   ┌──────────────────┐   ┌──────────────┐   ┌────────────┐   ┌────────┐
│  Reader  │──▶│ Splitter │──▶│ TableExtractor   │──▶│ LLM Extractor│──▶│ Vectorizer │──▶│ Writer │
│ 文档解析  │   │ 章节路由  │   │ 表格规则解析      │   │ 章节级抽取    │   │ 向量化      │   │ 入图    │
└──────────┘   └──────────┘   └──────────────────┘   └──────────────┘   └────────────┘   └────────┘
     │              │                  │                    │                  │              │
     ▼              ▼                  ▼                    ▼                  ▼              ▼
  RawDocument   ParsedDocument    PartialExtraction   ExtractionResult   VectorizedResult   GraphCommit
                                  (从表格)            (合并表格+LLM)
```

每个组件必须：

1. 实现统一基类接口 `PipelineComponent`
2. 输入/输出严格遵循 Pydantic schema
3. 幂等：相同输入产生相同输出
4. 失败可重试，重试不产生副作用
5. 完整记录 trace_id、stage_name、耗时、token 消耗

---

## 2. 公共契约

### 2.1 Pipeline 上下文

```python
from datetime import datetime
from typing import Any
from uuid import UUID
from pydantic import BaseModel, Field


class PipelineContext(BaseModel):
    """流经所有 Pipeline 组件的上下文"""

    trace_id: UUID
    doc_id: UUID
    report_id: str
    user_id: str
    tenant_id: str | None = None

    # 版本信息
    pipeline_version: str = "pipeline-v0.1.0"
    schema_version: str = "v0.1.0"

    # 配置（可被运行时覆盖）
    config: dict[str, Any] = Field(default_factory=dict)

    # 累积统计（每个 stage 追加）
    stage_metrics: list[dict] = Field(default_factory=list)

    started_at: datetime
    model_config = {"extra": "forbid"}
```

### 2.2 组件基类

```python
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

I = TypeVar("I", bound=BaseModel)
O = TypeVar("O", bound=BaseModel)


class PipelineComponent(ABC, Generic[I, O]):
    """所有 Pipeline 组件统一基类"""

    component_name: str       # 子类必须设置
    component_version: str    # 子类必须设置

    @abstractmethod
    async def run(self, ctx: PipelineContext, input_data: I) -> O:
        """执行组件主逻辑"""
        ...

    async def health_check(self) -> bool:
        """健康检查（数据库连通、模型可用等）"""
        return True
```

### 2.3 Stage Metrics

每个组件运行结束必须 append 到 `ctx.stage_metrics`：

```python
class StageMetric(BaseModel):
    stage_name: str
    component_version: str
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    status: Literal["success", "partial_success", "failed"]
    items_processed: int = 0
    items_success: int = 0
    items_failed: int = 0
    llm_tokens_used: int = 0
    llm_cost_usd: float = 0.0
    error: str | None = None
```

### 2.4 错误处理统一原则

- 业务异常：继承 `app/core/exceptions.py` 中的 `PipelineError` 基类
- 致命错误：抛出 `FatalPipelineError`，整个文档处理失败
- 部分失败：抛出 `PartialPipelineError`，记录失败项，继续后续阶段
- 网络/IO 异常：自动重试 3 次（exponential backoff）
- 重试耗尽：标记为失败状态，保留原始数据供人工介入

```python
class PipelineError(Exception): ...
class FatalPipelineError(PipelineError): ...
class PartialPipelineError(PipelineError):
    def __init__(self, message: str, failed_items: list[dict]):
        super().__init__(message)
        self.failed_items = failed_items
```

---

## 3. Reader · 文档解析层

**职责**：把上传的二进制文档解析为统一的 `ParsedDocument` 结构，并完成基础清洗。

**模块路径**：`backend/app/pipeline/reader/`

### 3.1 输入 / 输出契约

```python
class ReaderInput(BaseModel):
    minio_object_key: str
    file_name: str
    file_type: Literal["pdf", "docx", "xlsx"]
    file_hash: str


class TextBlock(BaseModel):
    """正文段落"""
    para_idx: int
    text: str
    style_hints: dict = Field(default_factory=dict)
    # style_hints 可包含: font_size, is_bold, is_heading, heading_level, page_number


class TableBlock(BaseModel):
    """表格"""
    table_idx: int
    rows: list[list[str]]                 # 二维数组
    raw_column_count: int                 # 归一化前的原始列数
    has_merged_cells: bool = False
    page_number: int | None = None
    caption: str | None = None


class ParsedDocument(BaseModel):
    doc_id: UUID
    report_id: str
    file_type: str
    text_blocks: list[TextBlock]
    table_blocks: list[TableBlock]
    page_count: int | None = None
    metadata: dict = Field(default_factory=dict)


class ReaderOutput(BaseModel):
    parsed: ParsedDocument
    cleaning_stats: dict                   # 清洗统计：去重列数、占位符数、图片引用数
```

### 3.2 文件类型分派

| 类型 | 主用工具 | 备用工具 | 说明 |
|---|---|---|---|
| PDF | PyMuPDF (`fitz`) | pdfplumber | PyMuPDF 提取文本 + 段落，pdfplumber 提取表格 |
| DOCX | python-docx | unstructured | python-docx 拿正文段落 + 表格；unstructured 兜底处理无样式文档 |
| XLSX | openpyxl | — | 每个 sheet 当作一个 TableBlock |

> v0.1 不支持 XLS（旧版二进制 Word/Excel）、不支持扫描件 OCR，遇到时直接返回 `FatalPipelineError("unsupported_file_type")`。
> 注意：第一份样本是 `.doc` 格式，建议在前端上传时提示用户转换为 `.docx`，或后端用 LibreOffice headless 预转换（v0.1 可选实现）。

### 3.3 数据清洗规则（强制）

**清洗顺序**：

1. 全半角混用归一（数字、字母、标点统一为半角）
2. 空白字符归一（连续空格压缩为 1 个，保留段落分隔）
3. 表格重复列归一：检测连续相同列名（如"质量问题标题|质量问题标题"），保留首次出现
4. 表格合并单元格处理：合并单元格的内容向所有被合并位置复制
5. 占位符识别：见 SCHEMA.md §12.1，命中后段落级标记 `is_placeholder` 但**保留原文**
6. 图片引用识别：正则 `(如图|见下图|如下图所示|下图|上图)` → 段落 `style_hints["has_referenced_image"]=True`

```python
PLACEHOLDER_VALUES = {
    "tbd", "xxx", "n/a", "na",
    "待定", "需增加内容", "未确定", "暂无",
    "/", "-", "—", "",
}

IMAGE_REF_PATTERN = r"(如图|见下图|如下图所示|下图|上图)"
```

### 3.4 错误处理

| 错误场景 | 处理 |
|---|---|
| 文件不存在 / hash 不匹配 | `FatalPipelineError("file_not_found")` |
| 不支持的文件类型 | `FatalPipelineError("unsupported_file_type")` |
| 文件损坏 / 解析异常 | 重试 1 次，失败则 `FatalPipelineError("parse_failed")` |
| 文件过大（>50MB） | `FatalPipelineError("file_too_large")` |
| 单个表格解析失败 | `PartialPipelineError`，跳过该表格继续 |

### 3.5 幂等性

- 输入键：`doc_id + file_hash`
- 同一 doc_id 重复解析必须产生完全一致的 `text_blocks` / `table_blocks`（para_idx、table_idx 稳定）

### 3.6 测试要求

- 两份真实样本（弹簧断裂、EP2002）必须能正确解析所有表格
- 占位符识别的单元测试覆盖 PLACEHOLDER_VALUES 全集
- 重复列归一测试（基于样本一的合并单元格表格）

---

## 4. Splitter · 章节路由层

**职责**：将 `ParsedDocument` 切分为带 `section_path` 与 `chunk_role` 的 Chunk 序列。

**模块路径**：`backend/app/pipeline/splitter/`

### 4.1 输入 / 输出契约

```python
class SplitterInput(BaseModel):
    parsed: ParsedDocument


class SplitterOutput(BaseModel):
    chunks: list[Chunk]                   # 完整的 Chunk 序列（含表格 chunk）
    section_tree: dict                    # 嵌套章节树，便于前端展示
    unrouted_count: int                   # section=unknown 的 chunk 数
```

### 4.2 章节字典（配置化）

`backend/app/pipeline/splitter/section_dict.yaml`：

```yaml
templates:
  - name: kb_standard_8d
    description: "克诺尔标准 8D 模板"
    sections:
      "项目简介":           { d_step: "D0", chunk_role: "metadata" }
      "问题解决团队":        { d_step: "D1", chunk_role: "metadata" }
      "问题描述":           { d_step: "D2", chunk_role: "evidence" }
      "临时措施":           { d_step: "D3", chunk_role: "action" }
      "临时解决方案":        { d_step: "D3", chunk_role: "action" }
      "根本原因分析":        { d_step: "D4", chunk_role: "evidence" }
      "风险分析":           { d_step: "D4-risk", chunk_role: "conclusion" }
      "纠正措施":           { d_step: "D5/D6", chunk_role: "action" }
      "纠正措施验证":        { d_step: "D7", chunk_role: "action" }
      "最终会议":           { d_step: "D8", chunk_role: "action" }
      "变更记录":           { d_step: "META", chunk_role: "metadata" }

    # 子章节自动继承父级 chunk_role，除非显式覆盖
    sub_section_overrides:
      "结构":               { chunk_role: "background" }
      "功能":               { chunk_role: "background" }
      "弹簧介绍":            { chunk_role: "background" }
      "断口分析":            { chunk_role: "evidence" }
      "金相检测":            { chunk_role: "evidence" }
      "硬度试验":            { chunk_role: "evidence" }
      "化学成分分析":         { chunk_role: "evidence" }
      "对比实验分析":         { chunk_role: "evidence" }
      "加速老化试验":         { chunk_role: "evidence" }
      "实验结论":            { chunk_role: "conclusion" }
      "分析汇总":            { chunk_role: "conclusion" }
      "根本原因":            { chunk_role: "conclusion" }
```

> v0.1 内置 1 套模板（kb_standard_8d）；v0.2+ 支持每个客户/项目独立模板。

### 4.3 切分算法

**Step 1：标题识别**

按优先级判断段落是否为章节标题：

1. **样式特征**：style_hints 中 `is_heading=True` 或 `font_size > body_size * 1.2` 或 `is_bold=True`
2. **关键词匹配**：段落文本（去除前缀编号 / 空格 / `#`）命中字典
3. **格式特征**：段落短（<30 字符）+ 独占一行 + 后随长正文

**Step 2：构建章节树**

- 维护 `section_stack`，遇到更高级标题 pop，遇到同级或低级 push
- 每个 chunk 的 `section_path` = 当前 stack 全路径
- chunk_role 由 sub_section_overrides 优先，否则继承最近父级

**Step 3：表格归属**

- 表格 chunk 的 `section_path` = 表格上方最近的章节路径
- table_type 由 TableExtractor 在下一阶段识别填入

**Step 4：粒度切分**

- 同一 section 下的连续 TextBlock 合并为一个 chunk
- 如果合并后超过 token 上限（默认 1500），按句号/换行二次切分
- 每个 chunk 保留其覆盖的 para_idx 范围（`para_idx_start` / `para_idx_end`）

**Step 5：兜底**

- 找不到任何已知章节时，整篇按 token 切分，全部标 `section=unknown` + `chunk_role=unknown`
- `unrouted_count > total * 0.5` 时返回 warning（但不失败）

### 4.4 输出示例

```python
Chunk(
    chunk_id="600987222#根本原因分析/金相检测/断口附近金相#0",
    report_id="600987222",
    section_path=["根本原因分析", "金相检测", "断口附近金相"],
    para_idx=42,
    chunk_role="evidence",
    text="断口附近取样，源区附近未见夹杂、气孔和疏松等冶金缺陷...",
    token_count=156,
    is_table=False,
    is_placeholder=False,
    has_referenced_image=False,
    ...
)
```

### 4.5 错误处理

| 错误场景 | 处理 |
|---|---|
| 章节字典加载失败 | `FatalPipelineError("section_dict_invalid")` |
| 全文无法识别任何章节 | 整篇标 unknown，记录 warning，**不失败** |
| 单个段落 token 计数失败 | 跳过 token 限制，整段作为一个 chunk |

### 4.6 幂等性

- 输入相同的 ParsedDocument 必须产生相同的 chunk_id 序列
- chunk_id 必须确定性生成：`{report_id}#{section_path_joined}#{para_idx}`

### 4.7 测试要求

- 两份样本切分后，章节路径正确率 ≥ 95%
- chunk_role 标记正确率 ≥ 90%
- 嵌套层级（如"根本原因分析/金相检测/断口附近金相"）正确还原

---

## 5. TableExtractor · 表格规则解析层

**职责**：用 pandas + 规则识别 5 类已知表格，规则解析为结构化实体；不识别的表格回退给 LLM。**零 LLM 调用。**

**模块路径**：`backend/app/pipeline/table_extractor/`

### 5.1 输入 / 输出契约

```python
class TableExtractorInput(BaseModel):
    chunks: list[Chunk]                   # 来自 Splitter（含表格 chunk）


class PartialExtraction(BaseModel):
    """从表格直接得到的部分实体"""

    report: EightDReport | None = None         # 项目简介表
    persons: list[Person] = []                  # 团队表
    defect_occurrences: list[DefectOccurrence] = []  # 故障清单表
    measurements: list[Measurement] = []        # 测量结果表
    report_versions: list[dict] = []            # 变更记录表

    # 已被规则消费的 chunk_id（不再交给 LLM）
    consumed_chunk_ids: set[str] = Field(default_factory=set)


class TableExtractorOutput(BaseModel):
    partial: PartialExtraction
    chunks_updated: list[Chunk]           # 表格 chunk 的 table_type 字段已填入
    rule_match_stats: dict                # 每类表格命中数
    unrouted_tables: list[str]            # 未识别的表格 chunk_id
```

### 5.2 5 类表格识别器

每个识别器实现统一接口：

```python
class TableMatcher(ABC):
    table_type: str

    @abstractmethod
    def match(self, table_chunk: Chunk, raw_table: list[list[str]]) -> bool:
        """返回是否命中此类型"""

    @abstractmethod
    def extract(self, table_chunk: Chunk, raw_table: list[list[str]]) -> dict:
        """返回结构化抽取结果"""
```

| 类型 | 表头关键词（任一命中即可） | 章节上下文 | 输出 |
|---|---|---|---|
| `project_intro` | 项目号、客户、部件号、项目部件、项目名称 | section 包含"项目简介" | EightDReport 字段 |
| `change_log` | 版本、章节、变更描述 | section 包含"变更记录" | report_versions[] |
| `team` | 姓名、部门、邮件、邮件地址、邮箱、邮箱地址 | section 包含"团队"或"问题解决团队" | persons[] |
| `defect_list` | 故障日期、车号、序列号、料号 | section 包含"问题描述" | defect_occurrences[] |
| `measurement_result` | 设定压力、实测、判定结果，或单位 bar/HV/μm | section 包含"功能检测"/"硬度试验"/"测试结果" | measurements[] |

**匹配优先级（三重匹配）**：

1. 表头关键词 ≥ 1 个命中 → +50 分
2. 章节上下文匹配 → +30 分
3. 列数符合预期范围 → +20 分

总分 ≥ 70 视为命中；多个类型都命中时按总分排序，取最高。

### 5.3 字段映射规则

每个识别器的字段映射通过 YAML 配置：

`backend/app/pipeline/table_extractor/mappings/project_intro.yaml`：

```yaml
table_type: project_intro
column_aliases:
  report_id:
    - 质量通知号
  title:
    - 质量问题标题
    - 质量问题标题（KB）
  customer_complaint_no:
    - 质量涉及号（客户）
  project_no:
    - 项目号
    - 项目号（克诺尔）
  customer:
    - 客户
    - 客户（车辆制造商）
  operator:
    - 运营商
  part_name:
    - 克诺尔部件名称
    - 项目部件
  part_no:
    - 克诺尔部件号
  batch_no:
    - 螺栓批次号
  quantity_affected:
    - 所涉及部件的数量
  operating_mileage_km:
    - 所影响部件的运营里程
    - 所影响部件的里程数
```

**键值表识别**：项目简介表是"键-值"两列结构（首列字段名，次列字段值），识别器需自动检测：

- 行数 ≥ 5
- 第一列内容均为字段名（命中 alias）
- 第二列为对应值

### 5.4 数据规范化

| 字段 | 规范化规则 |
|---|---|
| 数量 | "4pcs" / "4 件" → `4` (int) |
| 里程 | "~300,000Km" / "30万公里" → `300000.0` (float, km) |
| 邮箱 | trim、小写化、去空格 |
| 日期 | "2022/8/19" → `datetime(2022, 8, 19)` |
| 测量值 | "5.7±0.1bar" → `target=5.7, tolerance_upper=0.1, tolerance_lower=-0.1, unit="bar"` |
| 测量值（无公差） | "4.607bar" → `actual_value=4.607, unit="bar"` |

### 5.5 表格清洗规则

- 重复列：保留首次，其余忽略，记录 `raw_column_count`
- 合并单元格：内容已在 Reader 层向所有位置复制
- 空单元格：`null` + 标记 `is_incomplete=True`
- 占位符（"TBD"/"待定"/"xxx"等）：字段设 `null` + `is_incomplete=True`

### 5.6 错误处理

| 错误场景 | 处理 |
|---|---|
| 表格格式异常（行数为 0 / 列数不一致） | 跳过该表格，记入 `unrouted_tables` |
| 字段映射失败（某字段无法匹配 alias） | 该字段 `null`，不阻断 |
| 数据规范化失败（如里程无法解析） | 该字段保留原始字符串，记 warning |
| 5 类规则全部未命中 | 表格 chunk 进入 `unrouted_tables`，由 LLM Extractor 处理 |

### 5.7 幂等性

- 同一表格输入必须产生完全一致的输出
- 不引入随机 UUID（业务键由报告号 + 行号确定性生成）

### 5.8 测试要求

- 两份样本中所有表格的识别正确率 100%
- 项目简介表字段抽取 F1 ≥ 95%
- 故障清单表（样本二）每行映射为正确的 DefectOccurrence
- 测量结果表的设定值/公差/实测值三元组解析正确

---

## 6. LLM Extractor · 章节级抽取层

**职责**：对未被 TableExtractor 消费的 chunk（按 chunk_role 路由）调用 LLM 抽取，与 TableExtractor 的 PartialExtraction 合并为 ExtractionResult。

**模块路径**：`backend/app/pipeline/extractor/`

### 6.1 输入 / 输出契约

```python
class LLMExtractorInput(BaseModel):
    chunks: list[Chunk]
    partial: PartialExtraction            # 来自 TableExtractor


class LLMExtractorOutput(BaseModel):
    result: ExtractionResult              # 完整 ExtractionResult（见 SCHEMA.md §11.1）
    extraction_metrics: dict              # 每个子抽取器的 token / 成功率 / 失败项
```

### 6.2 章节级路由

按 `chunk_role` 分组，调用不同的子抽取器：

| chunk_role | 子抽取器 | 输出 |
|---|---|---|
| `metadata` | 跳过（已由 TableExtractor 处理） | — |
| `background` | `BackgroundExtractor` | Material / Standard / Part 层级关系 |
| `evidence`（D2 段） | `DefectDescriptionExtractor` | 补充叙述型 DefectOccurrence 字段 |
| `evidence`（D4 段） | `RootCauseAnalysisExtractor` | InspectionEvent / Experiment / Measurement / Finding / RootCause |
| `hypothesis` | 与 `evidence` 同 | — |
| `conclusion` | `RootCauseExtractor` | RootCause（扁平）+ causal_narrative |
| `action` | `ActionExtractor` | ActionEvent + VerificationEvent + ClosureEvent |
| 风险分析章节 | `RiskExtractor` | RiskAssessment |
| `unknown` | `GenericExtractor`（兜底） | 尽力而为，confidence ≤ 0.5 |

### 6.3 子抽取器实现规范

每个子抽取器：

1. 用 instructor + Pydantic 定义结构化输出 schema（来自 SCHEMA.md）
2. Prompt 模板放在 `backend/app/pipeline/extractor/prompts/`，用 Jinja2 模板
3. 必须注入领域词典（`domain_lexicon.yaml`）作为受控词表
4. 必须强制输出 `supporting_chunk_ids`
5. 调用必须经过 `app/llm/` 抽象层

**通用 Prompt 模板骨架**：

```
你是一个 8D 报告分析专家。请从以下原文片段中抽取结构化信息。

## 上下文
报告 ID：{{ report_id }}
章节路径：{{ section_path }}
chunk_role：{{ chunk_role }}

## 原文片段
{% for chunk in chunks %}
[chunk_id: {{ chunk.chunk_id }}]
{{ chunk.text }}

{% endfor %}

## 受控词表（必须使用此列表中的术语，不要发明新术语）
失效模式：{{ lexicon.failure_modes | join("、") }}
断口特征：{{ lexicon.fractographic_features | join("、") }}
冶金缺陷：{{ lexicon.metallurgical_defects | join("、") }}
检测方法：{{ lexicon.test_methods | join("、") }}

## 抽取规则
1. 只抽取原文中明确出现的信息，禁止推测
2. 每条结果必须填写 supporting_chunk_ids，引用上述 chunk_id
3. confidence ∈ [0,1]，无明确证据时 ≤ 0.6
4. 关于 polarity（仅 Finding 字段）：
   - 原文表达"X 存在/发现 X" → polarity=positive
   - 原文表达"未见 X/未发现 X/排除 X/正常" → polarity=negative
   - 原文表达"可能/疑似" → polarity=neutral
5. 占位符（TBD/待定/xxx/N/A）字段返回 null
6. 所有日期使用 ISO 8601 格式

## 输出 Schema
{{ output_schema_json }}

请直接输出符合 Schema 的 JSON。
```

### 6.4 关键子抽取器细节

#### 6.4.1 RootCauseAnalysisExtractor

输入：D4 章节下所有 evidence/conclusion chunk
输出：`RootCauseAnalysisOutput`（见 SCHEMA.md §11.2）

**特殊处理**：

- 检测出 `Finding.polarity=negative` 时，自动建议关联 `RULES_OUT → RootCause`
- 实验数据（如"对比实验"）必须抽成 `Experiment` 而非 `InspectionEvent`
- 因果链：v0.1 仅输出 `causal_narrative` 文本字段 + 扁平 RootCause 列表，**禁止自动建 LEADS_TO 边**

**Prompt 增量约束**：

```
关于因果分析（v0.1 关键约束）：
- 列出所有提到的根因/中间原因/最终现象，作为扁平 root_causes 列表
- 不要在列表中表达"A 导致 B"的关系
- 完整的因果链描述放入 causal_narrative 字段（自由文本）
- 标记 is_root=True：链条最底层的根因
- 标记 is_symptom=True：链条最顶层的现象
```

#### 6.4.2 ActionExtractor

输入：D3/D5/D6/D7 段的 action chunk
输出：`list[ActionEvent]` + `list[VerificationEvent]` + `ClosureEvent`

**特殊处理**：

- 责任方判别：通过关键词识别（"克诺尔/KB" → KB；"供应商/上游" → Supplier；"客户/主机厂" → Customer）
- 状态：原文含"TBD/待定/xxx" → status="tbd"，confidence ≤ 0.5
- 多条对策必须拆为多个 ActionEvent

#### 6.4.3 RiskExtractor

输入：风险分析章节
输出：`list[RiskAssessment]`

**特殊处理**：

- 严重性映射："维护等级" → severity_level="maintenance"；"安全等级" → safety_impact="critical"
- 范围（scope）必须明确（如"深圳14号线项目AW3工况"），否则 scope=null + confidence ≤ 0.5

### 6.5 LLM 调用规范

- 模型选择：Schema-constrained 抽取统一用中等模型（默认 `claude-haiku-4-5` 或同等）；可在 config 中按 stage 覆盖
- 重试策略：3 次重试，exponential backoff (1s, 4s, 9s)
- 超时：单次调用 60s
- Token 上限：单次 prompt 不超过 8K tokens；超过时按 chunk 拆分多次调用

### 6.6 合并策略

LLM Extractor 输出与 TableExtractor 的 PartialExtraction 合并：

- 优先采用 PartialExtraction（规则置信度更高）
- LLM 输出与 PartialExtraction 字段冲突时：以 PartialExtraction 为准，LLM 值记入 `extraction_metrics.conflicts`
- LLM 抽出的实体若已存在于 PartialExtraction（按业务键），合并 supporting_chunks，confidence 取较高值

### 6.7 错误处理

| 错误场景 | 处理 |
|---|---|
| LLM 返回非 JSON / 无法 parse | 重试 1 次（带"请严格输出 JSON"提示），仍失败则该 chunk 跳过，记入 failed_items |
| Pydantic 验证失败 | 同上 |
| LLM 超时 | 重试 3 次，仍失败则跳过 |
| token 超限 | 自动拆 chunk 后重新调用 |
| 全部子抽取器都失败 | `PartialPipelineError`，但 PartialExtraction 部分仍可入图 |

### 6.8 幂等性

- LLM 调用本身不幂等（生成式），但 Pipeline 层必须保证：相同 doc_id + 相同 extraction_version 不重复抽取
- 通过 `entity_mirror` 表的 `(source_doc_id, extraction_version)` 去重

### 6.9 测试要求

- 两份样本的字段级 F1：表格直读 ≥ 95%、半结构化 ≥ 80%、叙述抽取 ≥ 65%
- polarity 字段准确率 ≥ 90%（基于针对性 golden set）
- 占位符过滤命中率 100%
- 受控词表合规率 ≥ 95%（不发明新术语）

---

## 7. Vectorizer · 向量化层（v0.2 启用）

**职责**：为 chunk 与实体生成 embedding，写入 PGVector。

**模块路径**：`backend/app/pipeline/vectorizer/`

> v0.1 实现空操作版本（保持接口兼容），v0.2 真正启用。

### 7.1 输入 / 输出契约

```python
class VectorizerInput(BaseModel):
    extraction_result: ExtractionResult


class VectorizerOutput(BaseModel):
    extraction_result: ExtractionResult   # 透传
    chunks_with_embedding: int
    entities_with_embedding: int
    skipped: int                          # v0.1 全部 skipped
```

### 7.2 v0.1 行为

- 接收 ExtractionResult，原样透传
- 不调用 embedding 模型
- 在 stage_metrics 记录 `status="skipped", reason="v0.1_disabled"`

### 7.3 v0.2 实现要点

- Chunk 级：embed `text` 字段（bge-m3 / bge-large-zh，1024 维）
- 实体级：embed `name + description + summary` 拼接
- 批量调用（每批 32 条）
- 失败重试 3 次

---

## 8. Writer · 入图层

**职责**：将 ExtractionResult 幂等写入 Neo4j + PostgreSQL，建立 MENTIONED_IN 双向边，记录审计日志。

**模块路径**：`backend/app/pipeline/writer/`

### 8.1 输入 / 输出契约

```python
class WriterInput(BaseModel):
    extraction_result: ExtractionResult


class WriterOutput(BaseModel):
    nodes_created: int
    nodes_merged: int
    relationships_created: int
    chunks_persisted: int
    audit_log_entries: int
    commit_id: UUID                       # 本次写入的批次 ID
```

### 8.2 写入顺序

严格按以下顺序，避免外键 / 关系悬空：

1. **Chunk → PostgreSQL**：先持久化所有 chunk 到 `chunks` 表
2. **Chunk → Neo4j**：MERGE Chunk 节点
3. **Concept 节点**：MERGE 已存在的 ConceptType 节点（不创建新概念，仅链接）
4. **Entity 节点**：MERGE 各 EntityType（按 SCHEMA.md §3）
5. **Event 节点**：MERGE 各 EventType（按 SCHEMA.md §4）
6. **Auxiliary 节点**：Measurement / Finding / RootCause / RiskAssessment
7. **关系**：按 SCHEMA.md §7.1 表顺序建立
8. **MENTIONED_IN 双向边**：对所有非 Chunk 节点，按 supporting_chunks 建立
9. **entity_mirror 表**：写入完整 payload
10. **audit_log 表**：写入操作记录

### 8.3 幂等写入规范

**所有 Cypher 必须用 MERGE，禁止裸 CREATE**。

通用模板：

```cypher
MERGE (n:{Label} {business_key: $business_key})
ON CREATE SET
    n.node_id = $node_id,
    n += $on_create_props,
    n.created_at = datetime()
ON MATCH SET
    n += $on_match_props,
    n.updated_at = datetime()
RETURN n.node_id AS node_id, EXISTS(n.created_at) AS is_new
```

**冲突处理**：

- 同一 business_key 已存在但来自不同 source_doc：合并 `supporting_chunks` 数组，保留较高 confidence，记 audit_log
- review_status 不允许从 `approved` / `committed` 退回到 `auto_committed`

### 8.4 关系幂等

```cypher
MATCH (a {node_id: $a_id}), (b {node_id: $b_id})
MERGE (a)-[r:{REL_TYPE}]->(b)
ON CREATE SET r += $rel_props, r.created_at = datetime()
ON MATCH SET r += $rel_props, r.updated_at = datetime()
```

### 8.5 MENTIONED_IN 双向边（强制）

```cypher
MATCH (e {node_id: $node_id})
UNWIND $supporting_chunks AS cid
MATCH (c:Chunk {chunk_id: cid})
MERGE (e)-[:MENTIONED_IN]->(c)
MERGE (c)-[:MENTIONS]->(e)
```

每个非 Chunk 实体写入后必须执行此操作。`supporting_chunks` 为空时跳过（但记 warning）。

### 8.6 事务边界

- 单份报告的所有写入在一个事务内（Neo4j session + PG transaction 协调）
- 失败时整体回滚，不留半成品
- PG 与 Neo4j 跨库事务用"先 PG 后 Neo4j"两阶段：PG 写入成功但 Neo4j 失败时，PG 标记 `pipeline_status=neo4j_failed` 供重试

### 8.7 错误处理

| 错误场景 | 处理 |
|---|---|
| Neo4j 唯一约束冲突 | 自动重试一次（可能是并发），仍失败则 `FatalPipelineError` |
| PG 外键冲突 | `FatalPipelineError`（说明上游 chunk 写入有遗漏） |
| Concept 节点不存在 | 跳过该关系，记 warning（v0.1 不自动创建概念） |
| 关系两端节点不存在 | 跳过该关系，记 warning |
| 部分实体写入失败 | `PartialPipelineError`，已写入部分保留，未写入部分记入 failed_items |

### 8.8 幂等性

- 同一 ExtractionResult 重复写入：所有 MERGE 命中已有节点，无新增
- `commit_id` 每次新生成，但写入结果一致

### 8.9 测试要求

- 同一份报告连续写入 2 次，第二次 `nodes_created=0`，`nodes_merged>0`
- MENTIONED_IN 双向边对所有实体建立完整
- 审计日志覆盖每个写操作

---

## 9. Celery 编排

**模块路径**：`backend/app/tasks/`

### 9.1 任务定义

```python
from celery import Celery, chain
from app.tasks.celery_app import celery_app


@celery_app.task(bind=True, max_retries=3, name="pipeline.read")
def task_read(self, ctx_dict: dict) -> dict: ...

@celery_app.task(bind=True, max_retries=3, name="pipeline.split")
def task_split(self, ctx_dict: dict, reader_output: dict) -> dict: ...

@celery_app.task(bind=True, max_retries=3, name="pipeline.table_extract")
def task_table_extract(self, ctx_dict: dict, splitter_output: dict) -> dict: ...

@celery_app.task(bind=True, max_retries=3, name="pipeline.llm_extract")
def task_llm_extract(self, ctx_dict: dict, table_output: dict) -> dict: ...

@celery_app.task(bind=True, max_retries=3, name="pipeline.vectorize")
def task_vectorize(self, ctx_dict: dict, extraction_output: dict) -> dict: ...

@celery_app.task(bind=True, max_retries=2, name="pipeline.write")
def task_write(self, ctx_dict: dict, vectorize_output: dict) -> dict: ...


def run_pipeline(doc_id: UUID, user_id: str) -> str:
    """启动完整 Pipeline，返回 task_chain_id"""
    ctx = build_pipeline_context(doc_id, user_id)
    workflow = chain(
        task_read.s(ctx.model_dump()),
        task_split.s(),
        task_table_extract.s(),
        task_llm_extract.s(),
        task_vectorize.s(),
        task_write.s(),
    )
    result = workflow.apply_async()
    return result.id
```

### 9.2 状态持久化

每个 task 开始 / 结束时更新 `documents.pipeline_status`：

```
pending → reading → splitting → table_extracting → llm_extracting → vectorizing → writing → committed
                                                                                            ↓
                                                                                          failed
```

每个阶段失败时记录到 `pipeline_runs` 表：

```sql
CREATE TABLE pipeline_runs (
    run_id UUID PRIMARY KEY,
    doc_id UUID NOT NULL REFERENCES documents(doc_id),
    trace_id UUID NOT NULL,
    pipeline_version VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    current_stage VARCHAR(32),
    stage_metrics JSONB,
    error_detail JSONB,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);
```

### 9.3 重试与幂等

- Celery 任务自带 `max_retries`，自动 exponential backoff
- 每个 stage 在开始时检查 `pipeline_runs`，若已成功则跳过（幂等保护）
- `FatalPipelineError` → 不重试，标记失败
- `PartialPipelineError` → 保存部分结果，继续后续 stage

### 9.4 并发控制

- 单文档串行（同一 doc_id 一次只能跑一个 pipeline）
- 实现：Redis 分布式锁，key=`pipeline_lock:{doc_id}`，TTL=30 分钟

---

## 10. 可观测性

### 10.1 日志规范

每个组件用 structlog 输出 JSON 日志：

```python
log.info(
    "stage_completed",
    trace_id=str(ctx.trace_id),
    doc_id=str(ctx.doc_id),
    stage="table_extractor",
    duration_ms=1234,
    items_processed=12,
    items_success=10,
)
```

### 10.2 关键指标（v0.3+ 接入 OpenTelemetry）

- 各 stage 耗时分布（P50/P95/P99）
- LLM token 消耗 / 成本
- 失败率（按 stage、按错误类型）
- 实体抽取数量分布

### 10.3 v0.1 简化版

- structlog → stdout
- LLM 调用记录在 `llm_usage_log` 表（已在 SCHEMA.md §9.1 定义）
- pipeline_runs 表查询近期任务状态

---

## 11. 配置项

集中在 `backend/app/core/config.py`：

```python
class PipelineSettings(BaseSettings):
    pipeline_version: str = "pipeline-v0.1.0"
    schema_version: str = "v0.1.0"

    # Reader
    max_file_size_mb: int = 50
    enable_ocr: bool = False  # v0.4+

    # Splitter
    section_dict_path: str = "app/pipeline/splitter/section_dict.yaml"
    chunk_max_tokens: int = 1500

    # TableExtractor
    table_match_threshold: int = 70

    # LLM Extractor
    llm_model_default: str = "claude-haiku-4-5"
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 3
    llm_max_prompt_tokens: int = 8000
    domain_lexicon_path: str = "app/lexicon/domain_lexicon.yaml"

    # Vectorizer
    enable_vectorizer: bool = False  # v0.2+
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024

    # Writer
    writer_batch_size: int = 100
    enforce_concept_existence: bool = True  # 概念节点不存在时跳过关系而不创建

    model_config = SettingsConfigDict(env_prefix="PIPELINE_")
```

---

## 12. 检查清单（Pipeline 实现完成时）

- [ ] 每个组件继承 PipelineComponent，输入输出严格遵循 Pydantic schema
- [ ] PipelineContext 在所有 stage 间正确传递
- [ ] 每个 stage 追加 StageMetric
- [ ] Reader 处理 PDF / DOCX / XLSX 三种格式
- [ ] Reader 完成全半角 / 重复列 / 占位符 / 图片引用清洗
- [ ] Splitter 章节字典从 YAML 加载
- [ ] Splitter 输出 chunk_id 确定性、可重现
- [ ] TableExtractor 5 类规则识别覆盖率 100%（基于两份样本）
- [ ] TableExtractor 不调用 LLM
- [ ] LLM Extractor 按 chunk_role 路由到不同子抽取器
- [ ] LLM Extractor 注入 domain_lexicon
- [ ] LLM Extractor 输出含 supporting_chunk_ids
- [ ] Finding 必含 polarity，准确率 ≥ 90%
- [ ] 因果链 v0.1 不自动建 LEADS_TO 边，仅 causal_narrative
- [ ] Writer 所有 Cypher 用 MERGE，幂等通过测试
- [ ] Writer 自动建立 MENTIONED_IN 双向边
- [ ] Writer 失败时事务回滚
- [ ] Celery 编排支持 chain + 重试 + 幂等保护
- [ ] pipeline_runs 表记录每次执行状态
- [ ] llm_usage_log 表记录每次 LLM 调用
- [ ] 单元测试覆盖率 ≥ 70%
- [ ] e2e 测试：上传两份样本 → 完整 Pipeline → 查询拿到预期实体

---

**文档版本**：v1.0（基于 PRD v1.5 / Schema v0.1.0）
**最后更新**：2026-05-07
**维护者**：项目团队
