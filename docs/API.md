# API.md · REST 接口契约

**API 版本**：v0.1.0
**对应 PRD 版本**：v1.5
**对应 Schema 版本**：v0.1.0
**最后更新**：2026-05-07
**文件路径**：docs/API.md

本文档定义 8D 知识图谱平台 MVP v0.1 阶段的所有 REST 接口契约。所有接口必须严格遵循本文档定义的请求/响应格式。前端通过 `openapi-typescript` 从后端自动生成的 OpenAPI schema 派生类型，**禁止手写后端 DTO 类型**。

---

## 1. 通用约定

### 1.1 Base URL

```
开发环境: http://localhost:8000/api/v1
生产环境: https://kg.example.com/api/v1
```

所有路径以 `/api/v1` 开头，未来 v0.2+ 不兼容变更走 `/api/v2`。

### 1.2 内容类型

- 请求体（除文件上传）：`application/json; charset=utf-8`
- 文件上传：`multipart/form-data`
- 响应体：`application/json; charset=utf-8`

### 1.3 时间格式

所有时间字段统一使用 ISO 8601 + UTC：

```
2026-05-07T14:23:45Z
```

### 1.4 ID 格式

- 业务键（如 `report_id`、`part_no`）：字符串
- 内部 ID：UUID v4
- Chunk ID：`{report_id}#{section_path}#{para_idx}`（URL 中需 percent-encode）

### 1.5 分页

所有列表接口统一使用 cursor-based + offset 双兼容方案，v0.1 使用 offset：

请求参数：

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `page` | int | 1 | 页码，1-based |
| `page_size` | int | 20 | 每页大小，最大 100 |
| `sort_by` | string | `created_at` | 排序字段 |
| `sort_order` | string | `desc` | `asc` / `desc` |

响应：

```json
{
  "items": [...],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 145,
    "total_pages": 8
  }
}
```

### 1.6 响应包络

**成功响应**：直接返回业务数据，HTTP 200/201/204。

**错误响应**：统一格式

