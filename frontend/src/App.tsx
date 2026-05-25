/** 8D 知识图谱平台 - 根组件 */

import React, { Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ConfigProvider, App as AntApp, Result, Button, ThemeConfig } from 'antd'
import { PageSpin } from './components/PageSpin'
import zhCN from 'antd/locale/zh_CN'

import { MainLayout } from './components/layout/MainLayout'
import { UploadPage } from './pages/UploadPage/UploadPage'
import { TaskPage } from './pages/TaskPage/TaskPage'
import { QueryPage } from './pages/QueryPage/QueryPage'
import { GraphPage } from './pages/GraphPage/GraphPage'
import { EntityDetailPage } from './pages/EntityDetailPage'
import { TaskDetailPage } from './pages/TaskDetailPage'
import DashboardPage from './pages/DashboardPage'
import DocumentListPage from './pages/DocumentListPage'

// =============================================================================
// Query Client
// =============================================================================

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
})

// =============================================================================
// 主题配置
// =============================================================================

const lightTheme: ThemeConfig = {
  token: {
    colorPrimary: '#1677ff',
    borderRadius: 6,
    fontFamily: "'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif",
  },
  components: {
    Layout: {
      siderBg: '#001529',
      headerBg: '#fff',
    },
    Menu: {
      darkItemBg: '#001529',
      darkSubMenuItemBg: '#000c1a',
    },
  },
}

// =============================================================================
// 错误边界
// =============================================================================

interface ErrorBoundaryState {
  hasError: boolean
  error?: Error
}

class ErrorBoundary extends React.Component<React.PropsWithChildren, ErrorBoundaryState> {
  constructor(props: React.PropsWithChildren) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('[ErrorBoundary]', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <Result
          status="error"
          title="页面加载失败"
          subTitle={this.state.error?.message || '发生未知错误'}
          extra={
            <Button type="primary" onClick={() => window.location.reload()}>
              刷新页面
            </Button>
          }
        />
      )
    }
    return this.props.children
  }
}

// =============================================================================
// Loading Fallback
// =============================================================================

const PageLoader: React.FC = () => <PageSpin tip="页面加载中..." />

// =============================================================================
// 页面懒加载
// =============================================================================

// =============================================================================
// 路由配置
// =============================================================================

const AppRoutes: React.FC = () => {
  const navigate = useNavigate()

  return (
    <MainLayout
      activePath={window.location.pathname}
      onMenuSelect={(path) => navigate(path)}
    >
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/documents" element={<DocumentListPage />} />
          <Route path="/extraction/list" element={<Navigate to="/extraction" replace />} />
          <Route path="/extraction" element={<TaskPage />} />
          <Route path="/extraction/:runId" element={<TaskDetailPage />} />
          <Route path="/graph" element={<GraphPage />} />
          <Route path="/graph/:label/:businessKey" element={<GraphPage />} />
          <Route path="/entity/:label/:businessKey" element={<EntityDetailPage />} />
          <Route path="/query" element={<QueryPage />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </Suspense>
    </MainLayout>
  )
}

// =============================================================================
// App Root
// =============================================================================

const App: React.FC = () => {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ConfigProvider locale={zhCN} theme={lightTheme}>
          <AntApp>
            <BrowserRouter>
              <AppRoutes />
            </BrowserRouter>
          </AntApp>
        </ConfigProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  )
}

export default App