# 前端说明

8D 报告知识图谱平台前端使用 React + TypeScript + Vite 构建，当前已补齐原型页面骨架，覆盖以下主路径：

- 文档上传
- 文档列表
- 抽取任务列表与详情
- 图谱浏览
- 关键词检索

## 本地开发

在仓库根目录先启动后端与隧道，再进入前端目录启动开发服务器：

```bash
cd frontend
npm install
npm run dev
```

默认开发地址为 `http://localhost:5172`，通过 Vite 代理把 `/api` 请求转发到 `http://localhost:8000`。

## 当前状态

- 已有页面原型和接口封装
- 已配置 Ant Design、TanStack Query、Zustand、G6
- 当前仍存在若干 TypeScript 构建错误，正式联调前需要继续收敛接口与类型

## 约定

- 当前仓库以 `npm` 作为前端包管理器，提交 `package-lock.json`
- `pnpm-lock.yaml` 不纳入版本管理，避免双锁文件并存
