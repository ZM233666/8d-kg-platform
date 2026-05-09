# 8D 报告知识图谱平台 · 项目方案 v1.5

**文档版本**：v1.5
**最后更新**：2026-05-07
**变更摘要**：基于两份真实 8D 样本（弹簧断裂、EP2002 阀压力超差）的分析，新增章节路由、TableExtractor、占位符识别、因果链结构、扩展 Schema（Measurement 三元组、Experiment、RiskAssessment、Finding 极性等）；MVP 工期由 6 周调整为 8-9 周。
**文件路径**：docs/PRD.md

---

## 1. 项目定位

将质量管理领域的 8D 报告通过 `Reader → Splitter → Extractor → Aligner → Vectorizer → Writer` 链路转化为可查询的知识图谱，支撑以下核心场景：

- 历史相似案例快速检索（部件/失效模式/根因）
- 根因-对策证据沉淀与复用
- 跨项目质量趋势分析
- 验证型实验复用（避免重复造轮子）

整体提供前后端完整闭环：文档上传、章节切分、实体抽取、人工审核（v0.2+）、写入图谱、多模式查询、子图可视化。

---

## 2. 设计参考与自研策略

借鉴 OpenSPG / KAG 的核心思想：

- 三层 LLMFriSPG 知识表示（EntityType / EventType / ConceptType）
- Chunk-Entity 双向互索引
- 双轨抽取（Schema-constrained + OpenIE）
- Aligner 概念归一化
- Logical-Form-Guided Reasoning

但**不直接 fork KAG**，自行实现轻量化版本，可逐步复用 KAG 的 Apache-2.0 资产（prompt 模板、aligner 组件、schema DSL）。

---

## 3. 技术栈

### 3.1 后端

- FastAPI + SQLAlchemy 2.0 + Pydantic v2
- Celery + Redis（异步任务编排）
- LLM：instructor + OpenAI-compatible API
- Embedding：bge-m3 / bge-large-zh
- Reranker：bge-reranker-v2

### 3.2 存储

- PostgreSQL 15+（元数据、Chunk、staging）
- PGVector（HNSW 索引，向量检索）
- Neo4j Community 5.x(知识图谱)
- MinIO（原始文档对象存储）
- Redis（缓存、队列、分布式锁）

### 3.3 前端

- React 18 + TypeScript + Vite
- Ant Design 5 + ProComponents
- AntV G6（图谱可视化）
- Zustand / TanStack Query
- react-pdf + mammoth.js（文档预览）
- react-hotkeys-hook（快捷键，v0.2+）

### 3.4 文档解析

- PDF：PyMuPDF + pdfplumber
- Word：python-docx + unstructured
- Excel：openpyxl
- 表格解析：pandas（TableExtractor 核心）
- OCR：PaddleOCR（v0.4+）

### 3.5 部署与运维

- 开发/MVP：docker-compose 单机
- 生产：Kubernetes + Helm（v0.4+）
- 可观测性：OpenTelemetry + Grafana + Loki（v0.3+）

---

## 4. 整体架构

```
┌─────────────────────────────────────────────────────┐
│  Frontend (React + AntD + G6)                       │
│  上传 / 任务 / 抽取结果 / 查询 / 图谱 / 审核(v0.2+) │
└──────────────────┬──────────────────────────────────┘
                   │ REST / WebSocket
┌──────────────────▼──────────────────────────────────┐
│  Backend (FastAPI Gateway)                          │
│  ├─ Auth / RBAC / Audit                             │
│  ├─ Schema/Ontology Service                         │
│  ├─ Pipeline Orchestrator (Celery)                  │
│  │   Reader → Splitter → TableExtractor             │
│  │     → LLM Extractor → Vectorizer → Writer        │
│  ├─ Review Service (v0.2+)                          │
│  └─ Query Router (Cypher / Vector+KG / LF-Solver)   │
└──────────────────┬──────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────┐
│  Storage Layer                                      │
│  MinIO │ PostgreSQL+PGVector │ Neo4j │ Redis        │
└─────────────────────────────────────────────────────┘
```

