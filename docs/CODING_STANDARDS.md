# CODING_STANDARDS.md · 编码规范

**版本**：v1.0
**对应 PRD 版本**：v1.5
**最后更新**：2026-05-07

本文档定义本项目的编码规范、提交流程、测试要求。所有贡献者（包括 Claude Code）必须遵守。规范的目的是：让代码可读、可维护、可测试，让 PR 评审聚焦逻辑而非格式。

---

## 1. 通用原则

1. **可读性 > 简洁性**：代码先给人读，再给机器执行
2. **显式 > 隐式**：禁止"魔法"行为；类型、参数、返回值显式声明
3. **小步快跑**：单次 PR 不超过 ~500 行新代码；大改动拆分为多个 PR
4. **失败显式**：禁止吞异常；遇到不应发生的状态用 `assert` 或抛异常
5. **配置外置**：禁止硬编码 URL、密钥、模型名、超时等
6. **文档同步**：API 变更、Schema 变更必须同时更新 `docs/`
7. **不重复造轮子**：优先用 ProComponents、AntD、TanStack Query；自研前先在 PR 中说明理由

---

## 2. Python 规范

### 2.1 版本与工具链

- **Python**：3.11+
- **包管理**：`uv` 或 `poetry`（项目统一选 `uv`）
- **构建系统**：`pyproject.toml`（PEP 621）
- **格式化**：`ruff format`
- **静态检查**：`ruff check` + `mypy --strict`
- **测试**：`pytest` + `pytest-asyncio` + `pytest-cov`

### 2.2 ruff 配置（pyproject.toml）

```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = [
    "E", "F", "W",      # pycodestyle / pyflakes
    "I",                # isort
    "N",                # pep8-naming
    "UP",               # pyupgrade
    "B",                # flake8-bugbear
    "A",                # flake8-builtins
    "C4",               # flake8-comprehensions
    "SIM",              # flake8-simplify
    "RUF",              # ruff-specific
    "ASYNC",            # flake8-async
    "S",                # flake8-bandit (安全)
]
ignore = [
    "E501",             # 行宽由 formatter 处理
    "S101",             # assert（测试中允许）
]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101", "S105", "S106"]   # 测试中允许 assert / 测试密钥

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

### 2.3 mypy 配置

```toml
[tool.mypy]
python_version = "3.11"
strict = true
warn_unused_ignores = true
warn_redundant_casts = true
no_implicit_reexport = true
disallow_any_generics = true
plugins = ["pydantic.mypy"]

[[tool.mypy.overrides]]
module = ["unstructured.*", "paddleocr.*", "pdfplumber.*"]
ignore_missing_imports = true
```

### 2.4 代码风格

#### 2.4.1 类型注解（强制）

所有函数签名必须有完整类型注解，包括返回值。

```python
# ✓ 正确
async def fetch_document(doc_id: UUID, *, include_chunks: bool = False) -> Document | None:
    ...

# ✗ 错误：缺少类型
async def fetch_document(doc_id, include_chunks=False):
    ...
```

复杂类型用 `TypeAlias` 或 `TypedDict` 命名：

```python
from typing import TypeAlias

ChunkId: TypeAlias = str
SectionPath: TypeAlias = list[str]
```

#### 2.4.2 命名约定

| 对象 | 风格 | 示例 |
|---|---|---|
| 模块 / 文件 | snake_case | `document_service.py` |
| 函数 / 方法 / 变量 | snake_case | `extract_root_cause` |
| 类 / 枚举 | PascalCase | `EightDReport`、`ReviewStatus` |
| 常量 | UPPER_SNAKE | `MAX_FILE_SIZE_MB` |
| 私有 | 前缀 `_` | `_internal_helper` |
| 类型变量 | 单字母大写或 PascalCase + `T` | `T`, `EntityT` |
| Pydantic 字段 | snake_case | `source_doc_id` |

#### 2.4.3 异步优先

所有 IO 操作（DB / HTTP / 文件 / Redis / Neo4j）必须 `async def`。禁止在 `async def` 内调用阻塞 IO。

```python
# ✓ 正确
async def get_user(session: AsyncSession, user_id: str) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()

# ✗ 错误：在 async 函数中调用阻塞库
async def upload_to_minio(data: bytes) -> str:
    response = requests.put(url, data=data)  # 阻塞！
    return response.text
