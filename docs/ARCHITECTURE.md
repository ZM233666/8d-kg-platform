# ARCHITECTURE.md · 系统架构

**架构版本**：v0.1.0
**对应 PRD 版本**：v1.5
**对应 Schema 版本**：v0.1.0
**最后更新**：2026-05-07

本文档面向开发团队、运维、新加入的工程师，描述 8D 知识图谱平台的系统架构、模块边界、数据流、部署拓扑、关键技术决策。配合 `PRD.md`（产品需求）、`SCHEMA.md`（数据模型）、`PIPELINE.md`（组件契约）、`API.md`（接口契约）共同构成完整的设计文档。

---

## 1. 架构总览

### 1.1 系统视图

```
                  ┌──────────────────────────────────┐
                  │         浏览器（用户）            │
                  └───────────────┬──────────────────┘
                                  │ HTTPS
                  ┌───────────────▼──────────────────┐
                  │  Nginx / Ingress（反向代理 + TLS）│
                  └───────────────┬──────────────────┘
                                  │
        ┌─────────────────────────┴─────────────────────────┐
        │                                                   │
┌───────▼────────┐                                ┌─────────▼─────────┐
│  Frontend SPA  │                                │  Backend Gateway  │
│  React + Vite  │                                │     FastAPI       │
│  AntD + G6     │                                │  REST + WebSocket │
└────────────────┘                                └─────────┬─────────┘
                                                            │
            ┌───────────────────────────────────────────────┼───────────────────────┐
            │                                               │                       │
   ┌────────▼─────────┐    ┌──────────────────────┐  ┌──────▼────────┐  ┌──────────▼──────────┐
   │  Service 层       │    │   Pipeline 任务队列   │  │  Query Router │  │  Auth/Audit/Schema  │
   │  Documents/...   │    │      Celery + Redis   │  │  Cypher/Vec   │  │      Service        │
   └────────┬─────────┘    └──────────┬───────────┘  └──────┬────────┘  └──────────┬──────────┘
            │                         │                     │                       │
            └─────────────┬───────────┴────────┬────────────┴───────────┬───────────┘
                          │                    │                        │
                ┌─────────▼─────┐    ┌─────────▼──────┐      ┌──────────▼─────────┐
                │   PostgreSQL  │    │     Neo4j      │      │       MinIO        │
                │   + PGVector  │    │   Community    │      │   Object Storage   │
                └───────────────┘    └────────────────┘      └────────────────────┘

                                  ┌─────────────────────┐
                                  │ External Services   │
                                  │  LLM Gateway        │
                                  │  (OpenAI-compatible)│
                                  └─────────────────────┘
```

### 1.2 分层架构

系统按四层组织：

```
┌──────────────────────────────────────────────────────────────┐
│  表现层 (Presentation)                                        │
│  React SPA · 上传/任务/抽取结果/查询/图谱/反馈                │
├──────────────────────────────────────────────────────────────┤
│  应用层 (Application)                                         │
│  FastAPI · 路由/认证/权限/编排/查询路由/WebSocket             │
├──────────────────────────────────────────────────────────────┤
│  领域层 (Domain)                                              │
│  Pipeline 组件 · 服务 · 业务规则 · LLM 抽象 · Cypher 模板     │
├──────────────────────────────────────────────────────────────┤
│  基础设施层 (Infrastructure)                                  │
│  PostgreSQL · Neo4j · MinIO · Redis · Celery · LLM Gateway    │
└──────────────────────────────────────────────────────────────┘
```

层间约束：

- 上层只能依赖下层，不允许反向依赖
- 表现层不直接访问基础设施层
- 领域层不持有 HTTP 上下文（请求/响应对象）
- 基础设施细节（如 Neo4j Cypher、MinIO SDK）不泄漏到领域层之外

---

## 2. 模块边界

### 2.1 前端模块