---

## 5. 知识表示与 Schema

### 5.1 类型分层

**EntityType（实体）**

- `EightDReport`：报告主体（含 closure_status: open / closed / partially_closed / root_cause_unidentified）
- `Project`：项目（一份报告可关联多个项目）
- `Customer`：客户（车辆制造商）
- `Operator`：运营商
- `Vehicle`：车辆（车号）
- `Part`：部件（v0.1 不区分 Type/Instance，序列号作为属性数组；v0.2 拆分为 PartType + PartInstance）
- `Material`：材料牌号
- `Standard`：执行标准/规范
- `TestMethod`：检测方法
- `Laboratory`：第三方机构
- `Person`：人员
- `Team`：团队
- `Supplier`：供应商
- `Process` / `Equipment`：工艺与设备

**EventType（事件）**

- `DefectOccurrence`：故障发生（绑定 Vehicle、Part、日期、里程）
- `InspectionEvent`：检测事件（绑定 TestMethod、样本、结论）
- `Experiment`：验证型实验（绑定 hypothesis、control_group、test_group、conclusion）
- `ContainmentExecution`：临时措施执行
- `CorrectiveExecution`：纠正措施执行
- `PreventiveExecution`：预防措施执行
- `VerificationEvent`：纠正措施验证
- `ClosureEvent`：报告关闭

**ConceptType（概念）**

- `FailureModeConcept`：失效模式分类树（疲劳断裂、应力腐蚀、变形等）
- `FractographicFeatureConcept`：断口特征术语（海滩花样、韧窝、疲劳条带等）
- `MetallurgicalDefectConcept`：冶金缺陷术语（夹杂、气孔、疏松、脱碳等）
- `RootCauseConcept`：根因分类
- `ActionTypeConcept`：对策类型分类

**辅助类型**

- `Measurement`：测量值（quantity / target_value / tolerance_upper / tolerance_lower / actual_value / unit / judgement / sample_id / method）
- `Finding`：检测/分析结论（含 polarity: positive / negative / neutral，evidence_source，evidence_strength）
- `RiskAssessment`：风险评估（severity、operational_impact、safety_impact）
- `Chunk`：原文片段（id = report_id#section_path#para_idx）

### 5.2 关键关系

- `EightDReport -BELONGS_TO-> Project`（多对多）
- `EightDReport -DESCRIBES-> DefectOccurrence`
- `DefectOccurrence -OCCURS_ON-> Vehicle`
- `DefectOccurrence -INVOLVES-> Part`
- `Part -PART_OF-> Part`（部件层级，递归）
- `Part -MADE_OF-> Material`
- `Material -COMPLIES_WITH-> Standard`
- `InspectionEvent -APPLIES-> TestMethod`
- `InspectionEvent -PRODUCES-> Measurement`
- `InspectionEvent -CONCLUDES-> Finding`
- `Experiment -TESTS-> Hypothesis`
- `Finding -SUPPORTS / RULES_OUT-> RootCause`
- `RootCause -LEADS_TO-> RootCause`（因果链，带 sequence_order、chain_id、confidence）
- `RootCause -ADDRESSED_BY-> Action`
- `Action -RESPONSIBLE_PARTY-> Organization`（KB / Supplier / Customer）
- 所有实体 `-MENTIONED_IN-> Chunk`（互索引）

### 5.3 必备公共属性

每个实体节点必须包含：

- `supporting_chunks`：原文 chunk id 列表（互索引核心）
- `description` / `summary`
- `source_doc_id` / `source_section`
- `confidence`：抽取置信度
- `extraction_version`：抽取流水线版本
- `schema_version`
- `review_status`：v0.1 默认 `auto_committed`
- `owner_id` / `sensitivity`
- `created_at` / `updated_at`

### 5.4 因果链建模（v0.1 折中方案 A+B）

**Schema 层（完整支持）**：

- `RootCause` 实体支持 `LEADS_TO` 自关联
- 边属性：`sequence_order`（整数）、`chain_id`（UUID）、`confidence`、`created_by`（llm / human）
- 链端标记：`is_root=true`（起点）、`is_symptom=true`（终点）
- 一个 Problem 可挂多条 chain