```

CPU 密集型操作（解析 PDF、构造 embedding）放进 `asyncio.to_thread` 或 Celery worker。

#### 2.4.4 异常处理

- 禁止裸 `except:`
- 禁止 `except Exception:` 后吞掉（必须 re-raise 或转换）
- 业务异常继承 `app/core/exceptions.py` 中的基类

```python
# ✓ 正确
try:
    result = await client.fetch(url)
except httpx.TimeoutException as e:
    log.warning("upstream_timeout", url=url, error=str(e))
    raise LLMUpstreamError(f"timeout calling {url}") from e

# ✗ 错误：吞异常
try:
    result = await client.fetch(url)
except Exception:
    pass
```

异常基类规范：

```python
# app/core/exceptions.py
class AppError(Exception):
    """所有业务异常的基类"""
    code: str = "APP_ERROR"
    http_status: int = 500


class NotFoundError(AppError):
    code = "NOT_FOUND"
    http_status = 404


class ValidationError(AppError):
    code = "VALIDATION_ERROR"
    http_status = 422


class PermissionDenied(AppError):
    code = "FORBIDDEN"
    http_status = 403


class PipelineError(AppError):
    code = "PIPELINE_ERROR"


class FatalPipelineError(PipelineError): ...
class PartialPipelineError(PipelineError): ...
class LLMUpstreamError(AppError):
    code = "LLM_UPSTREAM_ERROR"
    http_status = 502
```

#### 2.4.5 日志

- 必须用 `structlog`，禁止 `print`、禁止 `logging` 直接调用
- 日志输出 JSON，便于 Loki/Grafana 解析

```python
import structlog

log = structlog.get_logger(__name__)

# ✓ 正确
log.info("document_uploaded", doc_id=str(doc.doc_id), size=doc.size_bytes)

# ✗ 错误
print(f"uploaded {doc.doc_id}")
logging.info(f"uploaded {doc.doc_id}")
```

日志级别约定：

| 级别 | 用途 |
|---|---|
| `debug` | 开发期细节，生产关闭 |
| `info` | 正常业务事件（上传、查询、阶段完成） |
| `warning` | 可恢复的异常（重试、降级） |
| `error` | 业务失败但服务继续 |
| `critical` | 服务不可用 |

#### 2.4.6 配置访问

禁止散落 `os.getenv`，必须经过 `app/core/config.py` 的 Pydantic Settings：

```python
# ✓ 正确
from app.core.config import settings
timeout = settings.llm_timeout_seconds

# ✗ 错误
import os
timeout = int(os.getenv("LLM_TIMEOUT", "60"))
```

#### 2.4.7 Pydantic v2 专属

- 必须用 v2 API：`model_dump()` / `model_validate()` / `model_config`
- 禁用 v1 兼容：`BaseModel.dict()` / `BaseModel.parse_obj()` / `class Config:`

```python
# ✓ 正确
class User(BaseModel):
    name: str
    age: int

    model_config = {"extra": "forbid", "frozen": True}

# ✗ 错误（v1 风格）
class User(BaseModel):
    name: str
    age: int

    class Config:
        extra = "forbid"
```

#### 2.4.8 SQLAlchemy 2.0 风格

- 必须用 2.0 风格 `select()`，禁止 `Query` 1.x API
- 必须用 `AsyncSession`，禁止同步 `Session`

```python
# ✓ 正确
from sqlalchemy import select

result = await session.execute(
    select(Document).where(Document.report_id == report_id)
)
doc = result.scalar_one_or_none()

# ✗ 错误（1.x 风格）
doc = session.query(Document).filter(Document.report_id == report_id).first()
```

#### 2.4.9 LLM 调用（强制约束）

所有 LLM 调用必须经过 `app/llm/` 抽象层：

```python
# ✓ 正确
from app.llm import LLMClient

client = LLMClient()
result = await client.structured_completion(
    model="claude-haiku-4-5",
    messages=[...],
    response_model=RootCauseAnalysisOutput,
    caller_module="root_cause_extractor",
    related_doc_id=doc_id,
)

# ✗ 错误：直接 SDK
from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(...)
```

CI 阶段会 grep `from openai`、`from anthropic` 等关键词，仅允许出现在 `app/llm/` 目录内。

#### 2.4.10 Cypher / SQL 注入防护

必须参数绑定，禁止字符串拼接：

```python
# ✓ 正确
await session.run(
    "MATCH (n:Part {part_no: $part_no}) RETURN n",
    part_no=part_no,
)