```
frontend/src/
├── pages/                  # 页面级组件（路由入口）
│   ├── Login/
│   ├── DocumentList/       # 文档列表
│   ├── DocumentUpload/     # 上传页
│   ├── ExtractionResult/   # 抽取结果只读页
│   ├── EntityDetail/       # 实体详情
│   ├── QueryStructured/    # 结构化查询
│   ├── GraphView/          # 单报告子图
│   └── Admin/              # 管理后台
├── components/             # 通用组件
│   ├── DocumentPreview/    # PDF / Word 预览
│   ├── EntityCard/         # 实体卡片
│   ├── ChunkHighlight/     # Chunk 原文高亮
│   ├── G6Graph/            # G6 图谱封装
│   └── FeedbackButton/     # 错误反馈按钮
├── api/                    # API 客户端（TanStack Query）
│   ├── documents.ts
│   ├── extraction.ts
│   ├── entities.ts
│   ├── query.ts
│   └── graph.ts
├── stores/                 # Zustand 全局状态
│   ├── auth.ts
│   ├── ui.ts
│   └── pipeline.ts         # WebSocket 状态
├── types/
│   └── api.ts              # 由 openapi-typescript 自动生成（禁止手写）
├── utils/
└── App.tsx
```

**关键设计**：

- 服务端状态用 TanStack Query，禁止用 Zustand 缓存服务端数据
- 客户端 UI 状态（侧边栏开合等）用 useState；跨页面状态（用户信息、WebSocket 连接）用 Zustand
- 所有后端类型必须从 `types/api.ts` 引用，禁止手写

### 2.2 后端模块

```
backend/app/
├── api/                    # FastAPI 路由（薄层，仅做参数校验、调用 Service）
│   ├── auth.py
│   ├── documents.py
│   ├── pipeline.py
│   ├── extraction.py
│   ├── entities.py
│   ├── query.py
│   ├── graph.py
│   ├── feedback.py
│   ├── schema.py
│   ├── audit.py
│   ├── admin.py
│   ├── health.py
│   └── ws.py               # WebSocket
│
├── core/                   # 横切关注点
│   ├── config.py           # Pydantic Settings
│   ├── logging.py          # structlog 配置
│   ├── exceptions.py       # 业务异常基类
│   ├── deps.py             # FastAPI 依赖注入
│   ├── security.py         # JWT、密码哈希
│   ├── permissions.py      # require_object_access 装饰器
│   └── middleware.py       # 请求 trace_id、CORS、限流
│
├── models/                 # SQLAlchemy ORM
│   ├── base.py
│   ├── user.py
│   ├── document.py
│   ├── chunk.py
│   ├── entity_mirror.py
│   ├── pipeline_run.py
│   ├── llm_usage.py
│   ├── audit_log.py
│   └── feedback.py
│
├── schemas/                # Pydantic DTO（API 输入输出）
│   ├── auth.py
│   ├── document.py
│   ├── entity/             # 各 EntityType 的 Pydantic 模型（来自 SCHEMA.md）
│   ├── event/
│   ├── concept/
│   ├── extraction.py
│   ├── query.py
│   └── exported/           # 自动导出的 JSON Schema
│
├── services/               # 业务逻辑（无 HTTP 上下文）
│   ├── document_service.py
│   ├── pipeline_service.py
│   ├── extraction_service.py
│   ├── entity_service.py
│   ├── query_service.py
│   ├── graph_service.py
│   ├── feedback_service.py
│   └── schema_service.py
│
├── pipeline/               # 抽取链路
│   ├── base.py             # PipelineComponent / PipelineContext
│   ├── reader/
│   │   ├── pdf_reader.py
│   │   ├── docx_reader.py
│   │   ├── xlsx_reader.py
│   │   └── cleaner.py      # 清洗规则
│   ├── splitter/
│   │   ├── splitter.py
│   │   └── section_dict.yaml
│   ├── table_extractor/
│   │   ├── matchers/       # 5 类表格识别器
│   │   ├── mappings/       # YAML 字段映射
│   │   └── normalizer.py   # 数据规范化
│   ├── extractor/
│   │   ├── prompts/        # Jinja2 prompt 模板
│   │   ├── defect.py
│   │   ├── inspection.py
│   │   ├── root_cause.py
│   │   ├── action.py
│   │   ├── risk.py
│   │   └── router.py       # 按 chunk_role 路由
│   ├── vectorizer/         # v0.2 启用
│   └── writer/
│       ├── writer.py
│       ├── cypher_templates.py
│       └── tx_coordinator.py  # PG + Neo4j 跨库事务协调
│
├── graph/                  # Neo4j 适配层
│   ├── client.py
│   ├── cypher/             # 复用 Cypher 模板
│   └── schema_init.py      # 启动时建立约束/索引
│
├── llm/                    # LLM 抽象层（强制经过此层）
│   ├── client.py           # OpenAI-compatible 客户端
│   ├── instructor_wrapper.py
│   ├── usage_logger.py     # 写入 llm_usage_log
│   └── retry.py
│
├── lexicon/                # 领域词典加载器
│   ├── domain_lexicon.yaml # （已存在）
│   └── loader.py
│
├── tasks/                  # Celery 任务
│   ├── celery_app.py
│   └── pipeline_tasks.py
│
├── ws/                     # WebSocket 管理
│   ├── manager.py
│   └── pipeline_channel.py
│
└── main.py                 # FastAPI 入口
```