```json
{
  "error": {
    "code": "DOCUMENT_NOT_FOUND",
    "message": "Document with id 'xxx' not found",
    "details": { "doc_id": "xxx" },
    "trace_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

### 1.7 错误码表

| HTTP | code | 说明 |
|---|---|---|
| 400 | `INVALID_REQUEST` | 请求参数校验失败 |
| 400 | `INVALID_FILE_TYPE` | 不支持的文件类型 |
| 400 | `FILE_TOO_LARGE` | 文件超过 50MB |
| 401 | `UNAUTHORIZED` | 未登录或 token 无效 |
| 403 | `FORBIDDEN` | 已登录但无权访问该资源 |
| 404 | `DOCUMENT_NOT_FOUND` | 文档不存在 |
| 404 | `ENTITY_NOT_FOUND` | 实体不存在 |
| 404 | `CHUNK_NOT_FOUND` | Chunk 不存在 |
| 409 | `DUPLICATE_UPLOAD` | 文件 hash 已存在 |
| 409 | `PIPELINE_RUNNING` | 该文档 pipeline 正在运行，不能重复触发 |
| 422 | `VALIDATION_ERROR` | Pydantic 校验失败（详见 details） |
| 429 | `RATE_LIMITED` | 速率限制 |
| 500 | `INTERNAL_ERROR` | 服务器内部错误 |
| 502 | `LLM_UPSTREAM_ERROR` | LLM 上游异常 |
| 503 | `SERVICE_UNAVAILABLE` | 数据库/Neo4j 不可用 |

### 1.8 认证

所有接口（除登录、健康检查）需要 `Authorization` 请求头：

```
Authorization: Bearer <jwt_token>
```

JWT 包含 claims：`user_id, role, exp, iat`。Token 有效期默认 8 小时。

### 1.9 权限模型（v0.1 简化）

两角色：`user`（普通用户）、`admin`（管理员）。

对象级访问规则：

- 普通用户：仅能访问 `owner_id == self.user_id` 的文档及其衍生的实体/chunk
- 管理员：访问全部
- 公开数据（`sensitivity=public`）：所有登录用户可访问

接口层通过 `require_object_access` 装饰器检查。

### 1.10 速率限制

- 上传：每用户 30 次 / 小时
- 查询：每用户 600 次 / 小时
- LLM 相关查询（v0.4+ NL-QA）：每用户 60 次 / 小时

超限返回 429 + `Retry-After` 响应头。

### 1.11 Trace ID

每个请求自动生成 `X-Trace-Id` 响应头。前端在错误上报时必须带上 trace_id。

---

## 2. 接口清单

| 模块 | 路径 | 方法 | 说明 |
|---|---|---|---|
| **Auth** | `/auth/login` | POST | 登录 |
| | `/auth/me` | GET | 当前用户 |
| | `/auth/logout` | POST | 登出 |
| **Health** | `/health` | GET | 健康检查 |
| | `/health/deep` | GET | 深度健康检查（含数据库） |
| **Documents** | `/documents` | POST | 上传文档 |
| | `/documents` | GET | 文档列表 |
| | `/documents/{doc_id}` | GET | 文档详情 |
| | `/documents/{doc_id}` | DELETE | 删除文档（含级联） |
| | `/documents/{doc_id}/preview` | GET | 文档预览 URL |
| | `/documents/{doc_id}/raw` | GET | 下载原始文件 |
| **Pipeline** | `/documents/{doc_id}/pipeline` | POST | 触发 pipeline |
| | `/documents/{doc_id}/pipeline` | GET | pipeline 当前状态 |
| | `/documents/{doc_id}/pipeline/runs` | GET | pipeline 运行历史 |
| **Extraction** | `/documents/{doc_id}/extraction` | GET | 抽取结果（聚合视图） |
| | `/documents/{doc_id}/chunks` | GET | 文档的 chunk 列表 |
| | `/chunks/{chunk_id}` | GET | 单个 chunk 详情 |
| **Feedback** | `/feedback` | POST | 提交错误反馈 |
| | `/feedback` | GET | 反馈列表（admin） |
| **Entities** | `/entities` | GET | 实体列表（按类型） |
| | `/entities/{node_id}` | GET | 实体详情 |
| | `/entities/{node_id}/neighbors` | GET | 实体邻居（图扩展） |
| | `/entities/{node_id}/chunks` | GET | 实体溯源到的 chunks |
| **Query** | `/query/structured` | POST | 结构化查询 |
| | `/query/templates` | GET | 预编译查询模板列表 |
| | `/query/templates/{template_id}/execute` | POST | 执行模板查询 |
| **Graph** | `/graph/report/{report_id}` | GET | 单报告子图 |
| | `/graph/entity/{node_id}` | GET | 实体周边子图 |
| **Schema** | `/schema/types` | GET | 实体/事件/概念类型清单 |
| | `/schema/version` | GET | 当前 schema 版本 |
| **Audit** | `/audit/logs` | GET | 审计日志（admin） |
| **Admin** | `/admin/users` | GET | 用户列表（admin） |
| | `/admin/llm-usage` | GET | LLM 用量统计（admin） |

---

## 3. Auth 模块

### 3.1 POST /auth/login

**请求**：

```json
{
  "username": "alice",
  "password": "xxx"
}
```

**响应** 200：

```json
{
  "access_token": "eyJhbGc...",
  "token_type": "Bearer",
  "expires_in": 28800,
  "user": {
    "user_id": "u-001",
    "username": "alice",
    "role": "user",
    "display_name": "Alice"
  }
}
```

**错误**：401 `UNAUTHORIZED`

### 3.2 GET /auth/me

返回当前用户。

**响应** 200：

```json
{
  "user_id": "u-001",
  "username": "alice",
  "role": "user",
  "display_name": "Alice",
  "created_at": "2026-01-01T00:00:00Z"
}
```

### 3.3 POST /auth/logout

服务端将 token 加入黑名单。

**响应** 204。

---

## 4. Health 模块

### 4.1 GET /health

**响应** 200：

```json
{ "status": "ok", "version": "v0.1.0" }
```

### 4.2 GET /health/deep

检查数据库 / Neo4j / Redis / MinIO 连通性。

**响应** 200：

```json
{
  "status": "ok",
  "components": {
    "postgres": "ok",
    "neo4j": "ok",
    "redis": "ok",
    "minio": "ok",
    "llm_gateway": "ok"
  }
}
```

任一组件失败时返回 503 + 同样结构（对应组件值为 `error`）。

---

## 5. Documents 模块

### 5.1 POST /documents · 上传文档

**请求**（`multipart/form-data`）：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file` | binary | ✓ | 文件，PDF/DOCX，最大 50MB |
| `report_id` | string | ✗ | 业务键，缺省时由文件 hash 派生 |
| `sensitivity` | string | ✓ | `public` / `restricted` / `confidential` |
| `auto_run_pipeline` | bool | ✗ | 默认 `true`，上传后自动触发 pipeline |