**抽取层（v0.1 扁平 + narrative）**：

- LLM 输出扁平 RootCause 列表 + `causal_narrative` 文本字段
- 不在 v0.1 自动生成 LEADS_TO 边
- v0.2 审核 UI 上线后由审核员手工连线，同时积累训练数据
- v0.3 基于审核数据训练/调 prompt，启用自动因果链抽取

---

## 6. Pipeline 设计

```
Reader → Splitter → TableExtractor → LLM Extractor → Vectorizer → Writer
   ↓        ↓            ↓                ↓              ↓         ↓
原文清洗  章节路由    规则解析表格      章节级抽取      向量化    幂等写入
```

### 6.1 Reader（数据清洗层）

- 占位符识别：`TBD`、`xxx`、`待定`、`需增加内容`、`N/A`、`n/a` → 标记 `is_placeholder=true`
- 图片引用识别：`如图`、`见下图`、`如下图所示` → 标记 `has_referenced_image=true`
- 表格重复列归一化（合并单元格导致）
- 全半角混用归一化、空白字符归一

### 6.2 Splitter（章节路由）

- 配置化章节字典（按客户/模板维护映射），如 `{"问题描述": "D2", "临时措施": "D3", "根本原因分析": "D4", "纠正措施": "D5/D6", "最终会议": "D8"}`
- 支持嵌套层级：每个 Chunk 带 `section_path`（数组）
- 每个 Chunk 带 `chunk_role`：`background` / `evidence` / `hypothesis` / `conclusion` / `action`
- 表格独立处理：作为结构化 Chunk（`TableChunk`）
- 找不到已知标题时按字号/加粗格式特征切分；最差按固定 token 切分并标 `section=unknown`

### 6.3 TableExtractor（独立规则模块，零 LLM）

v0.1 内置 5 类表格识别器：

| 表类型 | 识别特征 | 输出 |
|---|---|---|
| 项目简介表 | 含"项目号/客户/部件号"等关键词 | Report 元数据 |
| 变更记录表 | 表头含"版本/日期/章节/变更描述" | ReportVersion |
| 团队表 | 表头含"姓名/部门/邮件" | Person + Role |
| 故障清单表 | 表头含"故障日期/车号/序列号" | DefectOccurrence 列表 |
| 测量结果表 | 表头含"设定/实测/判定"或单位（bar/HV/μm） | Measurement 列表 |

**处理规则**：

- 重复列：默认去重，保留原始列数到 metadata
- 合并单元格：内容向所有被合并的格复制
- 空单元格：按 `null` 处理 + 标记 `is_incomplete=true`
- 识别失败回退：表头不在白名单时先用启发式（首列是否字段名），再决定走 LLM 通用抽取

匹配优先级：表头关键词 + 列数 + 章节上下文三重匹配。

### 6.4 LLM Extractor（按章节路由）

每个 prompt 上下文短、约束紧、Pydantic 强约束：

- **故障描述抽取器** → DefectOccurrence
- **检测/实验抽取器** → InspectionEvent / Experiment / Measurement / Finding（含 polarity）
- **根因抽取器** → RootCause（扁平）+ causal_narrative
- **对策抽取器** → Action + responsible_party
- **风险抽取器** → RiskAssessment
- **背景知识抽取器**（chunk_role=background）→ Material / Standard / Part 层级关系

**关键 Prompt 设计点**：

- 否定语义识别：明确区分"存在 X" vs "未见 X / 排除 X"
- 受控词表注入：`domain_lexicon.yaml`（失效模式、断口特征、检测方法等专业术语）
- 多实例输出：list 而非单对象
- 强制溯源：每个抽取结果必须带 `supporting_chunk_ids`

### 6.5 Vectorizer

- 双层向量：chunk 级（语义检索） + 实体级（消歧/合并）
- 模型：bge-m3（多语言）或 bge-large-zh（中文优先）
- 存入 PGVector（HNSW），v0.2 启用

### 6.6 Writer