### 2.3 模块依赖规则

允许的依赖方向：

```
api → services → pipeline / graph / llm → models / schemas
api → schemas（仅校验）
core 可以被任何模块依赖
tasks → services → pipeline
ws → services
```

禁止：

- `pipeline` 直接调用 `api` 层
- `models` 依赖 `schemas` 或 `services`
- `services` 直接持有 FastAPI Request/Response 对象
- 任何业务模块绕过 `llm/` 直接调 OpenAI/Anthropic SDK

### 2.4 模块职责一句话

| 模块 | 职责 |
|---|---|
| `api/` | HTTP 路由、参数校验、权限检查；不写业务逻辑 |
| `core/` | 配置、日志、异常、依赖注入、中间件 |
| `models/` | SQLAlchemy ORM，仅描述数据结构 |
| `schemas/` | Pydantic DTO，API 边界 + Pipeline 边界 |
| `services/` | 业务逻辑、跨组件编排（同步） |
| `pipeline/` | 文档处理链路（异步，受 Celery 调度） |
| `graph/` | Neo4j 客户端封装、Cypher 模板 |
| `llm/` | LLM 调用统一入口，含计量、重试、限流 |
| `lexicon/` | 领域词典加载 |
| `tasks/` | Celery 任务定义与编排 |
| `ws/` | WebSocket 连接池与消息分发 |

---

## 3. 数据流

### 3.1 文档上传 + 抽取（核心流程）

```
用户                Frontend           Backend API         Service           Celery            Pipeline           Storage
 │                     │                   │                  │                 │                 │                  │
 ├─上传 PDF/DOCX──────▶│                   │                  │                 │                 │                  │
 │                     ├─POST /documents──▶│                  │                 │                 │                  │
 │                     │                   ├──validate hash──▶│                 │                 │                  │
 │                     │                   │◀──duplicate?─────┤                 │                 │                  │
 │                     │                   ├──put_object──────────────────────────────────────────────────────────▶│ MinIO
 │                     │                   ├──insert document_meta──────────────────────────────────────────────▶│ PG
 │                     │                   ├──enqueue pipeline──────────────▶│                 │                  │
 │                     │◀──201 doc_id──────┤                  │                 │                 │                  │
 │                     │                   │                  │                 ├─task_read──────▶ Reader            │
 │                     ├─WS /ws/pipeline──▶│                  │                 │                 ├─读 MinIO──────▶ │
 │                     │◀─ stage_started ──┤                  │                 │                 │                  │
 │                     │                   │                  │                 │                 ├─Splitter         │
 │                     │                   │                  │                 │                 ├─TableExtractor   │
 │                     │                   │                  │                 │                 ├─LLM Extractor───▶│ LLM Gateway
 │                     │                   │                  │                 │                 │◀──structured────│
 │                     │                   │                  │                 │                 ├─Vectorizer (v0.1 noop)
 │                     │                   │                  │                 │                 ├─Writer──────────▶│ PG (entity_mirror)
 │                     │                   │                  │                 │                 │                  ├▶Neo4j (MERGE)
 │                     │◀─ stage_completed ┤                  │                 │                 │                  │
 │                     │◀─ pipeline_done ──┤                  │                 │                 │                  │
 │                     │                   │                  │                 │                 │                  │
```

