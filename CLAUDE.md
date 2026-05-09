# CLAUDE.md

本文件是 Claude Code 在本仓库工作时的系统级指令。每次开始新任务前必须阅读本文件以及 `docs/` 目录下的相关文档。

---

## 1. 项目概述

**项目名**：8D 报告知识图谱平台
**目标**：将质量管理领域的 8D 报告通过 `Reader → Splitter → TableExtractor → LLM Extractor → Vectorizer → Writer` 链路转化为可查询的知识图谱，提供前后端完整闭环。
**当前阶段**：MVP v0.1（详见 `docs/PRD.md`）
**完整方案**：见 `docs/PRD.md`（v1.5）

核心场景：
- 历史相似 8D 案例快速检索
- 根因-对策证据沉淀
- 跨项目质量趋势分析
- 验证型实验复用

---

## 2. 技术栈（强制）

未经用户明确同意，**禁止引入本节未列出的依赖**。

### 2.1 后端

- Python 3.11+
- FastAPI（REST + WebSocket）
- SQLAlchemy 2.0（ORM，必须用 2.0 风格 `select()`，禁止 1.x `Query`）
- Pydantic v2（**禁止使用 v1 API**，如 `BaseModel.dict()`、`Config` class，应使用 `model_dump()`、`model_config`）
- Alembic（数据库迁移）
- Celery + Redis（异步任务）
- instructor（LLM 结构化输出）
- httpx（HTTP 客户端）
- pytest + pytest-asyncio（测试）

### 2.2 存储

- PostgreSQL 15+（元数据、staging、Chunk）
- PGVector（HNSW，向量检索，v0.2 启用）
- Neo4j Community 5.x（知识图谱，使用 `neo4j` 官方 Python driver，**禁止 py2neo**）
- MinIO（对象存储，使用 `minio` SDK 或 boto3）
- Redis 7+（缓存、队列、分布式锁）

### 2.3 前端

- Node 20+
- React 18 + TypeScript 5+
- Vite 5+
- Ant Design 5 + ProComponents（**优先使用 ProForm / ProTable，避免自研同等组件**）
- AntV G6 v5（图谱可视化）
- TanStack Query v5（服务端状态）
- Zustand（客户端状态）
- react-pdf + mammoth.js（文档预览）

### 2.4 文档解析

- PDF：PyMuPDF（fitz）+ pdfplumber
- Word：python-docx + unstructured
- Excel：openpyxl
- 表格：pandas（TableExtractor 核心）
- OCR：v0.4+ 才引入 PaddleOCR，v0.1 不做 OCR

### 2.5 LLM / Embedding

- LLM 统一走 OpenAI-compatible 接口，不直接耦合具体厂商
- Embedding：bge-m3 或 bge-large-zh
- Reranker：bge-reranker-v2（v0.2+）

---

## 3. 仓库目录约定

```
8d-kg-platform/
├── CLAUDE.md                      # 本文件
├── README.md
├── docker-compose.yml
├── .env.example
├── docs/
│   ├── PRD.md                     # 项目方案 v1.5
│   ├── ARCHITECTURE.md
│   ├── SCHEMA.md                  # 8D 本体定义
│   ├── PIPELINE.md                # Pipeline 各组件契约
│   ├── API.md                     # REST 接口清单
│   └── CODING_STANDARDS.md
├── backend/
│   ├── app/
│   │   ├── api/                   # FastAPI 路由
│   │   ├── core/                  # 配置、日志、依赖注入、异常
│   │   ├── models/                # SQLAlchemy ORM
│   │   ├── schemas/               # Pydantic DTO
│   │   ├── services/              # 业务逻辑
│   │   ├── pipeline/              # Reader/Splitter/TableExtractor/Extractor/Vectorizer/Writer
│   │   │   ├── reader/
│   │   │   ├── splitter/
│   │   │   ├── table_extractor/
│   │   │   ├── extractor/
│   │   │   ├── vectorizer/
│   │   │   └── writer/
│   │   ├── graph/                 # Neo4j 客户端、Cypher 模板
│   │   ├── llm/                   # LLM 抽象层（必须经过此层）
│   │   ├── tasks/                 # Celery tasks
│   │   └── lexicon/               # domain_lexicon.yaml
│   ├── tests/
│   ├── alembic/
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   ├── api/                   # 接口封装（推荐 openapi-typescript 自动生成）
│   │   ├── stores/
│   │   ├── types/
│   │   └── utils/
│   ├── package.json
│   └── vite.config.ts
└── eval/
    ├── datasets/                  # 评测数据集
    ├── scripts/                   # F1 / Recall@K 等指标计算
    └── reports/
```