**响应** 201：

```json
{
  "doc_id": "550e8400-e29b-41d4-a716-446655440000",
  "report_id": "600987222",
  "file_name": "8D_弹簧断裂.docx",
  "file_type": "docx",
  "file_hash": "sha256:abc...",
  "size_bytes": 245678,
  "sensitivity": "restricted",
  "owner_id": "u-001",
  "upload_status": "uploaded",
  "pipeline_status": "pending",
  "pipeline_run_id": "660e8400-...",
  "created_at": "2026-05-07T14:23:45Z"
}
```

**错误**：

- 400 `INVALID_FILE_TYPE` / `FILE_TOO_LARGE`
- 409 `DUPLICATE_UPLOAD`（响应 body 含已存在的 `doc_id`）
- 422 `VALIDATION_ERROR`

### 5.2 GET /documents · 文档列表

**Query 参数**：

| 参数 | 类型 | 说明 |
|---|---|---|
| `page`, `page_size`, `sort_by`, `sort_order` | — | 见 §1.5 |
| `pipeline_status` | string | `pending` / `running` / `committed` / `failed` |
| `closure_status` | string | 关联 EightDReport 的状态 |
| `owner_id` | string | 文档所有者（仅 admin 可查他人） |
| `search` | string | 模糊匹配 file_name / report_id |
| `created_from` | datetime | 创建时间下限 |
| `created_to` | datetime | 创建时间上限 |

**响应** 200：

```json
{
  "items": [
    {
      "doc_id": "...",
      "report_id": "600987222",
      "file_name": "8D_弹簧断裂.docx",
      "pipeline_status": "committed",
      "owner_id": "u-001",
      "created_at": "2026-05-07T14:23:45Z",
      "report_summary": {
        "title": "佛山南海磁轨弹簧断裂",
        "closure_status": "root_cause_unidentified",
        "defect_count": 1,
        "vehicle_count": 3
      }
    }
  ],
  "pagination": { "page": 1, "page_size": 20, "total": 12, "total_pages": 1 }
}
```

### 5.3 GET /documents/{doc_id}

**响应** 200：

```json
{
  "doc_id": "...",
  "report_id": "600987222",
  "file_name": "8D_弹簧断裂.docx",
  "file_type": "docx",
  "file_hash": "sha256:abc...",
  "size_bytes": 245678,
  "sensitivity": "restricted",
  "owner_id": "u-001",
  "upload_status": "uploaded",
  "pipeline_status": "committed",
  "schema_version": "v0.1.0",
  "extraction_version": "pipeline-v0.1.0",
  "created_at": "2026-05-07T14:23:45Z",
  "updated_at": "2026-05-07T14:30:12Z",
  "stats": {
    "chunk_count": 87,
    "table_count": 5,
    "entity_count": 23,
    "event_count": 8,
    "placeholder_chunks": 2
  }
}
```

### 5.4 DELETE /documents/{doc_id}

级联删除：MinIO 对象、PG `documents` / `chunks` / `entity_mirror`、Neo4j 相关节点（按 source_doc_id 过滤）。审计日志保留。

**响应** 204。

**错误**：404、403、409 `PIPELINE_RUNNING`

### 5.5 GET /documents/{doc_id}/preview

返回 MinIO 预签名 URL（5 分钟有效）。

**响应** 200：

```json
{
  "preview_url": "https://minio.example.com/...?X-Amz-Signature=...",
  "expires_at": "2026-05-07T14:35:00Z",
  "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
}
```

### 5.6 GET /documents/{doc_id}/raw