**关键时序点**：

1. **同步阶段**（API 路由内）：file hash 校验 → MinIO 持久化 → 写 documents 表 → 入队 → 立即返回 doc_id
2. **异步阶段**（Celery worker）：6 个 stage 顺序执行；每 stage 开始/结束推 WebSocket
3. **失败处理**：任一 stage 抛 FatalPipelineError 整体失败，标记 documents.pipeline_status；PartialPipelineError 记入 stage_metrics 但继续后续 stage

### 3.2 查询数据流（v0.1 结构化）

```
用户        Frontend       API          QueryService        Cypher         Neo4j         PG
 │            │             │                │                │             │             │
 ├─发起查询───▶│            │                │                │             │             │
 │            ├─POST query─▶│                │                │             │             │
 │            │             ├─权限过滤──────▶│                │             │             │
 │            │             │                ├─选择模板──────▶│             │             │
 │            │             │                ├─参数绑定──────▶│             │             │
 │            │             │                │                ├─执行────────▶│             │
 │            │             │                │                │◀─节点列表───┤             │
 │            │             │                ├─批量取 chunk──────────────────────────────▶│
 │            │             │                │◀─chunk 数据────────────────────────────────┤
 │            │             │                ├─组装响应──────▶│                            │
 │            │             ├─结果─────────◀─┤                                            │
 │            ├─渲染列表─◀──┤                                                              │
```

### 3.3 子图查询数据流

```
Frontend ──GET /graph/report/{id}──▶ GraphService
                                          │
                                          ├─权限检查
                                          ├─构造单跳 Cypher（含 WHERE source_doc_id=...）
                                          ├─执行 → 节点 + 关系
                                          ├─按 max_nodes 截断（保留高 confidence）
                                          ├─按 entity_type / confidence 计算 style_hint
                                          └─返回 G6 兼容格式
```

### 3.4 数据生命周期

```
上传 → MinIO 永久存储（受保留策略约束）
  │
  └─解析 → PG (chunks 表) + Neo4j (Chunk 节点)
        │
        ├─表格抽取 → PG (entity_mirror) + Neo4j (实体节点)
        │
        └─LLM 抽取 → PG (entity_mirror) + Neo4j (实体节点 + 关系)
                  │
                  ├─审计 → PG (audit_log)
                  │
                  └─LLM 调用 → PG (llm_usage_log)
```

删除文档（DELETE /documents/{id}）级联清理 MinIO 对象、PG 相关表、Neo4j 按 source_doc_id 过滤的节点。审计日志保留。

---

## 4. 关键技术决策

### 4.1 为什么 PostgreSQL + Neo4j 双库？

| 维度 | PostgreSQL | Neo4j |
|---|---|---|
| 元数据、staging、Chunk 全文 | ✓ | — |
| 任意深度图查询 | 慢且复杂 | 原生支持 |
| 向量检索 | PGVector 够用到百万级 | 无原生向量 |
| 事务保证 | 强 | 强（单库内） |
| 运维熟悉度 | 高 | 中 |

**决策**：双库各司其职，通过 `node_id` 同步。`entity_mirror` 表是 Neo4j 节点的镜像，方便审计、回溯、staging。