# ✗ 错误
await session.run(f"MATCH (n:Part {{part_no: '{part_no}'}}) RETURN n")
```

### 2.5 函数与类设计

- 单函数行数 ≤ 50 行；超出考虑拆分
- 单文件 ≤ 500 行；超出按职责拆分
- 函数参数 ≤ 5 个；多于 5 个用 Pydantic / dataclass 封装
- 关键字参数：3 个以上的函数参数建议改为 keyword-only（`*` 分隔）

```python
def create_chunk(
    *,
    chunk_id: str,
    report_id: str,
    section_path: list[str],
    text: str,
    chunk_role: ChunkRole,
) -> Chunk: ...
```

### 2.6 docstring

所有 public 函数 / 类必须有 docstring，推荐 Google 风格：

```python
async def split_document(
    doc: ParsedDocument,
    *,
    section_dict: dict,
) -> list[Chunk]:
    """Split a parsed document into chunks based on section dict.

    Args:
        doc: The parsed document with text and table blocks.
        section_dict: Configuration mapping section titles to D-steps and roles.

    Returns:
        A list of Chunks with section_path and chunk_role assigned.

    Raises:
        FatalPipelineError: If section_dict is invalid.
    """
    ...
```

模块级 docstring 简述模块职责，3-5 行。

注释用中文：

```python
# 占位符识别：命中 PLACEHOLDER_VALUES 时标记，但保留原文供审计
if normalized.lower() in PLACEHOLDER_VALUES:
    chunk.is_placeholder = True
```

### 2.7 导入顺序

`ruff` 自动排序，三段式：标准库 → 第三方 → 本项目。

```python
# 标准库
from datetime import datetime
from uuid import UUID, uuid4

# 第三方
import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

# 本项目
from app.core.config import settings
from app.models.document import Document
from app.schemas.document import DocumentRead
```

---

## 3. TypeScript 规范

### 3.1 版本与工具链

- **Node**：20+
- **包管理**：`pnpm`（项目统一）
- **TypeScript**：5+，`strict: true`
- **格式化**：Prettier
- **静态检查**：ESLint（airbnb-typescript）
- **测试**：Vitest + React Testing Library

### 3.2 tsconfig

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitOverride": true,
    "exactOptionalPropertyTypes": true,
    "verbatimModuleSyntax": true,
    "jsx": "react-jsx",
    "isolatedModules": true,
    "skipLibCheck": true
  }
}
```

### 3.3 ESLint 关键规则

- `no-explicit-any`: error（仅在边界处加 `// eslint-disable-next-line` + 注释解释）
- `no-unused-vars`: error
- `prefer-const`: error
- `react-hooks/rules-of-hooks`: error
- `react-hooks/exhaustive-deps`: error

### 3.4 命名约定

| 对象 | 风格 | 示例 |
|---|---|---|
| 组件文件 | PascalCase.tsx | `EntityCard.tsx` |
| Hook 文件 | useXxx.ts | `useDocumentList.ts` |
| 工具文件 | camelCase.ts | `formatDate.ts` |
| 类型 / 接口 | PascalCase | `DocumentRead`, `ApiError` |
| 函数 / 变量 | camelCase | `fetchDocument`, `isLoading` |
| 常量 | UPPER_SNAKE | `MAX_PAGE_SIZE` |
| React 组件 | PascalCase | `<EntityCard />` |

不要在文件名中加 `.tsx` 之外的标记（如 `.component.tsx`）。

### 3.5 类型策略

- 后端 DTO 类型从 `src/types/api.ts` 引用，**禁止手写**
- 业务实体的衍生类型用 `Pick / Omit / Partial` 派生
- 禁止 `any`；不得已用 `unknown` 并配合类型守卫

```typescript
// ✓ 正确
import type { components } from "@/types/api";

type Document = components["schemas"]["DocumentRead"];
type DocumentSummary = Pick<Document, "doc_id" | "report_id" | "file_name">;

// ✗ 错误
const doc: any = response.data;
```

### 3.6 React 规范

#### 3.6.1 函数组件 + Hooks

只用函数组件，禁止 class component。

```tsx
// ✓ 正确
export function EntityCard({ entity }: Props) {
  const [expanded, setExpanded] = useState(false);
  return <Card>...</Card>;
}

// 组件 props 类型用 interface 或 type alias，文件内可省略 export
interface Props {
  entity: Entity;
  onClick?: (id: string) => void;
}
```