直接 stream 原始文件（带 `Content-Disposition: attachment`）。

---

## 6. Pipeline 模块

### 6.1 POST /documents/{doc_id}/pipeline · 触发

**请求**：

```json
{
  "force": false,
  "stages": null
}
```

| 字段 | 说明 |
|---|---|
| `force` | 即使已有成功 run 也重新执行（默认 false） |
| `stages` | v0.1 仅支持 `null`（全流程）；v0.3+ 支持单 stage 重跑 |

**响应** 202：

```json
{
  "run_id": "770e8400-...",
  "doc_id": "...",
  "status": "queued",
  "started_at": "2026-05-07T14:25:00Z"
}
```

**错误**：409 `PIPELINE_RUNNING`

### 6.2 GET /documents/{doc_id}/pipeline · 当前状态

**响应** 200：

```json
{
  "run_id": "770e8400-...",
  "doc_id": "...",
  "status": "running",
  "current_stage": "llm_extracting",
  "progress": {
    "completed_stages": ["reading", "splitting", "table_extracting"],
    "current": "llm_extracting",
    "remaining": ["vectorizing", "writing"]
  },
  "stage_metrics": [
    {
      "stage_name": "reading",
      "duration_ms": 856,
      "status": "success",
      "items_processed": 1
    },
    {
      "stage_name": "splitting",
      "duration_ms": 412,
      "status": "success",
      "items_processed": 87
    }
  ],
  "started_at": "2026-05-07T14:25:00Z",
  "finished_at": null,
  "error": null
}
```

`status` 枚举：`queued` / `running` / `success` / `partial_success` / `failed`。

### 6.3 GET /documents/{doc_id}/pipeline/runs · 历史

返回该文档历次 pipeline 执行（按 started_at 倒序）。

**响应** 200：

```json
{
  "items": [
    { "run_id": "...", "status": "success", "started_at": "...", "finished_at": "...", "pipeline_version": "pipeline-v0.1.0" }
  ],
  "pagination": { ... }
}
```

---

## 7. Extraction 模块

### 7.1 GET /documents/{doc_id}/extraction · 抽取结果（聚合视图）

返回该文档抽取出的所有实体的汇总，**用于"抽取结果只读页"**。

**响应** 200：

```json
{
  "doc_id": "...",
  "report_id": "600987222",
  "schema_version": "v0.1.0",
  "extraction_version": "pipeline-v0.1.0",

  "report": { /* EightDReport 完整字段，见 SCHEMA.md §3.1 */ },
  "projects": [ /* Project[] */ ],
  "customers": [ /* Customer[] */ ],
  "operators": [ /* Operator[] */ ],
  "vehicles": [ /* Vehicle[] */ ],
  "parts": [ /* Part[] */ ],
  "materials": [ /* Material[] */ ],
  "standards": [ /* Standard[] */ ],
  "test_methods": [ /* TestMethod[] */ ],
  "laboratories": [ /* Laboratory[] */ ],
  "persons": [ /* Person[] */ ],
  "teams": [ /* Team[] */ ],
  "suppliers": [ /* Supplier[] */ ],

  "defect_occurrences": [ /* DefectOccurrence[] */ ],
  "inspection_events": [ /* InspectionEvent[] */ ],
  "experiments": [ /* Experiment[] */ ],
  "actions": [ /* ActionEvent[] */ ],
  "verifications": [ /* VerificationEvent[] */ ],
  "closure": null,

  "measurements": [ /* Measurement[] */ ],
  "findings": [ /* Finding[] */ ],
  "root_causes": [ /* RootCause[] */ ],
  "risk_assessments": [ /* RiskAssessment[] */ ],

  "concept_references": [
    { "node_id": "...", "concept_type": "FailureModeConcept", "concept_name": "疲劳断裂" }
  ],

  "stats": {
    "total_entities": 23,
    "total_events": 8,
    "avg_confidence": 0.82,
    "low_confidence_count": 3,
    "placeholder_chunks": 2
  }
}
```

每个实体节点对象包含 `node_id`、业务键、所有 schema 字段以及：

```json
{
  "supporting_chunks": ["600987222#问题描述#0", "..."],
  "confidence": 0.92,
  "review_status": "auto_committed"
}
```

