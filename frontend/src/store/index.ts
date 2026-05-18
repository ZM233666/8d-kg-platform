/** 8D 知识图谱平台 - Zustand 状态管理（v0.2） */

import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type {
  DocumentResponse,
  Task,
  SubgraphNode,
  TaskStatus,
} from '../types'

// =============================================================================
// User Store
// =============================================================================

export interface User {
  id: string
  username: string
  role: 'admin' | 'engineer' | 'viewer'
  email?: string
}

interface UserState {
  user: User | null
  token: string | null
  setUser: (user: User | null) => void
  setToken: (token: string | null) => void
  logout: () => void
}

export const useUserStore = create<UserState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      setUser: (user) => set({ user }),
      setToken: (token) => set({ token }),
      logout: () => set({ user: null, token: null }),
    }),
    { name: '8d-user' }
  )
)

// =============================================================================
// Upload Store
// =============================================================================

export type UploadStatus = 'idle' | 'uploading' | 'success' | 'error'

interface UploadState {
  status: UploadStatus
  progress: number // 0-100
  currentFile: File | null
  uploadedDocument: DocumentResponse | null
  errorMessage: string | null
  // setters
  startUpload: (file: File) => void
  setProgress: (progress: number) => void
  uploadSuccess: (document: DocumentResponse) => void
  uploadError: (message: string) => void
  resetUpload: () => void
}

export const useUploadStore = create<UploadState>()(
  persist(
    (set) => ({
      status: 'idle',
      progress: 0,
      currentFile: null,
      uploadedDocument: null,
      errorMessage: null,
      startUpload: (file) =>
        set({ status: 'uploading', progress: 0, currentFile: file, errorMessage: null, uploadedDocument: null }),
      setProgress: (progress) => set({ progress }),
      uploadSuccess: (document) =>
        set({ status: 'success', progress: 100, uploadedDocument: document }),
      uploadError: (message) =>
        set({ status: 'error', errorMessage: message }),
      resetUpload: () =>
        set({ status: 'idle', progress: 0, currentFile: null, uploadedDocument: null, errorMessage: null }),
    }),
    { name: '8d-upload' }
  )
)

// =============================================================================
// Task Store
// =============================================================================

interface TaskState {
  tasks: Task[]
  taskCount: Record<TaskStatus, number>
  selectedTaskId: string | null
  // setters
  setTasks: (tasks: Task[]) => void
  addTask: (task: Task) => void
  updateTask: (id: string, patch: Partial<Task>) => void
  removeTask: (id: string) => void
  setSelectedTaskId: (id: string | null) => void
  updateTaskCount: (tasks: Task[]) => void
}

export const useTaskStore = create<TaskState>()((set, get) => ({
  tasks: [],
  taskCount: { pending: 0, running: 0, succeeded: 0, failed: 0 },
  selectedTaskId: null,
  setTasks: (tasks) => {
    set({ tasks })
    get().updateTaskCount(tasks)
  },
  addTask: (task) => {
    const tasks = [task, ...get().tasks]
    set({ tasks })
    get().updateTaskCount(tasks)
  },
  updateTask: (id, patch) => {
    const tasks = get().tasks.map((t) => (t.id === id ? { ...t, ...patch } : t))
    set({ tasks })
    get().updateTaskCount(tasks)
  },
  removeTask: (id) => {
    const tasks = get().tasks.filter((t) => t.id !== id)
    set({ tasks })
    get().updateTaskCount(tasks)
  },
  setSelectedTaskId: (id) => set({ selectedTaskId: id }),
  updateTaskCount: (tasks) => {
    const taskCount: Record<TaskStatus, number> = {
      pending: 0,
      running: 0,
      succeeded: 0,
      failed: 0,
    }
    tasks.forEach((t) => {
      if (t.status in taskCount) {
        taskCount[t.status]++
      }
    })
    set({ taskCount })
  },
}))

// =============================================================================
// Query History Store
// =============================================================================

export interface QueryHistoryItem {
  id: string
  query: string
  timestamp: string
  resultCount?: number
}

interface QueryHistoryState {
  history: QueryHistoryItem[]
  // setters
  addQuery: (item: QueryHistoryItem) => void
  removeQuery: (id: string) => void
  clearHistory: () => void
}

export const useQueryHistoryStore = create<QueryHistoryState>()(
  persist(
    (set, get) => ({
      history: [],
      addQuery: (item) => set({ history: [item, ...get().history].slice(0, 100) }),
      removeQuery: (id) => set({ history: get().history.filter((h) => h.id !== id) }),
      clearHistory: () => set({ history: [] }),
    }),
    { name: '8d-query-history' }
  )
)

// =============================================================================
// Selected Entity Store
// =============================================================================

interface SelectedEntityState {
  entity: SubgraphNode | null
  label: string | null
  businessKey: string | null
  // setters
  setEntity: (entity: SubgraphNode | null, label?: string | null, businessKey?: string | null) => void
  clearEntity: () => void
}

export const useSelectedEntityStore = create<SelectedEntityState>()((set) => ({
  entity: null,
  label: null,
  businessKey: null,
  setEntity: (entity, label = null, businessKey = null) =>
    set({ entity, label: entity ? label : null, businessKey: entity ? businessKey : null }),
  clearEntity: () => set({ entity: null, label: null, businessKey: null }),
}))

// =============================================================================
// Theme Store
// =============================================================================

export type ThemeMode = 'light' | 'dark'
export type ThemeColor = 'default' | 'cyan' | 'purple' | 'blue' | 'geekblue' | 'green'

interface ThemeState {
  mode: ThemeMode
  color: ThemeColor
  compact: boolean
  // setters
  setMode: (mode: ThemeMode) => void
  setColor: (color: ThemeColor) => void
  toggleCompact: () => void
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      mode: 'light',
      color: 'default',
      compact: false,
      setMode: (mode) => set({ mode }),
      setColor: (color) => set({ color }),
      toggleCompact: () => set((s) => ({ compact: !s.compact })),
    }),
    { name: '8d-theme' }
  )
)

// =============================================================================
// App-level Store（聚合导出，方便组件消费）
// =============================================================================

export const useAppStore = () => ({
  user: useUserStore(),
  upload: useUploadStore(),
  tasks: useTaskStore(),
  queryHistory: useQueryHistoryStore(),
  selectedEntity: useSelectedEntityStore(),
  theme: useThemeStore(),
})

export type AppStore = ReturnType<typeof useAppStore>