#### 3.6.2 服务端状态

服务端数据必须用 TanStack Query，禁止 `useEffect + fetch + setState` 模式：

```tsx
// ✓ 正确
const { data, isLoading, error } = useQuery({
  queryKey: ["document", docId],
  queryFn: () => api.documents.get(docId),
});

// ✗ 错误
const [data, setData] = useState();
useEffect(() => {
  fetch(`/api/v1/documents/${docId}`).then(r => r.json()).then(setData);
}, [docId]);
```

QueryKey 约定：`[resource, id?, ...filters]`，便于失效。

#### 3.6.3 客户端状态

- 单组件状态：`useState`
- 跨页面/全局：Zustand（仅放确实需要全局的，如 user / theme / WebSocket）
- 表单状态：ProForm 内置或 `react-hook-form`（不用 Zustand 管表单）

#### 3.6.4 副作用

- `useEffect` 仅用于真正的副作用（订阅、计时器、DOM 操作）
- 数据获取一律走 TanStack Query
- 派生状态用 `useMemo` 而非 `useEffect + setState`

#### 3.6.5 性能

- 列表渲染必给 `key`（不要用 index 作为 key，除非列表完全静态）
- 重型计算用 `useMemo`
- 子组件依赖稳定 props 时用 `React.memo`
- 长列表用虚拟化（`@tanstack/react-virtual` 或 AntD `VirtualList`）

### 3.7 文件组织

每个组件一个文件夹，包含：

```
EntityCard/
  ├── EntityCard.tsx
  ├── EntityCard.test.tsx
  ├── EntityCard.module.css   # 如果用 CSS Modules
  └── index.ts                # 仅 re-export
```

简单组件直接放单文件 `EntityCard.tsx`，复杂时再拆。

### 3.8 样式

- 默认用 AntD 组件 + `style` / `className` 局部覆盖
- 自定义样式用 CSS Modules 或 Tailwind（项目选其一，不混用）
- 禁止全局 CSS（除 reset 与主题变量）

---

## 4. 数据库规范

### 4.1 PostgreSQL

#### 4.1.1 命名

- 表名：`snake_case` 复数（`documents`, `chunks`, `entity_mirror`）
- 主键：`id` (BIGSERIAL) 或业务键 PK（如 `chunks.chunk_id`）
- 外键：`{表名单数}_id`，例如 `documents` 表的外键叫 `doc_id`
- 索引：`{表名}_{字段}_idx`，唯一索引 `{表名}_{字段}_uidx`
- 枚举值：`snake_case`（`auto_committed`、`pending_review`）

#### 4.1.2 类型选择

- 时间戳：`TIMESTAMPTZ`（始终带时区）
- 主键 UUID：`UUID` 类型，默认值用 `gen_random_uuid()`
- JSON：`JSONB`（不用 `JSON`）
- 字符串：明确 VARCHAR 长度上限；未知用 `TEXT`
- 数组：`TEXT[]`、`UUID[]` 等原生数组类型
- 向量：`vector(1024)`（PGVector）

#### 4.1.3 迁移

- 必须用 Alembic，禁止手写 `ALTER TABLE` 直接上线
- 一次迁移做一件事（加列 / 加索引 / 加约束分开）
- 破坏性变更（删列、改类型）必须分两个迁移：先兼容、再删除
- 大表加索引必须 `CONCURRENTLY`：

```python
# alembic/versions/xxxx_add_idx.py
def upgrade():
    op.execute(
        "CREATE INDEX CONCURRENTLY chunks_role_idx ON chunks(chunk_role)"
    )
```

注意：`CONCURRENTLY` 不能在事务中执行，需在 migration 中关闭事务。

#### 4.1.4 查询

- 必须参数绑定（见 §2.4.10）
- 单表查询超过 200ms 应加索引或重写
- N+1 必须用 `selectinload` / `joinedload` 解决

```python
# ✓ 正确
result = await session.execute(
    select(Document).options(selectinload(Document.chunks))
)
```

### 4.2 Neo4j

#### 4.2.1 命名

- 节点 Label：`PascalCase`，如 `EightDReport`、`Part`、`Chunk`
- 关系类型：`UPPER_SNAKE`，如 `LEADS_TO`、`MENTIONED_IN`
- 属性：`snake_case`，与 PG 字段对齐

#### 4.2.2 写入