### 7.2 GET /documents/{doc_id}/chunks · Chunk 列表

**Query 参数**：

| 参数 | 类型 | 说明 |
|---|---|---|
| `chunk_role` | string | 过滤角色 |
| `is_table` | bool | 仅表格 / 仅文本 |
| `is_placeholder` | bool | 仅占位符 |
| `section_path_prefix` | string | 章节路径前缀过滤 |

**响应** 200：

```json
{
  "items": [
    {
      "chunk_id": "600987222#问题描述#0",
      "report_id": "600987222",
      "section_path": ["问题描述"],
      "para_idx": 0,
      "chunk_role": "evidence",
      "text": "佛山南海有轨电车T13车...",
      "token_count": 87,
      "is_table": false,
      "is_placeholder": false,
      "has_referenced_image": false
    }
  ],
  "pagination": { ... }
}
```

### 7.3 GET /chunks/{chunk_id}

**响应** 200：返回完整 Chunk 对象（同 SCHEMA.md §6.5）+ 关联的实体列表（通过 MENTIONS 边）：

```json
{
  "chunk_id": "...",
  /* ...所有 Chunk 字段 */
  "mentioned_entities": [
    { "node_id": "...", "entity_type": "Part", "name": "弹簧", "business_key": "C115408" }
  ]
}
```

---

## 8. Feedback 模块

### 8.1 POST /feedback · 提交错误反馈

用于"抽取结果只读页"的错误反馈按钮。v0.1 不做修改，仅记录。

**请求**：

```json
{
  "target_type": "entity",
  "target_id": "node-uuid-xxx",
  "feedback_type": "incorrect_extraction",
  "description": "根因抽取错误，原文是'未见夹杂'但抽成了'存在夹杂'",
  "expected_value": "polarity 应为 negative",
  "doc_id": "...",
  "chunk_id": "..."
}
```

字段说明：

| 字段 | 必填 | 说明 |
|---|---|---|
| `target_type` | ✓ | `entity` / `chunk` / `relationship` / `general` |
| `target_id` | ✗ | target_type=general 时可空 |
| `feedback_type` | ✓ | `incorrect_extraction` / `missing_entity` / `wrong_relationship` / `placeholder_leaked` / `polarity_wrong` / `other` |
| `description` | ✓ | 文字描述 |
| `expected_value` | ✗ | 期望的正确值 |

**响应** 201：

```json
{
  "feedback_id": "fb-uuid-xxx",
  "created_at": "2026-05-07T14:30:00Z"
}
```

### 8.2 GET /feedback · 反馈列表

仅 admin 可访问。

**Query 参数**：分页参数 + `feedback_type` / `doc_id` / `created_from` / `created_to`。

**响应** 200（items 中含完整反馈 + 上报用户）。

---

## 9. Entities 模块

### 9.1 GET /entities · 实体列表

**Query 参数**：

| 参数 | 类型 | 说明 |
|---|---|---|
| `entity_type` | string | EightDReport / Part / RootCause 等，详见 SCHEMA.md |
| `report_id` | string | 限定某报告 |
| `business_key` | string | 精确匹配 |
| `name_search` | string | 名称模糊搜索 |
| `min_confidence` | float | 置信度下限 |
| `review_status` | string | 过滤审核状态 |
| `closure_status` | string | 仅 EightDReport 实体使用 |
| 分页参数 | — | 见 §1.5 |

**响应** 200：

```json
{
  "items": [
    {
      "node_id": "...",
      "entity_type": "Part",
      "business_key": "C115408",
      "name": "弹簧",
      "summary": "...",
      "confidence": 0.95,
      "review_status": "auto_committed",
      "source_doc_ids": ["doc-uuid-xxx"],
      "supporting_chunk_count": 4
    }
  ],
  "pagination": { ... }
}
```

### 9.2 GET /entities/{node_id}

**响应** 200：完整实体对象（按 entity_type 包含相应字段）+ 关联统计：

```json
{
  "node_id": "...",
  "entity_type": "Part",
  "payload": { /* 完整 Pydantic 序列化 */ },
  "statistics": {
    "incoming_relationships": 5,
    "outgoing_relationships": 3,
    "supporting_chunks": 4,
    "appears_in_reports": 2
  }
}
```