**风险**：跨库事务用"先 PG 后 Neo4j"两阶段策略，PG 成功但 Neo4j 失败时标记 `pipeline_status=neo4j_failed` 由后台任务重试。v0.1 容忍最终一致。

### 4.2 为什么 Celery 而非 Temporal/Prefect？

- v0.1 流程线性、节点少（6 个 stage），Celery 足够
- Celery 运维成熟、社区生态完整
- 切换成本可接受：v0.4+ 若需要复杂工作流（重抽 + 回滚 + 审批），再迁 Temporal

### 4.3 为什么 TableExtractor 走规则不走 LLM？

两份样本中表格字段抽取是高 ROI 但低难度的活：

- 故障清单表、项目简介表、团队表都是确定性结构
- pandas + 表头白名单可达 95%+ 准确率
- 零 token 成本、毫秒级响应
- 可解释性强，调试简单

LLM 仅用于规则失败时的兜底（unrouted_tables）。

### 4.4 为什么因果链 v0.1 仅 narrative + 扁平节点？

LLM 对因果顺序的抽取容易错乱（样本二的 7 步链路任何一步错位就不可用）。v0.1 折中方案：

- Schema 完整支持 LEADS_TO 边（不返工）
- LLM 只输出扁平 RootCause + 完整因果叙述文本
- v0.2 审核员人工连边，同时积累训练数据
- v0.3 启用自动抽取（调优 prompt 或微调）

### 4.5 为什么 v0.1 不做向量检索？

向量检索的价值在数据量上来后才显著（>100 篇报告）。v0.1 数据量 ≤ 20 篇，结构化查询 + 全文搜索足够覆盖 80% 场景。Vectorizer 实现 noop 但保持接口契约，v0.2 平滑启用。

### 4.6 为什么 LLM 必须经过 `app/llm/` 抽象层？

- 统一记录 token 消耗、成本归因
- 统一重试、超时、限流
- 模型切换（Claude / GPT / 本地 vLLM）只改一处
- 评测时可 mock LLM 调用

任何业务模块绕过此层调用 SDK 即视为违规（CI 静态检查）。

### 4.7 为什么前端用 React + AntD 而非 Vue？

- React 生态对 G6/G6Plus、AntV 系列支持更完整
- ProComponents（ProForm/ProTable）覆盖 80% 表单/列表场景，减少自研
- TanStack Query + Zustand 是当前社区最稳的服务端/客户端状态分层方案
- 团队熟悉度也是关键考量

### 4.8 为什么不引入 GraphQL？

- v0.1 接口数量有限（~30 个），REST + OpenAPI 自动生成 TS 类型已足够
- Neo4j Cypher 已是图查询语言，再叠加 GraphQL 增加复杂度
- 后续若需要灵活查询，考虑提供 Cypher API（仅 admin）而非 GraphQL

---

## 5. 部署架构

### 5.1 v0.1 单机部署（docker-compose）

```
┌────────────────────────────────────────────────────┐
│              Single Host (Linux, ≥8 vCPU, 16GB)    │
│                                                    │
│  ┌──────────────────────────────────────────────┐  │
│  │              docker-compose                  │  │
│  │                                              │  │
│  │  ┌──────────┐  ┌──────────┐  ┌────────────┐  │  │
│  │  │ frontend │  │ backend  │  │ celery     │  │  │
│  │  │ nginx    │  │ FastAPI  │  │ worker x2  │  │  │
│  │  │ :80      │  │ :8000    │  │            │  │  │
│  │  └──────────┘  └──────────┘  └────────────┘  │  │
│  │                                              │  │
│  │  ┌──────────┐  ┌──────────┐  ┌────────────┐  │  │
│  │  │PostgreSQL│  │  Neo4j   │  │   MinIO    │  │  │
│  │  │ :5432    │  │ :7687    │  │   :9000    │  │  │
│  │  └──────────┘  └──────────┘  └────────────┘  │  │
│  │                                              │  │
│  │  ┌──────────┐                                │  │
│  │  │  Redis   │                                │  │
│  │  │  :6379   │                                │  │
│  │  └──────────┘                                │  │
│  └──────────────────────────────────────────────┘  │
│                                                    │
│  Volumes: pg_data, neo4j_data, minio_data,         │
│           redis_data, uploads_temp                 │
└────────────────────────────────────────────────────┘
                       │
                       │ HTTPS (外部)
                       ▼
              ┌──────────────────┐
              │  LLM Gateway     │
              │ (Claude/GPT API) │
              └──────────────────┘
```