- **必须用 MERGE**，禁止裸 CREATE（见 SCHEMA.md §8.1）
- MERGE 必须指定业务键
- 关系也必须 MERGE：

```cypher
MATCH (a {node_id: $a_id}), (b {node_id: $b_id})
MERGE (a)-[r:LEADS_TO]->(b)
ON CREATE SET r += $props
```

#### 4.2.3 查询

- 必须使用参数化查询
- 必须设置 `LIMIT` 上限（v0.1：单查询 ≤ 1000 节点）
- 复杂查询写在 `app/graph/cypher/*.cypher` 文件内，由 Python 加载，便于版本控制

#### 4.2.4 事务

- 写操作必须包在 `session.execute_write()` 内
- 读操作用 `session.execute_read()`（路由到 reader replica，未来扩展用）

### 4.3 MinIO

- Bucket 命名：`kg-{env}-{purpose}`，如 `kg-dev-uploads`
- 对象 key 规范：`{report_id}/{YYYYMMDD}/{filename}`
- 仅通过 presigned URL 暴露给前端，禁止直接暴露 endpoint
- 上传后立即写 PG 元数据，原子性由应用层保证

---

## 5. 测试规范

### 5.1 测试金字塔

| 层级 | 比例 | 工具 | 范围 |
|---|---|---|---|
| 单元测试 | 60% | pytest / vitest | 单函数、单组件 |
| 集成测试 | 30% | pytest + testcontainers | DB / Neo4j / MinIO 真实容器 |
| E2E 测试 | 10% | Playwright（v0.2+） | 完整用户路径 |

### 5.2 Python 测试

#### 5.2.1 文件组织

```
backend/tests/
├── unit/
│   ├── pipeline/
│   │   ├── test_reader.py
│   │   ├── test_splitter.py
│   │   └── test_table_extractor.py
│   ├── services/
│   └── llm/
├── integration/
│   ├── test_pipeline_e2e.py        # 跑两份样本
│   ├── test_neo4j_writer.py
│   └── test_postgres_models.py
├── conftest.py                     # fixtures
└── fixtures/
    └── sample_8d_reports/          # 两份样本 + 期望输出
```

#### 5.2.2 命名

- 测试文件：`test_{module}.py`
- 测试函数：`test_{被测函数}_{场景}_{期望}`
  - 例：`test_table_extractor_defect_list_returns_5_occurrences`
- 测试类：`Test{被测类}`

#### 5.2.3 fixture 与 mock

- 共用 fixture 放 `conftest.py`
- 数据库 fixture 用 `pytest-asyncio` + `testcontainers`
- LLM 调用必须 mock：

```python
@pytest.fixture
def mock_llm(monkeypatch):
    async def fake_completion(*args, **kwargs):
        return RootCauseAnalysisOutput(...)
    monkeypatch.setattr(LLMClient, "structured_completion", fake_completion)
```

#### 5.2.4 覆盖率

- 业务代码覆盖率 ≥ 70%
- 核心 Pipeline 组件 ≥ 85%
- Schema / models 不强求（属于声明性代码）

CI 配置覆盖率门槛，下降阻断合并。

#### 5.2.5 必须有的关键测试

| 模块 | 关键测试 |
|---|---|
| Reader | 两份样本能正确解析；占位符识别命中所有黑名单值 |
| Splitter | 章节路径正确率 ≥95%；chunk_id 确定性 |
| TableExtractor | 5 类表格命中率 100%；故障清单表逐行映射 |
| LLM Extractor | mock LLM 后 Pydantic 校验通过；polarity 抽取准确 |
| Writer | 重复写入幂等；MENTIONED_IN 双向边建立 |
| API | 权限检查；错误码符合规范 |

### 5.3 TypeScript 测试

```typescript
// src/components/EntityCard/EntityCard.test.tsx
import { render, screen } from "@testing-library/react";
import { EntityCard } from "./EntityCard";

describe("EntityCard", () => {
  it("renders entity name and type", () => {
    render(<EntityCard entity={{ name: "弹簧", type: "Part" }} />);
    expect(screen.getByText("弹簧")).toBeInTheDocument();
  });
});
```

- 关注组件行为，不测内部实现细节
- 用 `userEvent` 模拟交互，不直接 fire DOM event
- API 调用用 `msw`（Mock Service Worker）拦截

---

## 6. Git 与提交规范

### 6.1 分支策略

