# 前端

> **v0.1 后端骨架优先，前端将在后端 `/health` 通过后单独生成。**

## 状态

- [ ] 后端骨架生成中（进行中）
- [ ] 前端代码生成（待启动）

## 技术栈（已选定）

- React 18 + TypeScript 5+
- Vite 5+
- Ant Design 5 + ProComponents
- AntV G6 v5（图谱可视化）
- TanStack Query v5（服务端状态）
- Zustand（客户端状态）

## 下一步

待后端 `make backend` + `make tunnel-up` 成功，`curl http://localhost:8000/health` 返回 `{"status":"ok",...}` 后，再启动前端完整代码生成。