**资源建议**：

| 服务 | CPU | 内存 | 磁盘 |
|---|---|---|---|
| backend (FastAPI) | 2 | 2 GB | — |
| celery worker × 2 | 2 × 2 | 2 × 2 GB | — |
| PostgreSQL | 1 | 2 GB | 50 GB SSD |
| Neo4j | 1 | 2 GB | 30 GB SSD |
| MinIO | 0.5 | 1 GB | 100 GB |
| Redis | 0.5 | 512 MB | — |
| frontend (nginx) | 0.5 | 256 MB | — |

总计：约 7 vCPU / 12 GB 内存 / 200 GB 磁盘。

### 5.2 v0.4+ 生产部署（Kubernetes）

```
┌──────────────────────────── Kubernetes Cluster ────────────────────────────┐
│                                                                            │
│  ┌─────────────┐    ┌──────────────────────────────────────────────────┐   │
│  │  Ingress    │───▶│  Service: backend (3 replicas)                   │   │
│  │   nginx     │    │  Service: frontend (2 replicas)                  │   │
│  └─────────────┘    │  Service: celery-worker (5 replicas, HPA)        │   │
│                     │  Service: celery-beat (1 replica, leader)        │   │
│                     └──────────────────────────────────────────────────┘   │
│                                                                            │
│  ┌──────────────────────── StatefulSets ──────────────────────────────┐    │
│  │  PostgreSQL (Primary + 1 Replica)                                  │    │
│  │  Neo4j Community (single instance, snapshot backup)                │    │
│  │  MinIO (4-node distributed)                                        │    │
│  │  Redis (sentinel: 1 master + 2 replica)                            │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                                                                            │
│  ┌──────────────────────── 可观测性 ────────────────────────────────┐      │
│  │  OpenTelemetry Collector → Tempo / Prometheus / Loki              │      │
│  │  Grafana 仪表盘                                                   │      │
│  └──────────────────────────────────────────────────────────────────┘      │
└────────────────────────────────────────────────────────────────────────────┘
```

**关键变更（vs v0.1 单机）**：

- 后端、worker、frontend 用 Deployment + HPA
- 数据库走 StatefulSet + PVC
- Neo4j v0.1 用社区版单机，v0.6+ 数据量大时再考虑企业版集群
- 通过 Secret 管理 LLM API Key、DB 密码
- Helm Chart 统一发布

### 5.3 网络拓扑

```
                    Internet
                       │
                  [WAF / CDN]              （可选）
                       │
                  [Ingress + TLS]
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
   /api/*         /static/*       /ws/*
   backend        frontend        backend
        │
        ├─→ PostgreSQL (内网)
        ├─→ Neo4j (内网)
        ├─→ MinIO (内网, presigned URL 走外网)
        ├─→ Redis (内网)
        └─→ LLM Gateway (外网，HTTPS + API Key)
```

---

## 6. 横切关注点

### 6.1 认证授权

```
请求 ──▶ JWT 中间件 ──▶ require_login ──▶ require_object_access ──▶ 路由 handler
                              │                    │
                              │                    └─ 检查 owner_id == self.user_id 或 role=admin
                              │
                              └─ 解析 user_id, role, 注入 ctx
```