- 幂等写入：业务键（report_id、part_no+serial、measurement_id）+ source_doc_id
- 实体合并：v0.1 仅业务键精确匹配；v0.3 启用向量+概念对齐
- 双向边：`MENTIONED_IN`（实体↔Chunk）必须建立
- 审计日志：所有写操作记录 user_id、action、target、before/after

---

## 7. 查询系统

### 7.1 三类查询通道

```
Query Router → 结构化通道 (Cypher)        ~50% 流量, <200ms
            → 语义检索通道 (Vector+KG)    ~30% 流量, <1.5s
            → 推理问答通道 (LF-Solver)    ~15-20% 流量, <8s
```

### 7.2 关键模块

- **Query Router**：规则路由 + 轻量 LLM 分类（<500ms）
- **结构化通道**：Text-to-Cypher 强化（schema 注入 + few-shot + 静态校验 + 模板化）
- **语义检索通道**：向量召回 → 图扩展 1-2 跳 → cross-encoder 重排 → top-N
- **推理通道**：LF-Solver 将复杂 query 分解为 DAG（Retrieve / Expand / Aggregate / Compare）
- **答案生成**：强制溯源引用 `[来源: 报告ID-chunk]`，不足时返回"不知道"

### 7.3 性能优化

- 多级缓存（Redis）：query→answer / 子查询 / embedding
- Neo4j 索引：business_key、Chunk id、时间属性
- 高频统计预计算 → 物化视图
- LLM 模型分层：Router 用小模型，Cypher 生成用中等模型，答案合成用大模型
- 流式输出降低感知延迟

### 7.4 准确性保障

- 召回-精排两段式
- BM25 + 向量 RRF 融合
- Schema 硬过滤
- 置信度可视化
- Golden 评测集持续监控（Recall@K、Precision、答案准确率）

---

## 8. MVP v0.1（8-9 周）

### 8.1 功能清单

**必做**：

- 文档上传（PDF / Word，单文件）
- Reader：占位符识别、图片引用标记、表格重复列归一化
- Splitter：章节路由 + 嵌套结构 + chunk_role 标记
- **TableExtractor（5 类表格规则解析）**
- LLM Extractor：按章节路由 + 否定语义识别 + 领域词典注入
- 因果链：Schema 完整支持，v0.1 仅扁平 RootCause + causal_narrative
- Writer：幂等写入 Neo4j + PG，`review_status=auto_committed`，建立 MENTIONED_IN 双向边
- 查询：结构化筛选面板 + 实体详情页 + 原文回溯
- 单报告子图可视化（G6，≤200 节点）
- 任务管理 + 错误反馈按钮
- 基础权限：用户名/密码 + 普通用户/管理员两角色 + 对象级访问检查
- 审计日志（user_id、action、target、before/after、ip、timestamp）
- LLM token 计量
- 评测骨架（数据集 + 字段级 F1 计算脚本）
- 领域词典 `domain_lexicon.yaml`（v0.1 即建）

**v0.1 不做**：

- OCR、批量上传
- 双轨抽取（OpenIE）
- 向量检索 / 语义查询
- 自然语言问答 / Text-to-Cypher
- 人工审核子系统（v0.2）
- PartType / PartInstance 分离（v0.2）
- 因果链自动抽取（v0.3）
- Experiment 实体的复杂建模（v0.1 仅基础字段）
- 多租户、SSO、RBAC
- 在线 Ontology 编辑

### 8.2 工期与里程碑（8.5 周）

| 周 | 模块 | 关键产出 |
|---|---|---|
| W1 | 项目骨架 + Schema 初稿 | docker-compose 起得来，Schema/Ontology 文档定稿 |
| W2 | Reader + Splitter（含章节路由+占位符） | 两份样本能正确切分嵌套章节 |
| W2.5 | TableExtractor（5 类） | 项目表/团队表/故障清单/测量结果表全部规则解析通过 |
| W3.5 | LLM Extractor（章节路由+否定语义） | 字段级 F1 ≥ 75% |
| W4 | Schema + Writer（含因果链结构） | Neo4j 写入幂等，MENTIONED_IN 双向边建立 |
| W5 | 前端：上传 + 任务列表 + 抽取结果只读页 | 端到端跑通 |
| W6 | 前端：查询面板 + 实体详情 | 结构化查询可用 |
| W7 | 前端：子图可视化（G6）+ 错误反馈 | 单报告图谱可视 |
| W8 | 评测脚本 + 种子用户试用 | 评测集 ≥20 份报告 |
| W8.5 | Bug 修复 + 文档 + 数据采集 | 上线试用版 |