### 9.3 GET /entities/{node_id}/neighbors · 邻居（图扩展）

**Query 参数**：

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `direction` | string | `both` | `in` / `out` / `both` |
| `relationship_types` | string[] | null | 指定关系类型，如 `INVOLVES,LEADS_TO`；逗号分隔 |
| `depth` | int | 1 | 跳数（1 或 2，最大 2） |
| `limit` | int | 50 | 节点数上限 |

**响应** 200：

```json
{
  "center": { "node_id": "...", "entity_type": "Part", "name": "弹簧" },
  "nodes": [
    { "node_id": "...", "entity_type": "DefectOccurrence", "name": "弹簧断裂" }
  ],
  "edges": [
    {
      "source": "node-1",
      "target": "node-2",
      "type": "INVOLVES",
      "properties": { "confidence": 0.9 }
    }
  ]
}
```

### 9.4 GET /entities/{node_id}/chunks · 实体溯源

返回该实体所有 supporting_chunks 的详情（用于实体详情页的"原文证据"区域）。

**响应** 200：

```json
{
  "node_id": "...",
  "entity_type": "RootCause",
  "chunks": [
    {
      "chunk_id": "...",
      "section_path": ["根本原因分析", "根本原因"],
      "text": "塑料活塞销存在气孔导致其强度变弱...",
      "chunk_role": "conclusion",
      "report_id": "600812585"
    }
  ]
}
```

---

## 10. Query 模块

### 10.1 POST /query/structured · 结构化查询

v0.1 仅支持参数化结构化查询，不支持自由 NL / Cypher。

**请求**：

```json
{
  "entity_type": "DefectOccurrence",
  "filters": {
    "occurred_at_from": "2024-01-01T00:00:00Z",
    "occurred_at_to": "2025-12-31T23:59:59Z",
    "involves_part": "EP2002阀",
    "exhibits_failure_mode": "疲劳断裂",
    "vehicle_no": null,
    "min_operating_mileage_km": 100000,
    "closure_status": "open"
  },
  "include_neighbors": ["INVOLVES", "EXHIBITS"],
  "page": 1,
  "page_size": 20,
  "sort_by": "occurred_at",
  "sort_order": "desc"
}
```

`filters` 字段按 `entity_type` 不同而不同（详见 OpenAPI schema）。后端校验未知字段返回 422。

**响应** 200：

```json
{
  "entity_type": "DefectOccurrence",
  "items": [
    {
      "node_id": "...",
      "entity_type": "DefectOccurrence",
      "summary": { /* 关键字段摘要 */ },
      "neighbors": {
        "INVOLVES": [ { "node_id": "...", "name": "EP2002阀" } ],
        "EXHIBITS": [ { "node_id": "...", "name": "疲劳断裂" } ]
      },
      "confidence": 0.88,
      "source_doc_id": "..."
    }
  ],
  "pagination": { ... },
  "query_metrics": {
    "duration_ms": 145,
    "cypher_template_id": "structured_defect_v1"
  }
}
```

### 10.2 GET /query/templates · 模板列表

返回 v0.1 内置的预编译查询模板（高频查询走模板，毫秒级返回）。

**响应** 200：

```json
{
  "items": [
    {
      "template_id": "recent_defects_by_part",
      "name": "某部件最近的故障",
      "description": "查询某部件号最近 N 个月的故障发生记录",
      "parameters": [
        { "name": "part_no", "type": "string", "required": true },
        { "name": "months", "type": "int", "required": false, "default": 12 }
      ]
    },
    {
      "template_id": "root_causes_for_failure_mode",
      "name": "某失效模式的常见根因",
      "parameters": [
        { "name": "failure_mode", "type": "string", "required": true }
      ]
    },
    {
      "template_id": "actions_by_responsible_party",
      "name": "按责任方汇总对策"
    }
  ]
}
```

### 10.3 POST /query/templates/{template_id}/execute

**请求**：

```json
{
  "parameters": {
    "part_no": "C115408",
    "months": 12
  }
}
```

**响应** 200：与 §10.1 相同结构。

---

## 11. Graph 模块