- Token 存浏览器 localStorage（v0.1 简化），v0.4+ 改 httpOnly Cookie
- 所有写操作在审计中间件内记录到 `audit_log` 表
- 公开数据（sensitivity=public）跳过 owner 检查

### 6.2 错误处理

统一异常处理器（`core/middleware.py`）：

```
PipelineError → 4xx 业务错误响应
SQLAlchemyError → 500 + 隐藏堆栈（生产）
Neo4jError → 502
LLMError → 502 LLM_UPSTREAM_ERROR
RateLimitError → 429
其他 Exception → 500 INTERNAL_ERROR
```

所有错误响应必含 `trace_id` 用于排查。

### 6.3 日志

- **应用日志**：structlog → stdout（JSON 格式）→ docker logs / Loki
- **审计日志**：audit_log 表，永久保留
- **LLM 调用日志**：llm_usage_log 表
- **Pipeline 运行日志**：pipeline_runs 表

每条日志带 `trace_id`、`doc_id`、`user_id`、`stage`、`component_version`，便于跨系统串联。

### 6.4 配置管理

- 单一来源：`backend/app/core/config.py` 的 Pydantic Settings
- 环境变量 > .env 文件 > 默认值
- 敏感配置（API Key、DB 密码）只走环境变量，禁止入仓
- 所有模块禁止散落 `os.getenv`，必须从 settings 读取

### 6.5 限流

- 应用层（slowapi）：按用户限速（见 API.md §1.10）
- LLM 层：内部限流避免上游限流（按 model + provider 分桶）
- 数据库连接池：PostgreSQL pool_size=10, Neo4j max_connection_lifetime=3600

### 6.6 缓存

| 缓存对象 | 位置 | TTL |
|---|---|---|
| Schema 类型清单 | 内存 LRU | 进程生命周期 |
| 领域词典 | 内存 | 启动加载，热更新需重启 |
| 查询模板结果（高频） | Redis | 60s |
| MinIO presigned URL | 不缓存 | — |
| JWT 黑名单 | Redis | token 剩余有效期 |

v0.1 缓存策略保守。v0.5+ 引入查询答案缓存。

### 6.7 可观测性

- v0.1：structlog + 数据库表（pipeline_runs / llm_usage_log）足以排查
- v0.3+：接入 OpenTelemetry，trace 全链路（API → Celery → Pipeline → DB）
- 关键指标：
  - 各 stage 耗时 P50/P95/P99
  - Pipeline 成功率（按 stage、按错误类型）
  - LLM token 消耗 / 成本
  - 查询延迟分布
  - 实体抽取准确率（CI 跑评测自动上报）

---

## 7. 关键时序图

### 7.1 上传 + 自动触发 Pipeline

```
User    Frontend    Backend    PG      MinIO    Redis    Celery   Pipeline   Neo4j   LLM
  │        │          │         │        │        │        │         │         │       │
  ├─选择文件─▶│         │         │        │        │        │         │         │       │
  │        ├──hash──▶│         │        │        │        │         │         │       │
  │        │          ├──查重─▶│        │        │        │         │         │       │
  │        │          │◀─新文件┤        │        │        │         │         │       │
  │        │          ├─上传─────────────▶        │        │         │         │       │
  │        │          ├─插入元数据─▶│        │        │        │         │         │       │
  │        │          ├─入队─────────────────────────▶│        │         │         │       │
  │        │◀─201 doc_id┤         │        │        │        │         │         │       │
  │        ├─WS 订阅─▶│         │        │        │        │         │         │       │
  │        │          │         │        │        │        ├──pull───▶│         │       │
  │        │          │         │        │        │        │         ├─读 MinIO──▶       │
  │        │          │         │        │◀──────────────────────────┤         │       │
  │        │          │         │        │        │        │         ├─chunks→PG       │
  │        │          │         │        │        │        │         ├─表格规则           │
  │        │          │         │        │        │        │         ├─LLM 抽取─────────▶│
  │        │          │         │        │        │        │         │◀─结构化响应──────┤
  │        │          │         │        │        │        │         ├─Writer→PG       │
  │        │          │         │        │        │        │         ├─Writer→Neo4j────▶│
  │        │◀ WS stage_completed×N ────────────────────────────────────┤         │       │
  │        │◀ WS pipeline_completed ─────────────────────────────────────┤         │       │
  │        ├─跳转结果页─────────────────▶│        │        │         │         │       │
  │        ├─GET /extraction─▶│        │        │        │         │         │       │
  │        │          ├─聚合查询─▶│        │        │        │         │         │       │
  │        │◀─完整抽取数据────┤         │        │        │         │         │       │
```