### 8.3 评测指标（三档分组）

| 字段类别 | 难度 | v0.1 目标 | 示例 |
|---|---|---|---|
| 表格直读字段 | 低 | ≥ 95% | 部件号、批次、序列号、车号、测量值 |
| 半结构化字段 | 中 | ≥ 80% | 项目号、客户、运营里程、故障日期 |
| 叙述抽取字段 | 高 | ≥ 65% | 根因描述、失效模式、对策措施、causal_narrative |

加权整体 F1 目标 ≥ 75%。

### 8.4 成功标准

- 处理 ≥20 份真实 8D 报告（覆盖两份样本相似的复杂度）
- 加权字段 F1 ≥ 75%，表格字段 F1 ≥ 95%
- 3-5 名种子用户使用 ≥2 周，每人 ≥10 次有效查询
- 收集 ≥30 条用户反馈
- 错误反馈率 ≤ 30%
- 至少 5 条"图谱优于关键字搜索"的案例
- 结构化查询延迟 ≤ 1s

---

## 9. 版本路线图

### 9.1 v0.2（5-6 周）

- **人工审核子系统**：状态机（pending_review → in_review → approved / rejected / modified / on_hold → committed）+ 三级审核策略 + 字段视角 UI + 快捷键 + 双向定位 + 进度保存
- **回溯审核工具**：v0.1 auto_committed 数据全量回审
- **PGVector 向量化** + Chunk-Entity 双向索引 + 语义检索通道
- **PartType / PartInstance 拆分迁移**
- **因果链人工补边**：审核员在 UI 中连接 RootCause 之间的 LEADS_TO 边
- **审核数据资产化**：4 张表（extraction_corrections / rejection_log / concept_alignment_log / review_session_log）
- 评测集扩充至 50-200 条 + CI 自动跑

### 9.2 v0.3（6-8 周）

- 双轨抽取（Schema-constrained + OpenIE）
- 概念树管理 + Aligner（术语注入、消歧、概念归类）
- 重抽框架（ReExtractionJob、staging、diff、回滚）
- 多人协作审核（分配、锁、复核、专家仲裁）
- **因果链自动抽取**（基于审核数据调优 prompt/模型）
- 项目空间 RBAC
- OpenTelemetry 监控接入

### 9.3 v0.4（6 周）

- Text-to-Cypher + 自然语言问答（强制溯源）
- 三模式查询 UI（NL / 结构化 / Cypher）
- SSO（OIDC）
- 敏感字段脱敏
- K8s 部署评估

### 9.4 v0.5（6-8 周）

- 轻量 LF-Solver 推理（Retrieve / Expand / Aggregate / Compare）
- 业务分析仪表盘（根因 Top N、质量趋势、对策有效性）
- 物化视图固化高频聚合查询
- 自动化回归测试

### 9.5 v0.6+

- 在线 Ontology 编辑器
- 多租户
- 批量上传 + OCR（PaddleOCR）
- 模型微调（基于审核数据）
- VLM 接入（图片内容抽取）
- MES / QMS 集成
- 跨企业知识共享

---

## 10. 关键决策点