新文件必须放在以上目录中，禁止在根目录乱放代码。

---

## 4. 编码规范

### 4.1 Python

- 格式化：ruff format（行宽 100）
- 静态检查：ruff + mypy（strict 模式）
- 类型注解：所有函数签名必须有完整类型注解
- 异步优先：所有 IO 操作使用 `async def`，禁止在 async 函数中调用阻塞 IO
- 异常处理：禁止裸 `except:`，必须指定异常类型；业务异常继承 `app/core/exceptions.py` 中的基类
- 日志：使用 `structlog`，禁止 `print`
- 配置：通过 `app/core/config.py` 的 Pydantic Settings 读取，禁止散落 `os.getenv`

### 4.2 TypeScript

- 格式化：Prettier
- 静态检查：ESLint（airbnb-typescript 规则）
- 严格模式：`tsconfig.json` 必须开启 `strict: true`
- API 类型：通过 openapi-typescript 从后端 OpenAPI 生成，**禁止手写后端 DTO 类型**
- 状态管理：服务端状态用 TanStack Query，UI 局部状态用 useState，跨页面状态用 Zustand

### 4.3 命名

- Python：模块/函数 `snake_case`，类 `PascalCase`，常量 `UPPER_SNAKE`
- TypeScript：组件 `PascalCase.tsx`，hooks `useXxx.ts`，工具函数 `camelCase`
- 数据库表：`snake_case` 复数（如 `eight_d_reports`、`chunks`）
- Neo4j 节点：`PascalCase`（如 `EightDReport`、`Part`）；关系：`UPPER_SNAKE`（如 `LEADS_TO`）

---

## 5. 强制约束（必须遵守）

### 5.1 LLM 调用

- **所有 LLM 调用必须经过 `app/llm/` 抽象层**，禁止业务代码直接调用 OpenAI/Anthropic SDK
- 必须记录 token 消耗、模型名、调用方、关联文档/任务到 `llm_usage_log` 表
- 必须支持失败重试（exponential backoff）和超时
- 结构化输出统一使用 instructor + Pydantic schema

### 5.2 图谱写入

- 所有写 Neo4j 操作必须**幂等**：使用 `MERGE` + 业务键，禁止裸 `CREATE`
- 必须记录完整溯源字段：`source_doc_id`、`source_chunk_id`、`source_section`、`confidence`、`extraction_version`、`schema_version`
- 必须建立 `MENTIONED_IN` 双向边（实体 ↔ Chunk）
- 必须写审计日志（`audit_log` 表）

### 5.3 实体公共属性

每个图谱节点必须包含：

```python
supporting_chunks: list[str]
description: str | None
summary: str | None
source_doc_id: str
source_section: list[str]
confidence: float
extraction_version: str
schema_version: str
review_status: Literal["auto_committed", "pending_review", "approved", "rejected"]
owner_id: str
sensitivity: Literal["public", "restricted", "confidential"]
created_at: datetime
updated_at: datetime
```

### 5.4 占位符过滤

Reader 层必须识别以下占位符并标记 `is_placeholder=True`，**禁止入图**：

`TBD`、`tbd`、`xxx`、`XXX`、`待定`、`需增加内容`、`N/A`、`n/a`、`/`、`-`、空字符串

### 5.5 前后端类型对齐

- 后端启动时自动生成 OpenAPI 到 `frontend/openapi.json`
- 前端通过 `npm run gen:api` 由 openapi-typescript 生成 `frontend/src/types/api.ts`
- 禁止手写后端返回的 DTO 类型

### 5.6 测试要求

- 所有新增业务代码必须有 pytest 单元测试，覆盖率 ≥70%
- Pipeline 各组件必须有契约测试（输入/输出符合 Pydantic schema）
- 关键路径必须有 e2e 测试（上传一份样本 → 查询拿到预期实体）

---

## 6. 禁止事项

- **禁止** 在 v0.1 实现以下功能（属于后续版本）：OCR、批量上传、双轨 OpenIE 抽取、向量检索、自然语言问答、Text-to-Cypher、人工审核 UI、PartType/PartInstance 拆分、因果链自动抽取、多租户、SSO、在线 Ontology 编辑
- **禁止** 引入未在第 2 节列出的依赖（如需要请先在 PR 中说明理由）
- **禁止** 直接修改 `docs/PRD.md`（这是产品需求文档，由用户维护）
- **禁止** 在代码中硬编码 LLM 模型名、密钥、URL，必须走配置
- **禁止** 跳过测试直接合并代码
- **禁止** 在 ORM 中使用同步 Session（必须 `AsyncSession`）
- **禁止** 用 `requests` 库（用 `httpx`）
- **禁止** 用 print 输出日志
- **禁止** 用 Pydantic v1 API
- **禁止** 一次性生成大量代码而不分模块测试，应分阶段提交