### 7.2 结构化查询

```
User    Frontend    Backend    QuerySvc    Neo4j    PG
  │        │          │           │           │        │
  ├─输入条件─▶│         │           │           │        │
  │        ├─POST /query/structured─▶│           │        │
  │        │          ├─权限过滤──▶│           │        │
  │        │          │           ├─选模板──▶ │        │
  │        │          │           ├─参数绑定─▶│        │
  │        │          │           ├─执行 Cypher──▶│   │
  │        │          │           │◀─节点列表────┤   │
  │        │          │           ├─批量取 chunk──────────▶│
  │        │          │           │◀──chunk 数据────────────┤
  │        │          ├─结果─◀───┤           │        │
  │        ├─渲染列表─◀──┤        │           │        │
  │        ├─点击实体─▶│         │           │        │
  │        ├─GET /entities/{id}/neighbors─▶│           │
  │        │          ├─图扩展─▶│           ├─Cypher──▶│
  │        │◀─邻居子图────┤    │           │◀─────────┤
```

---

## 8. 演进路线（架构层面）

| 版本 | 架构关键变化 |
|---|---|
| v0.1 | 单机 docker-compose；Celery 串行 Pipeline；规则 + LLM 抽取 |
| v0.2 | PGVector 启用；Vectorizer 真实运行；审核子系统进入；entity_staging 表 |
| v0.3 | OpenIE 双轨抽取（Pipeline 节点增加）；Aligner 服务；OTel 接入 |
| v0.4 | 引入 NL Query Service（独立模块）；K8s 部署；SSO；脱敏中间件 |
| v0.5 | LF-Solver 服务；分析仪表盘（独立查询服务）；物化视图 |
| v0.6+ | 多租户（PG schema 隔离 + Neo4j label）；Temporal 替换 Celery（如需要） |

---

## 9. 风险与缓解（架构层面）

| 风险 | 影响 | 缓解 |
|---|---|---|
| 跨库一致性（PG ↔ Neo4j）| 数据不一致 | 写入顺序固定 + 失败重试 + entity_mirror 镜像表 |
| Neo4j 单点故障 | 服务不可用 | v0.1 接受；v0.4+ 上 Causal Cluster 或 Neo4j Aura |
| LLM 上游限流/故障 | Pipeline 卡住 | 重试 + 降级（失败 chunk 入 failed_items 不阻塞）+ 多 provider 切换 |
| 大文件解析 OOM | worker 崩溃 | 文件大小硬限 50MB；v0.4+ 流式解析 |
| 文档数据增长 | Neo4j/PG 性能下降 | 定期归档（v0.5+）；监控查询慢 |
| 前端图谱节点过多 | 浏览器卡死 | 服务端 max_nodes 截断；前端虚拟化（v0.5+） |
| Celery 任务丢失 | Pipeline 永久 pending | 任务持久化到 Redis AOF；超时重试；定期巡检 pipeline_runs |

---

## 10. 参考

- 项目方案：`docs/PRD.md`
- 数据模型：`docs/SCHEMA.md`
- 组件契约：`docs/PIPELINE.md`
- 接口契约：`docs/API.md`
- 系统指令：`CLAUDE.md`

---

**文档版本**：v1.0（基于 PRD v1.5）
**最后更新**：2026-05-07
**维护者**：项目团队
