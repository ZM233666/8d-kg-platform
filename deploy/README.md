# 服务器部署（Docker Compose）

本目录用于**单机全栈部署**，与本地「SSH 隧道 + 本机进程」开发流程分离。方案说明见仓库根目录 [迁移到服务器.md](../迁移到服务器.md)。

## 前置条件

- Docker Engine + Compose v2
- 服务器 ≥16GB RAM（推荐）
- 能访问 LLM 网关（Codex / LiteLLM）

## 快速开始

### 1. 准备环境变量

```bash
cd deploy
cp .env.example .env
# 编辑 .env，填入密码与 API Key
```

`config.py` 要求仓库根存在 `.env`；compose 会将 `deploy/.env` 挂载为 `/app/.env`。

### 2. 阶段 A — 仅验证 Codex（推荐第一步）

```bash
# 在仓库根目录执行
docker compose -f deploy/docker-compose.yml build codex
docker compose -f deploy/docker-compose.yml up -d codex

curl -s http://127.0.0.1:8787/health
./deploy/scripts/codex-smoke.sh
```

### 3. 阶段 B — 基础设施

```bash
docker compose -f deploy/docker-compose.yml up -d postgres neo4j redis minio
docker compose -f deploy/docker-compose.yml run --rm migrate
```

或仅 infra：

```bash
docker compose -f deploy/docker-compose.infra.yml up -d
docker compose -f deploy/docker-compose.infra.yml run --rm migrate
```

### 4. 阶段 C — 应用（API + Worker）

```bash
docker compose -f deploy/docker-compose.yml up -d codex app-api app-worker
curl -s http://127.0.0.1:8000/api/v1/health | jq .
```

### 5. 阶段 D — 前端

```bash
docker compose -f deploy/docker-compose.yml up -d frontend
# 浏览器访问 http://<服务器IP>/
```

## 文件说明

| 文件 | 用途 |
|------|------|
| `docker-compose.yml` | 全栈编排 |
| `docker-compose.infra.yml` | 仅 PG / Neo4j / Redis / MinIO + migrate |
| `Dockerfile.python-base` | Python 依赖基础层（供构建参考） |
| `Dockerfile.codex` | Codex 抽取服务 + Codex CLI |
| `Dockerfile.app` | FastAPI + Celery 共用镜像 |
| `Dockerfile.frontend` | Vite 构建 + nginx |
| `nginx/default.conf` | 静态资源与 `/api` 反代 |
| `scripts/` | 启动、等待、冒烟脚本 |

## 常用命令

```bash
# 查看日志
docker compose -f deploy/docker-compose.yml logs -f codex
docker compose -f deploy/docker-compose.yml logs -f app-worker

# 停止
docker compose -f deploy/docker-compose.yml down

# 停止并删除数据卷（危险）
docker compose -f deploy/docker-compose.yml down -v
```

## Codex CLI 鉴权

容器内通过 `@openai/codex` 调用 `codex exec`。常见方式：

1. 在 `deploy/.env` 中设置 `OPENAI_API_KEY`，并在镜像构建/启动时执行 `codex login --api-key`（见 `scripts/codex-entrypoint.sh` 注释）
2. 挂载已登录的 `~/.codex` 配置目录（只读）

具体以你方网关文档为准；POC 阶段先保证 `codex exec` 能返回 JSON。

## 与本地开发的区别

| 本地 | 服务器（本目录） |
|------|------------------|
| `localhost` + SSH 隧道 | compose 服务名 `postgres`、`neo4j` 等 |
| `make codex-service` | 服务 `codex` |
| 根目录 `.env` | `deploy/.env` |