- `main`：受保护，仅通过 PR 合并；每次合并对应一次可部署版本
- `develop`：日常开发集成分支（v0.2+ 启用，v0.1 直接用 main）
- `feature/{ticket}-{short-desc}`：功能分支
- `fix/{ticket}-{short-desc}`：修复分支
- `chore/{short-desc}`：杂务（依赖升级、文档）

分支命名小写、`-` 分隔。

### 6.2 Commit Message（Conventional Commits）

格式：

```
<type>(<scope>): <subject>

<body>

<footer>
```

`type`：

| 类型 | 用途 |
|---|---|
| `feat` | 新功能 |
| `fix` | 缺陷修复 |
| `docs` | 文档变更 |
| `refactor` | 重构（不改行为） |
| `perf` | 性能优化 |
| `test` | 测试相关 |
| `build` | 构建/依赖 |
| `ci` | CI 配置 |
| `chore` | 杂务 |

`scope`（可选）：模块名，如 `pipeline`、`api`、`frontend`、`schema`、`splitter`。

示例：

```
feat(splitter): support nested section detection

按 SCHEMA.md §6.2 实现章节嵌套层级，每个 chunk 带 section_path 数组。
新增 fixture: 弹簧断裂样本的章节树期望输出。

Refs: #42
```

```
fix(writer): ensure MENTIONED_IN edge is bidirectional

之前只建立 entity → chunk 单向边，导致 v0.2 反向溯源失败。
已补充测试覆盖。

Closes: #58
```

主标题：

- 小写开头、不加句号、≤ 72 字符
- 用祈使语气（"add"、"fix"、不是 "added"、"fixes"）

### 6.3 PR 规范

- 标题与 commit 标题同格式
- 描述模板：

```markdown
## 变更说明
（一段简述本次变更的目的与做法）

## 关联文档
- PRD §x.x
- SCHEMA §x.x

## 测试
- [ ] 单元测试已加
- [ ] 集成测试已跑
- [ ] 手工验证：xxx

## 影响面
- DB 迁移：是 / 否
- API 破坏性变更：是 / 否
- 前端类型重新生成：是 / 否

## 备注
（可选）
```

- 单 PR 行数：新代码 ≤ 500 行，例外需在描述中说明
- 必须 ≥ 1 个 reviewer 通过
- CI 必须全绿

### 6.4 禁止入仓

- `.env`、`*.local.*` 等环境文件
- 密钥、证书、token
- IDE 配置（除 `.editorconfig` 与团队约定的 `.vscode/settings.json`）
- 大型二进制（>1 MB），样本文件除外（放 `tests/fixtures/`）
- 编译产物：`__pycache__/`、`dist/`、`node_modules/`、`.next/`

`.gitignore` 已统一维护。

---

## 7. CI / CD

### 7.1 CI 流水线（每个 PR 必跑）

```
┌─ pre-commit hooks（本地）
│   ruff format + ruff check + mypy + prettier + eslint
│
├─ backend-test
│   ├─ ruff check
│   ├─ mypy --strict
│   ├─ pytest --cov (覆盖率门槛)
│   └─ pytest integration/（启 testcontainers）
│
├─ frontend-test
│   ├─ tsc --noEmit
│   ├─ eslint
│   ├─ vitest
│   └─ build (vite build 不报错)
│
├─ schema-sync-check
│   ├─ 后端启动 → 导出 openapi.json
│   ├─ 前端 npm run gen:api
│   └─ git diff frontend/src/types/api.ts → 必须无变更
│
├─ docs-check
│   ├─ markdown 格式
│   └─ 链接有效性
│
└─ security-scan
    ├─ pip-audit / npm audit
    └─ ruff S 规则（bandit）
```

任一步失败阻断合并。

### 7.2 pre-commit

仓库根目录 `.pre-commit-config.yaml`：

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.x.y
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-prettier
    rev: v3.x.x
    hooks:
      - id: prettier
        files: \.(ts|tsx|js|jsx|json|md|yaml|yml)$

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.x.x
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
        args: [--maxkb=1024]