| 时点 | 决策 | 判定标准 |
|---|---|---|
| v0.1 完成 | 业务价值是否成立 | ≥5 条图谱优于关键字搜索案例、查询耗时下降 ≥30% |
| v0.1 完成 | 是否紧急上线审核 | 错误反馈率 >30% 立即启动 v0.2 |
| v0.2 完成 | 是否回溯 v0.1 数据 | 数据量 ≤20 份则全量回审，否则采样 |
| v0.2 完成 | 是否切换专业向量库 | Chunk 数 >100 万 且 PGVector 延迟 >500ms |
| v0.3 完成 | 是否启用自动通过 | 评测 F1 ≥95% 且 ≥5000 条审核数据 |
| v0.3 完成 | 是否启用因果链自动抽取 | 审核员手工连边 ≥500 条 + Prompt 评测准确率 ≥80% |
| v0.4 完成 | 产品化路线 | 内部深耕 vs 对外平台 |

---

## 11. 风险与缓解

| 风险 | 缓解措施 |
|---|---|
| Schema 演进 | 版本化字段、重抽接口、节点版本兼容 |
| 8D 模板差异大 | Reader/Splitter 配置化（章节字典、表头白名单） |
| 抽取上限 80-85% | 表格走规则、领域词典约束、v0.2 人审兜底 |
| 否定语义误抽 | Prompt 强约束 polarity 字段 + 评测专项 |
| 因果链顺序错乱 | v0.1 仅 narrative 不强抽，v0.2 人工补边积累数据 |
| 占位符（TBD/xxx）误入图 | Reader 层识别 + Extractor 层过滤 |
| 图片内容丢失 | Chunk 标记 has_referenced_image，v0.6+ VLM 补抽 |
| 前端工作量低估 | 占总工期 40-50%，使用 ProComponents 减少自研 |
| 裸奔阶段错误数据 | 强制溯源、置信度标红、Beta 声明、共建种子用户 |

---

## 12. 数据治理与运维

### 12.1 权限模型

- v0.1：用户名/密码 + 普通用户/管理员两角色 + 对象级访问检查（`require_object_access` 装饰器）
- v0.3：项目空间 RBAC
- v0.4：SSO（OIDC）+ 敏感字段脱敏

### 12.2 数据分级

- public / restricted / confidential，上传时强制选择
- 文档 owner_id、sensitivity 字段必填

### 12.3 审计日志

字段：`user_id, tenant_id, action, target_type, target_id, before, after, ip, ua, timestamp`，覆盖所有写操作。

### 12.4 评测体系

- 四层评测集：文档级、字段级、查询级、端到端问答
- 指标：F1（三档分组）、Recall@K、Precision@K、MRR、nDCG、事实准确率、溯源正确率
- CI 自动跑核心评测，指标下降 >3% 阻断合并
- Bad Case 库 + 反馈驱动增量标注

### 12.5 LLM 计量

v0.1 即记录每次调用的 token 消耗、模型、调用方、关联文档/任务，便于后续成本归因。

---

## 13. 参考资源

- KAG Paper: <https://arxiv.org/abs/2409.13731>
- OpenSPG: <https://github.com/OpenSPG/openspg>
- KAG: <https://github.com/OpenSPG/KAG>
- 可复用 KAG 资产（Apache-2.0）：
  - `kag/builder/prompt/spg_prompt.py`（Schema-constrained extraction prompt）
  - `kag/builder/component/aligner/`（Aligner 组件）
  - `kag/schema/`（Schema DSL 解析器）
  - chunk-id 设计、`supporting_chunks` 互索引定义

---

## 14. 变更记录

| 版本 | 日期 | 变更摘要 |
|---|---|---|
| v1.0 | 2026-05 | 初版方案 |
| v1.1 | 2026-05 | 新增 ROI / 数据治理 / 前端工作量管控 |
| v1.2 | 2026-05 | 新增人工审核子系统 |
| v1.3 | 2026-05 | MVP 移除审核，改为裸奔版，6 周 |
| v1.4 | 2026-05 | 移除 ROI 章节，专注技术方案 |
| **v1.5** | **2026-05-07** | **基于两份真实 8D 样本调整：新增章节路由、TableExtractor、占位符识别、因果链结构（A+B 折中）、扩展 Schema（Measurement 三元组、Experiment、RiskAssessment、Finding 极性、Material/Standard/Vehicle 等）、评测三档分组；MVP 工期 6→8.5 周；PartType/Instance 拆分推迟至 v0.2** |