---

## 7. 工作流程

### 7.1 接到任务时

1. 先阅读 `docs/PRD.md` 中相关章节
2. 阅读 `docs/SCHEMA.md` / `docs/PIPELINE.md` / `docs/API.md` 中相关定义
3. 检查现有代码是否已有类似实现（避免重复造轮子）
4. 提出实现方案 + 涉及的文件清单 + 测试计划，等用户确认后再写代码

### 7.2 写代码时

1. 一次只做一件事，单次提交不超过 ~500 行新代码
2. 先写 Pydantic schema / SQLAlchemy model，再写 service，再写 API
3. 同步写 pytest 测试
4. 用到新依赖时先在 `pyproject.toml` / `package.json` 声明，并在回复中说明引入原因
5. 修改数据库 schema 必须同时生成 Alembic migration

### 7.3 完成后

1. 运行 `ruff check` + `mypy` + `pytest`，确保全部通过
2. 简要总结：新增/修改的文件、关键决策、潜在风险、测试覆盖情况
3. 如发现 PRD/Schema/Pipeline 文档与实现不一致，**主动指出**而不是擅自修改文档

### 7.4 不确定时

- 优先询问用户，而不是自行假设
- 提供 2-3 个备选方案 + 各自的权衡
- 如必须做假设，在回复中明确标注"假设：xxx"

---

## 8. MVP v0.1 范围速查

### 8.1 必做

- 文档上传（PDF/Word，单文件）
- Reader：占位符识别、图片引用标记、表格列归一
- Splitter：章节路由 + 嵌套 + chunk_role 标记
- TableExtractor：5 类表格规则解析（项目简介/变更记录/团队/故障清单/测量结果）
- LLM Extractor：按章节路由 + 否定语义识别 + 领域词典注入
- 因果链 Schema 完整支持，但 LLM 仅输出扁平 RootCause + causal_narrative
- Writer：幂等写入 + 双向边 + 审计日志
- 查询：结构化筛选 + 实体详情 + 原文回溯
- 单报告子图可视化（G6）
- 基础权限（用户名密码 + 两角色）
- LLM token 计量
- 评测骨架 + domain_lexicon.yaml

### 8.2 不做（v0.2+）

详见 PRD `9. 版本路线图`。

### 8.3 评测目标

| 字段类别 | v0.1 目标 |
|---|---|
| 表格直读字段 | F1 ≥ 95% |
| 半结构化字段 | F1 ≥ 80% |
| 叙述抽取字段 | F1 ≥ 65% |
| 加权整体 | F1 ≥ 75% |

---

## 9. 关键术语字典

- **8D 报告**：质量管理领域的标准问题解决报告，包含 D1-D8 八个步骤
- **EightDReport / DefectOccurrence / RootCause / Action**：核心实体类型，详见 `docs/SCHEMA.md`
- **chunk**：原文片段，id 格式 `report_id#section_path#para_idx`
- **chunk_role**：`background` / `evidence` / `hypothesis` / `conclusion` / `action`
- **closure_status**：报告状态，`open` / `closed` / `partially_closed` / `root_cause_unidentified`
- **polarity**：Finding 极性，`positive`（存在）/ `negative`（不存在/排除）/ `neutral`
- **causal_narrative**：v0.1 中存储 LLM 抽取的因果链文本描述，等待 v0.2 人工补边
- **MENTIONED_IN**：实体 ↔ Chunk 的双向边，互索引核心
- **auto_committed**：v0.1 抽取结果直接入图的 review_status 标记

---

## 10. 参考资源

- 项目方案：`docs/PRD.md`
- KAG Paper：<https://arxiv.org/abs/2409.13731>
- OpenSPG：<https://github.com/OpenSPG/openspg>
- KAG（可复用 Apache-2.0 资产）：<https://github.com/OpenSPG/KAG>
  - `kag/builder/prompt/spg_prompt.py`
  - `kag/builder/component/aligner/`
  - `kag/schema/`

---

## 11. 沟通约定

- 回复使用中文（除非代码/注释）
- 代码注释统一中文，但函数 docstring 推荐英文（便于 IDE 显示）
- 不确定的事必须问，不要编造接口/字段名
- 所有"假设"必须在回复中显式标注
- 提交前自我审查：是否引入了未列出的依赖？是否绕过了 LLM 抽象层？是否漏了溯源字段？是否漏了测试？

---

**文档版本**：v1.0（基于 PRD v1.5）
**最后更新**：2026-05-07