```

新成员第一次 clone 后必须运行 `pre-commit install`。

---

## 8. Code Review 准则

### 8.1 Reviewer 关注点

按优先级：

1. **正确性**：逻辑是否符合 PRD/SCHEMA/PIPELINE/API
2. **安全性**：参数注入、权限、敏感信息泄漏
3. **可测试性**：是否能单独测；mock 边界是否合理
4. **可读性**：命名、结构、注释；新人 5 分钟能否看懂
5. **性能**：N+1、未加索引、阻塞 IO；明显问题才提
6. **风格**：留给 ruff/eslint，人不应纠结这些

### 8.2 Reviewer 不做的事

- 不无意义争论代码风格（让工具决定）
- 不要求作者改名为自己的偏好（除非违反约定）
- 不在 PR 中扩大范围（"顺便也改一下 X"）

### 8.3 Reviewer 必须做的事

- 24 小时内首次响应（紧急 PR 6 小时）
- 提出 blocker 时给出具体修改建议
- 区分 `nit:`（可选）、`question:`（不阻塞）、`request changes:`（必须）

### 8.4 作者责任

- PR 描述清晰，让 reviewer 不需翻代码就能理解动机
- CI 全绿后再请评审
- 收到反馈后逐条回应（采纳 / 拒绝 / 讨论），不要无声修改
- 单条反馈讨论 ≤ 3 轮还无定论时升级线下沟通

---

## 9. 文档同步

变更代码时必须同步检查以下文档：

| 变更类型 | 必须更新的文档 |
|---|---|
| 新增 / 修改 API | `docs/API.md` + 自动生成的 OpenAPI |
| 新增 / 修改实体 / 关系 | `docs/SCHEMA.md` + Pydantic 模型 |
| 新增 / 修改 Pipeline 组件 | `docs/PIPELINE.md` |
| 新增 / 修改架构组件 | `docs/ARCHITECTURE.md` |
| 新增领域术语 | `backend/app/lexicon/domain_lexicon.yaml` + changelog |
| 引入新依赖 | `pyproject.toml` / `package.json` + PR 描述说明理由 |
| 破坏性变更 | `CHANGELOG.md` + PRD 路线图 |

文档与代码不一致视为 bug。

---

## 10. 安全要求

### 10.1 必做

- 敏感配置（API Key / DB 密码 / JWT Secret）只走环境变量
- 用户输入必须 Pydantic 校验（`extra="forbid"`）
- 文件上传必须校验 magic bytes，不仅看扩展名
- SQL / Cypher 必须参数化
- 错误响应不暴露内部堆栈（生产环境）
- 密码用 `argon2` / `bcrypt` 哈希，禁止 MD5/SHA1

### 10.2 禁做

- 提交密钥到仓库（即使是 dev key）
- 在日志中打印用户密码、token、PII（如手机号、邮箱明文超出必要范围）
- 引入未审查的二进制依赖
- 在生产环境开启 Swagger UI / debug toolbar

### 10.3 依赖管理

- 每月运行 `pip-audit` / `npm audit`
- 高危漏洞 7 天内修复
- 主版本升级走单独 PR，不与功能 PR 混

---

## 11. 性能基线

| 指标 | 目标 | 备注 |
|---|---|---|
| 前端首屏 LCP | < 2 s | 本地网络 |
| 前端列表渲染 | < 500 ms | 100 行以内 |
| 100 节点子图渲染 | < 1 s | G6 |
| 后端结构化查询 | P95 < 200 ms | v0.1 |
| 后端语义查询 | P95 < 1.5 s | v0.2+ |
| Pipeline 端到端 | P95 < 60 s | 单份 8D 报告 ≤ 5 MB |
| LLM 单次调用 | P95 < 15 s | 含重试 |

不达标的 PR 必须在描述中说明原因；持续退化进入技术债清单。

---

## 12. 检查清单（每次提交前）

作者自查：

- [ ] `ruff format && ruff check && mypy --strict` 全绿
- [ ] `pnpm lint && pnpm tsc --noEmit && pnpm test` 全绿
- [ ] 新增 / 修改的代码有对应测试
- [ ] 涉及 API / Schema / Pipeline 变更的文档已同步更新
- [ ] OpenAPI 自动生成的前端类型已重新生成并提交
- [ ] 没有硬编码、没有 print、没有 TODO 留在生产代码（必要的 TODO 加 issue 链接）
- [ ] 所有 LLM 调用经过 `app/llm/`
- [ ] 所有 Cypher / SQL 已参数化
- [ ] PR 描述完整，包含变更说明、关联文档、测试情况
- [ ] CI 全绿后请评审

---

**文档版本**：v1.0（基于 PRD v1.5）
**最后更新**：2026-05-07
**维护者**：项目团队