### 11.1 GET /graph/report/{report_id} · 单报告子图

返回该报告涉及的所有实体 + 关系，供 G6 渲染。

**Query 参数**：

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `include_chunks` | bool | false | 是否在子图中包含 Chunk 节点（true 时图节点数较多） |
| `include_concepts` | bool | true | 是否包含概念节点 |
| `min_confidence` | float | 0.0 | 节点置信度下限 |
| `max_nodes` | int | 200 | 节点数上限（v0.1 限制 200） |

**响应** 200：

```json
{
  "report_id": "600987222",
  "nodes": [
    {
      "id": "node-uuid-1",
      "label": "EightDReport",
      "name": "佛山南海磁轨弹簧断裂",
      "properties": { "closure_status": "root_cause_unidentified", "confidence": 1.0 },
      "style_hint": { "color": "#1890ff", "size": 40 }
    }
  ],
  "edges": [
    {
      "id": "edge-uuid-1",
      "source": "node-uuid-1",
      "target": "node-uuid-2",
      "label": "DESCRIBES",
      "properties": {}
    }
  ],
  "metadata": {
    "node_count": 23,
    "edge_count": 35,
    "truncated": false
  }
}
```

`style_hint` 由后端按 entity_type 与 confidence 计算（如低 confidence 标红），前端可覆盖。

### 11.2 GET /graph/entity/{node_id} · 实体周边子图

类似 §9.3 邻居接口，但返回适配 G6 渲染的格式。

**Query 参数**：同 §9.3，但额外支持 `max_nodes` (默认 50)。

**响应**：与 §11.1 同结构。

---

## 12. Schema 模块

### 12.1 GET /schema/types · 类型清单

返回所有 EntityType / EventType / ConceptType 的元信息，前端用于查询面板的下拉选项。

**响应** 200：

```json
{
  "schema_version": "v0.1.0",
  "entity_types": [
    {
      "name": "EightDReport",
      "category": "entity",
      "display_name_zh": "8D 报告",
      "business_key_field": "report_id",
      "json_schema_url": "/api/v1/schema/types/EightDReport"
    }
  ],
  "event_types": [ ... ],
  "concept_types": [ ... ],
  "relationship_types": [
    { "name": "DESCRIBES", "from": ["EightDReport"], "to": ["DefectOccurrence"] }
  ]
}
```

### 12.2 GET /schema/types/{type_name} · 单类型 JSON Schema

返回该类型的完整 Pydantic JSON Schema（来自 SCHEMA.md §10 导出）。

### 12.3 GET /schema/version

```json
{ "schema_version": "v0.1.0", "pipeline_version": "pipeline-v0.1.0" }
```

---

## 13. Audit 模块

### 13.1 GET /audit/logs · 审计日志（admin only）

**Query 参数**：

| 参数 | 类型 | 说明 |
|---|---|---|
| `user_id` | string | 操作用户 |
| `action` | string | 操作类型（如 `document.delete`、`entity.write`） |
| `target_type` | string | 目标类型 |
| `target_id` | string | 目标 ID |
| `created_from`, `created_to` | datetime | 时间范围 |
| 分页参数 | — | |

**响应** 200：

```json
{
  "items": [
    {
      "id": 1234,
      "user_id": "u-001",
      "action": "document.upload",
      "target_type": "Document",
      "target_id": "doc-uuid-xxx",
      "before_value": null,
      "after_value": { "report_id": "600987222" },
      "ip": "10.0.0.1",
      "user_agent": "Mozilla/5.0 ...",
      "created_at": "2026-05-07T14:23:45Z"
    }
  ],
  "pagination": { ... }
}
```

---

## 14. Admin 模块

### 14.1 GET /admin/users · 用户列表（admin）

**响应** 200：

```json
{
  "items": [
    {
      "user_id": "u-001",
      "username": "alice",
      "role": "user",
      "display_name": "Alice",
      "is_active": true,
      "created_at": "...",
      "last_login_at": "..."
    }
  ],
  "pagination": { ... }
}
```

### 14.2 GET /admin/llm-usage · LLM 用量统计（admin）

**Query 参数**：

| 参数 | 说明 |
|---|---|
| `from`, `to` | 时间范围 |
| `group_by` | `day` / `model` / `caller_module` / `user` |

