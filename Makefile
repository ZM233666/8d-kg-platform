.PHONY: help tunnel-up tunnel-status backend worker frontend test lint alembic

# === 开发环境 ===
# 前提：确保 .env 已配置且隧道已建立

# SSH 隧道
tunnel-up:
	@echo "建立 SSH 隧道到 devserver..."
	ssh -fN devserver
	@echo "隧道已建立，端口映射：5432(Postgres) 7474/7687(Neo4j) 6379(Redis) 9000/9001(MinIO)"
	sleep 1
	$(MAKE) tunnel-status

tunnel-status:
	@for p in 5432 7474 7687 6379 9000 9001; do \
		if nc -z localhost $$p 2>/dev/null; then \
			echo "✓ :$$p ok"; \
		else \
			echo "✗ :$$p FAIL"; \
		fi; \
	done

# 后端服务
backend:
	@echo "启动后端 FastAPI (:8000)..."
	cd backend && uv run uvicorn app.main:app --reload --port 8000

worker:
	@echo "启动 Celery worker..."
	cd backend && uv run celery -A app.tasks.celery_app worker -l info

# 数据库迁移
alembic:
	@echo "运行 Alembic 迁移..."
	cd backend && uv run alembic upgrade head

# 前端
frontend:
	@echo "启动前端开发服务器 (127.0.0.1:5173)..."
	cd frontend && if [ -d node_modules ]; then \
		npm run dev -- --host 127.0.0.1 --port 5173; \
	else \
		npm install && npm run dev -- --host 127.0.0.1 --port 5173; \
	fi

# 测试
test:
	@echo "运行后端测试..."
	cd backend && uv run pytest -q

test-cov:
	cd backend && uv run pytest --cov=app --cov-report=term-missing

# 代码检查
lint:
	@echo "Ruff check..."
	cd backend && uv run ruff check .
	@echo "Mypy check..."
	cd backend && uv run mypy app
	@echo "Prettier check (frontend)..."
	@if [ -f frontend/package.json ]; then \
		cd frontend && pnpm lint; \
	else \
		echo "frontend not generated yet, skipping"; \
	fi

format:
	@echo "Ruff format..."
	cd backend && uv run ruff format .
	@echo "Prettier format..."
	@if [ -f frontend/package.json ]; then \
		cd frontend && pnpm format; \
	else \
		echo "frontend not generated yet, skipping"; \
	fi

# 完整开发启动（4 个终端分别执行）
dev:
	@echo "=== 启动顺序 ==="
	@echo "终端 1: make tunnel-up"
	@echo "终端 2: make backend"
	@echo "终端 3: make worker"
	@echo "终端 4: make frontend"
	@echo "=== 健康检查 ==="
	@echo "curl http://localhost:8000/api/v1/health"

help:
	@echo "8D KG Platform 开发命令"
	@echo ""
	@echo "tunnel-up      建立 SSH 隧道（需先配置 .env）"
	@echo "tunnel-status  检查所有隧道端口连通性"
	@echo "backend        启动 FastAPI 后端 (:8000)"
	@echo "worker         启动 Celery worker"
	@echo "frontend       启动前端 (127.0.0.1:5173)"
	@echo "alembic        运行数据库迁移"
	@echo "test           运行测试"
	@echo "lint           代码静态检查"
	@echo "format         代码格式化"
