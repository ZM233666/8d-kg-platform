# Claude Code 启动 Prompt — 8D 报告知识图谱平台 v0.1

> 本文件是发给 Claude Code 的初始化指令。Claude Code 启动时应先完整阅读本项目所有文档，再按本 prompt 生成代码骨架。

## 上下文（必读）

1. 项目根：/Users/God-Prime/Desktop/KnowledgeGraph/8d-kg-platform
2. 已有文件：CLAUDE.md、docs/PRD.md、docs/ARCHITECTURE.md、docs/SCHEMA.md、docs/PIPELINE.md、docs/API.md、docs/CODING_STANDARDS.md、.env、.gitignore
3. **开发环境架构详见 CLAUDE.md 第 0 节**——数据库已远端就绪，通过 SSH 隧道暴露在 localhost:{5432,7474,7687,6379,9000,9001}。
4. **不得生成** docker-compose.yml、Dockerfile（v0.1 不打包）、任何启动数据库容器的脚本。

## 执行流程

### 阶段 1：阅读与确认（仅输出，不写代码）

1. 读完 CLAUDE.md 和 docs/ 全部 6 个文件（PRD、ARCHITECTURE、SCHEMA、PIPELINE、API、CODING_STANDARDS）。
2. 输出一份 ≤300 字的「我理解到的项目目标 + MVP v0.1 范围 + 6 阶段流水线」摘要。
3. 列出你计划生成的文件树（深度 ≤ 3）。
4. 等待用户回复 GO 后再进入阶段 2。

### 阶段 2：生成项目骨架

按下列结构生成代码（不要生成 docker-compose）：

    8d-kg-platform/
      CLAUDE.md                   # 已存在，勿动
      README.md                   # 新建：本地启动步骤（隧道→后端→前端）
      .env                        # 已存在
      .env.example                # 新建：占位符版本，可入 git
      .gitignore                  # 已存在
      .editorconfig               # 新建
      .pre-commit-config.yaml     # 新建：ruff + black + mypy + eslint
      Makefile                    # 新建：tunnel-up/tunnel-status/backend/worker/frontend/test/lint
      docs/                       # 已存在，勿动
      pyproject.toml              # 新建：uv + ruff + mypy + pytest 配置
      backend/
        app/
          __init__.py
          main.py                 # FastAPI + lifespan + CORS + /health
          core/
            config.py             # Pydantic Settings 读 .env
            logging.py            # structlog JSON + trace_id
            deps.py               # 共用依赖
          api/v1/
            routes_documents.py
            routes_pipeline.py
            routes_graph.py
            routes_health.py
          db/
            postgres.py           # async engine + session
            neo4j.py              # driver + 启动时执行约束
            redis.py
            minio.py
          models/                 # SQLAlchemy ORM
          schemas/                # Pydantic
          pipeline/
            base.py               # 抽象 PipelineStage
            s1_parse.py
            s2_chunk.py
            s3_extract.py
            s4_normalize.py
            s5_link.py
            s6_write.py
          llm/
            base.py               # LLMClient 抽象
            mock.py               # MVP 阶段用 mock
          graph/
            constraints.py        # 按 SCHEMA.md 创建 Neo4j 约束/索引
          lexicon/
            domain_lexicon.yaml   # 按 SCHEMA.md 抽取的领域词典种子
          tasks/
            celery_app.py
            pipeline_tasks.py
        alembic/                  # 迁移脚本目录
        alembic.ini
        tests/
          conftest.py
          test_health.py
      frontend/
        package.json              # React 18 + Vite + AntD + AntV G6 + zustand
        vite.config.ts
        tsconfig.json
        index.html
        src/
          main.tsx
          App.tsx
          api/                    # axios 客户端
          pages/
          components/
          store/
      eval/
        README.md                 # 评测说明（v0.1 占位）
      .github/
        workflows/
          ci.yml                  # ruff + mypy + pytest + eslint + tsc

### 阶段 3：关键文件实现要点

**backend/app/core/config.py**
- 用 pydantic-settings 读 .env
- 字段：DATABASE_URL、ALEMBIC_DATABASE_URL、NEO4J_URI/USER/PASSWORD/DATABASE、REDIS_URL、CELERY_BROKER_URL、CELERY_RESULT_BACKEND、MINIO_*、LLM_*、SECRET_KEY、JWT_*
- 嵌套 PipelineSettings（chunk_size、overlap、llm_concurrency 等）

**backend/app/main.py**
- lifespan 中：初始化 Neo4j 约束、ping 4 个数据库、注册 Celery
- 路由 /health 返回 {"db":"ok","neo4j":"ok","redis":"ok","minio":"ok"}，任一失败返回 503
- CORS 允许 http://localhost:5173

**backend/app/llm/base.py**
- 抽象 LLMClient，方法 complete(prompt, **kwargs) -> str、extract_structured(prompt, schema) -> dict
- mock.py 返回 docs/SCHEMA.md 示例中的固定 JSON，便于流水线联调

**backend/app/graph/constraints.py**
- 启动时执行 CREATE CONSTRAINT IF NOT EXISTS ... 与 CREATE INDEX IF NOT EXISTS ...
- 约束清单严格来源于 docs/SCHEMA.md

**backend/app/tasks/pipeline_tasks.py**
- 6 个 Celery 任务对应 6 个流水线阶段，使用 chain(...) 串联
- 所有任务幂等（基于 document_id + stage_name 的 Postgres 唯一键去重）

**Makefile 关键目标**

    tunnel-up:        ssh -fN devserver && sleep 1 && $(MAKE) tunnel-status
    tunnel-status:    for p in 5432 7474 7687 6379 9000 9001; do nc -z localhost $$p && echo "ok $$p" || echo "fail $$p"; done
    backend:          cd backend && uv run uvicorn app.main:app --reload --port 8000
    worker:           cd backend && uv run celery -A app.tasks.celery_app worker -l info
    frontend:         cd frontend && pnpm install && pnpm dev
    test:             cd backend && uv run pytest -q
    lint:             uv run ruff check . && uv run mypy backend/app && cd frontend && pnpm lint

**README.md 启动步骤**
1. ssh -fN devserver（或 make tunnel-up）
2. cp .env.example .env && 编辑 .env 填入真实密码
3. cd backend && uv sync && uv run alembic upgrade head
4. make backend（终端 1） + make worker（终端 2） + make frontend（终端 3）
5. 浏览器：http://localhost:5173（前端）、http://localhost:7474（Neo4j Browser）、http://localhost:9001（MinIO 控制台）
6. 健康检查：curl http://localhost:8000/health

### 阶段 4：自检与汇报

生成完成后输出：
1. 实际生成的文件树
2. 与 PRD/SCHEMA/PIPELINE 的映射对照表（每个核心实体/阶段对应到哪个文件）
3. 已知 TODO 列表（未实现的部分）
4. 下一步建议

## 沟通约定

- 所有回复使用中文
- 任何不确定的地方，先问再写，不要假设
- 涉及到 LLM 调用的地方，v0.1 一律走 MockLLM，不调真实 API
- 涉及到密码/密钥的地方，用 .env.example 占位符，不要硬编码