**响应** 200：

```json
{
  "summary": {
    "total_requests": 1234,
    "total_tokens": 4567890,
    "total_cost_usd": 12.34
  },
  "groups": [
    {
      "key": "claude-haiku-4-5",
      "requests": 1100,
      "prompt_tokens": 2000000,
      "completion_tokens": 500000,
      "cost_usd": 8.5
    }
  ]
}
```

---

## 15. WebSocket 接口

v0.1 仅提供 1 个 WebSocket 端点，用于 pipeline 实时进度推送。

### 15.1 WS /ws/pipeline/{doc_id}

连接时携带 `Authorization` query 参数（JWT）。

**服务端推送消息**：

```json
{
  "type": "stage_started",
  "run_id": "...",
  "stage": "llm_extracting",
  "timestamp": "..."
}
```

```json
{
  "type": "stage_completed",
  "run_id": "...",
  "stage": "llm_extracting",
  "duration_ms": 12345,
  "items_processed": 23,
  "timestamp": "..."
}
```

```json
{
  "type": "pipeline_completed",
  "run_id": "...",
  "status": "success",
  "stats": { ... }
}
```

```json
{
  "type": "error",
  "run_id": "...",
  "stage": "llm_extracting",
  "error_code": "LLM_UPSTREAM_ERROR",
  "message": "..."
}
```

客户端断开后自动清理订阅，重连后通过 §6.2 拉取最新状态。

---

## 16. OpenAPI 元信息

### 16.1 文档地址

- `/api/v1/openapi.json` · OpenAPI 3.1 规范文件
- `/api/v1/docs` · Swagger UI（仅开发环境）
- `/api/v1/redoc` · ReDoc（仅开发环境）

### 16.2 类型自动生成

后端启动时自动生成 OpenAPI 到 `frontend/openapi.json`。前端构建脚本：

```bash
npx openapi-typescript ../backend/openapi.json -o src/types/api.ts
```

CI 中检查 `git diff` 是否有未提交的 `api.ts` 变更，有则失败。

---

## 17. 安全要求

### 17.1 输入校验

- 所有请求体严格 Pydantic 校验，未知字段拒绝（`extra="forbid"`）
- 文件上传：校验 magic bytes（不仅看扩展名）
- SQL 注入防护：所有 SQLAlchemy 查询用参数绑定，禁止字符串拼接
- Cypher 注入防护：参数化 Cypher，禁止字符串拼接 `$param`

### 17.2 输出过滤

- 实体 payload 中的 `sensitivity=confidential` 字段，对非 owner 自动脱敏（v0.4+ 全面实现，v0.1 仅做权限过滤）
- 错误响应不暴露内部堆栈（生产环境）

### 17.3 CORS

仅允许前端域名（配置化）：

```python
allow_origins = ["http://localhost:5173", "https://kg.example.com"]
allow_credentials = True
```

### 17.4 文件大小

- 上传：最大 50MB（v0.1）
- 单次响应体：最大 10MB（超过须分页）

---

## 18. 检查清单（API 实现完成时）

- [ ] 所有接口实现并通过单元测试
- [ ] OpenAPI schema 自动生成无错误
- [ ] 前端 `src/types/api.ts` 通过 `openapi-typescript` 自动生成
- [ ] 错误响应统一格式
- [ ] JWT 认证中间件正确
- [ ] `require_object_access` 装饰器覆盖所有 documents/entities 接口
- [ ] 速率限制中间件接入
- [ ] 文件 magic bytes 校验
- [ ] 所有 Cypher / SQL 参数化
- [ ] 审计日志覆盖所有写操作
- [ ] WebSocket 端点工作并能正确鉴权
- [ ] `/health/deep` 检查所有依赖
- [ ] CORS 配置正确
- [ ] 速率限制响应包含 `Retry-After`
- [ ] 上传冲突返回已存在的 doc_id
- [ ] e2e 测试：上传 → 触发 → 查询抽取结果 → 查询子图 → 删除

---

**文档版本**：v1.0（基于 PRD v1.5 / Schema v0.1.0）
**最后更新**：2026-05-07
**维护者**：项目团队
