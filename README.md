# 8D 报告知识图谱平台

将质量管理领域的 8D 报告通过 `Reader → Splitter → TableExtractor → LLM Extractor → Vectorizer → Writer` 链路转化为可查询的知识图谱。

## 开发环境架构

**本地开发 + 远端数据库**。所有数据库已部署在远端服务器，通过 SSH 隧道暴露在本地。

```
本地 macOS 开发机                              远端服务器 aistation
/Users/.../8d-kg-platform/                    Ubuntu 22.04
                                              /opt/8d-kg-infra/
  - backend (uvicorn :8000)        SSH 公钥          4 个 Docker 容器（已就绪）
  - frontend (vite :5173)        ─────────────►       • 8dkg-postgres
                                  117.62.232.51         • 8dkg-neo4j
                                  :10022                • 8dkg-redis
                                  (frp → 内网 :22)      • 8dkg-minio
```

### SSH 隧道端口映射

| 服务         | 本地端口 | 远端容器端口 |
|--------------|----------|--------------|
| Postgres     | 5432     | 15432        |
| Neo4j HTTP   | 7474     | 17474        |
| Neo4j Bolt   | 7687     | 17687        |
| Redis        | 6379     | 26379        |
| MinIO API    | 9000     | 19000        |
| MinIO 控制台 | 9001     | 19001        |

## 快速启动

### 1. 建立 SSH 隧道

```bash
ssh -fN devserver
```

或使用 Makefile：

```bash
make tunnel-up
make tunnel-status  # 验证所有端口连通
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入真实密码和 API Key
```

**图谱可视化（默认 NeoVis.js）**：浏览器通过 Bolt 直连 Neo4j，需在 `.env` 配置 `VITE_NEO4J_*`。若需回滚到旧版 G6（经后端 REST 拉子图），设置：

```bash
VITE_GRAPH_RENDERER=g6
```

修改后需重启 `make frontend`。

### 3. 数据库迁移

```bash
cd backend
uv sync
uv run alembic upgrade head
```

### 4. 启动服务（4 个终端）

```bash
# 终端 1
make backend      # FastAPI :8000

# 终端 2
make worker      # Celery worker

# 终端 3
make frontend    # Vite :5173

# 终端 4（可选）
make tunnel-up   # 隧道守护
```

### 5. 健康检查

```bash
curl http://localhost:8000/health
# 期望返回: {"status":"ok","components":{"postgres":"ok","neo4j":"ok","redis":"ok","minio":"ok"}}
```

### 6. 访问地址

| 服务          | 地址                          |
|---------------|-------------------------------|
| 前端          | http://localhost:5173         |
| API 文档      | http://localhost:8000/api/v1/docs |
| Neo4j Browser | http://localhost:7474         |
| MinIO 控制台  | http://localhost:9001         |

## 技术栈

- **后端**：Python 3.11+ / FastAPI / SQLAlchemy 2.0 / Pydantic v2 / Celery + Redis
- **存储**：PostgreSQL 15+ (PGVector) / Neo4j Community 5.x / MinIO / Redis 7+
- **前端**：React 18 + TypeScript / Vite / Ant Design 5 + ProComponents / AntV G6
- **文档解析**：PyMuPDF / python-docx / openpyxl / pandas
- **LLM**：OpenAI-compatible 接口 / instructor 结构化输出

## 文档

- [PRD](./docs/PRD.md) — 项目方案
- [架构设计](./docs/ARCHITECTURE.md)
- [数据模型](./docs/SCHEMA.md)
- [Pipeline 组件契约](./docs/PIPELINE.md)
- [API 接口定义](./docs/API.md)
- [编码规范](./docs/CODING_STANDARDS.md)

## License

 proprietary
