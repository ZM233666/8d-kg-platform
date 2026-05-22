/** 8D 知识图谱平台 - API 封装层（v0.2） */

import axios, { AxiosError } from 'axios'
import type { AxiosInstance, InternalAxiosRequestConfig } from 'axios'
import type {
  DocumentResponse,
  UploadResponse,
  DocumentListResponse,
  Task,
  TaskListResponse,
  ExtractionResult,
  SubgraphResponse,
  SubgraphQueryParams,
  GraphCentersResponse,
  DocumentListParams,
  ExtractionTriggerResponse,
  StructuredQueryRequest,
  StructuredQueryResponse,
} from '../types'

// =============================================================================
// Axios 实例
// =============================================================================

// 开发环境走 Vite 代理（/api → :8000），避免 CORS；生产可用 VITE_API_BASE_URL 覆盖
const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

const api: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 120_000,
})

// 请求拦截器：注入 token + 自动处理 FormData Content-Type
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('token')
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`
    }
    // 不要对 FormData 手动设置 Content-Type，让浏览器自动填充 boundary
    if (config.data instanceof FormData) {
      delete config.headers['Content-Type']
    }
    return config
  },
  (error: AxiosError) => Promise.reject(error)
)

// 响应拦截器：统一错误处理
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    const message =
      (error.response?.data as { detail?: string })?.detail ||
      error.message ||
      '未知错误'
    console.error('[API Error]', error.response?.status, message)
    return Promise.reject(error)
  }
)

// =============================================================================
// uploadApi - 文档上传 / 查询 / 删除
// =============================================================================

export const uploadApi = {
  /** 上传 Word 文档（.doc / .docx） */
  upload: async (file: File): Promise<UploadResponse> => {
    const form = new FormData()
    form.append('file', file)
    const { data } = await api.post<UploadResponse>('/documents/upload', form)
    return data
  },

  /** 获取文档列表（分页） */
  list: async (params?: DocumentListParams): Promise<DocumentListResponse> => {
    const { data } = await api.get<DocumentListResponse>('/documents', { params })
    return data
  },

  /** 获取单个文档 */
  get: async (documentId: string): Promise<DocumentResponse> => {
    const { data } = await api.get<DocumentResponse>(`/documents/${documentId}`)
    return data
  },

  /** 删除文档（软删除或硬删除） */
  delete: async (documentId: string): Promise<void> => {
    await api.delete(`/documents/${documentId}`)
  },
}

// =============================================================================
// taskApi - ExtractionRun CRUD + 重试 + 取消
// =============================================================================

export const taskApi = {
  /** 查询 extraction run 状态 */
  getRun: async (runId: string): Promise<Task> => {
    const { data } = await api.get<Task>(`/extraction-runs/${runId}`)
    return data
  },

  /** 列出所有 extraction runs（分页） */
  listRuns: async (params?: { document_id?: string; offset?: number; limit?: number }): Promise<TaskListResponse> => {
    const { data } = await api.get<TaskListResponse>('/extraction-runs', { params })
    return data
  },

  /** 触发文档抽取（异步） */
  trigger: async (documentId: string): Promise<ExtractionTriggerResponse> => {
    const { data } = await api.post<ExtractionTriggerResponse>(
      `/documents/${documentId}/extract`
    )
    return data
  },

  /** 重试失败的 extraction run */
  retry: async (runId: string): Promise<ExtractionTriggerResponse> => {
    const { data } = await api.post<ExtractionTriggerResponse>(
      `/extraction-runs/${runId}/retry`
    )
    return data
  },

  /** 取消正在运行的 extraction run */
  cancel: async (runId: string): Promise<void> => {
    await api.post(`/extraction-runs/${runId}/cancel`)
  },
}

// =============================================================================
// extractionApi - 抽取结果查询
// =============================================================================

export const extractionApi = {
  /** 查询某次 run 的完整 ExtractionResult */
  getResult: async (runId: string): Promise<ExtractionResult> => {
    const { data } = await api.get<ExtractionResult>(`/extraction-runs/${runId}/result`)
    return data
  },
}

// =============================================================================
// graphApi - 图谱数据 / 子图查询
// =============================================================================

export const graphApi = {
  /** 以指定节点为中心查询 depth 跳子图 */
  getSubgraph: async (params: SubgraphQueryParams): Promise<SubgraphResponse> => {
    const { data } = await api.get<SubgraphResponse>('/graph/subgraph', { params })
    return data
  },

  /** 可浏览的 8D 报告中心列表（知识图谱快速入口） */
  listCenters: async (limit = 20): Promise<GraphCentersResponse> => {
    const { data } = await api.get<GraphCentersResponse>('/graph/centers', { params: { limit } })
    return data
  },

  /** 全量统计 */
  getStats: async (): Promise<Record<string, unknown>> => {
    const { data } = await api.get<Record<string, unknown>>('/graph/stats')
    return data
  },
}

// =============================================================================
// queryApi - 语义搜索 / 查询历史
// =============================================================================

export const queryApi = {
  /** 语义检索相关实体 */
  search: async (query: string, topK = 10): Promise<unknown> => {
    const { data } = await api.post('/query/search', { query, topK })
    return data
  },

  /** 结构化时间筛选 */
  structuredSearch: async (payload: StructuredQueryRequest): Promise<StructuredQueryResponse> => {
    const { data } = await api.post<StructuredQueryResponse>('/query/structured', payload)
    return data
  },

  /** 查询历史 */
  history: async (limit = 20): Promise<unknown> => {
    const { data } = await api.get('/query/history', { params: { limit } })
    return data
  },
}

// =============================================================================
// authApi - 登录 / 登出 / 刷新
// =============================================================================

export const authApi = {
  login: async (username: string, password: string): Promise<{ token: string }> => {
    const { data } = await api.post<{ token: string; expires_in: number }>('/auth/login', {
      username,
      password,
    })
    localStorage.setItem('token', data.token)
    return data
  },

  logout: (): void => {
    localStorage.removeItem('token')
  },

  refresh: async (): Promise<{ token: string }> => {
    const { data } = await api.post<{ token: string }>('/auth/refresh')
    localStorage.setItem('token', data.token)
    return data
  },

  getProfile: async (): Promise<unknown> => {
    const { data } = await api.get('/auth/profile')
    return data
  },
}

// =============================================================================
// auditApi - 审核任务 / 审核操作
// =============================================================================

export const auditApi = {
  /** 获取待审核实体列表 */
  listPending: async (): Promise<unknown> => {
    const { data } = await api.get('/audit/pending')
    return data
  },

  /** 提交审核结果 */
  submit: async (payload: {
    entity_bk: string
    label: string
    decision: 'approved' | 'rejected' | 'modified'
    comment?: string
  }): Promise<void> => {
    await api.post('/audit/submit', payload)
  },
}

// =============================================================================
// 导出 api 实例（供直接调用）
// =============================================================================

export { api }
export default api
