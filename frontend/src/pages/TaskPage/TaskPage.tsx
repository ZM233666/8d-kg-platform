/** 任务管理页面 */

import React, { useEffect, useState, useCallback } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  Table,
  Card,
  Statistic,
  Badge,
  Button,
  Space,
  Tag,
  Typography,
  Breadcrumb,
  message,
  Tooltip,
  Popconfirm,
} from 'antd'
import {
  ReloadOutlined,
  EyeOutlined,
  DeleteOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  SyncOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'

import { useTaskStore } from '../../store'
import { taskApi } from '../../api'
import type { Task, TaskStatus } from '../../types'

const { Text } = Typography

const STATUS_CONFIG: Record<TaskStatus, { color: string; label: string; icon: React.ReactNode }> = {
  pending: { color: 'default', label: '等待中', icon: <ClockCircleOutlined /> },
  running: { color: 'processing', label: '进行中', icon: <SyncOutlined spin /> },
  succeeded: { color: 'success', label: '已完成', icon: <CheckCircleOutlined /> },
  failed: { color: 'error', label: '失败', icon: <ExclamationCircleOutlined /> },
}

const formatDuration = (started: string, finished?: string): string => {
  if (!finished) return '-'
  const ms = new Date(finished).getTime() - new Date(started).getTime()
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

export const TaskPage: React.FC = () => {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const documentId = searchParams.get('document_id') ?? undefined

  const { tasks, taskCount, setTasks, updateTask, setSelectedTaskId } = useTaskStore()
  const [messageApi, contextHolder] = message.useMessage()
  const [loading, setLoading] = useState(false)
  const polling = tasks.some((t) => t.status === 'pending' || t.status === 'running')

  // 加载任务列表（GET /extraction-runs）
  const loadTasks = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const result = await taskApi.listRuns({
        limit: 50,
        ...(documentId ? { document_id: documentId } : {}),
      })
      setTasks(result.items)
    } catch (err) {
      console.error('[TaskPage] listRuns failed', err)
      messageApi.error('任务列表加载失败，请确认后端已启动')
    } finally {
      if (!silent) setLoading(false)
    }
  }, [documentId, messageApi, setTasks])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadTasks()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [loadTasks])

  // 存在未完成任务时定时刷新列表
  useEffect(() => {
    const active = tasks.filter((t) => t.status === 'pending' || t.status === 'running')
    if (active.length === 0) {
      return
    }

    const interval = setInterval(() => {
      void loadTasks(true)
    }, 3000)

    return () => {
      clearInterval(interval)
    }
  }, [tasks, loadTasks])

  const handleRetry = async (runId: string) => {
    try {
      const result = await taskApi.retry(runId)
      messageApi.success('任务已重新提交')
      updateTask(runId, { status: 'pending', ...result })
    } catch {
      messageApi.error('重试失败')
    }
  }

  const handleCancel = async (runId: string) => {
    try {
      await taskApi.cancel(runId)
      updateTask(runId, { status: 'failed' })
      messageApi.success('任务已取消')
    } catch {
      messageApi.error('取消失败')
    }
  }

  const handleViewDetail = (task: Task) => {
    setSelectedTaskId(task.id)
    navigate(`/extraction/${task.id}`)
  }

  const columns: ColumnsType<Task> = [
    {
      title: '任务ID',
      dataIndex: 'id',
      key: 'id',
      width: 140,
      ellipsis: true,
      render: (id: string) => (
        <Tooltip title={id}>
          <Text code style={{ fontSize: 12 }}>{id.slice(0, 8)}...</Text>
        </Tooltip>
      ),
    },
    {
      title: '文档',
      dataIndex: 'document_file_name',
      key: 'document_file_name',
      width: 220,
      ellipsis: true,
      render: (name: string | undefined, record) => (
        <Tooltip title={record.document_id}>
          <Text ellipsis>{name || `${record.document_id.slice(0, 8)}...`}</Text>
        </Tooltip>
      ),
    },
    {
      title: 'Pipeline',
      dataIndex: 'pipeline_version',
      key: 'pipeline_version',
      width: 90,
      render: (v: string) => <Tag>{v}</Tag>,
    },
    {
      title: '模型',
      dataIndex: 'llm_model',
      key: 'llm_model',
      width: 100,
      render: (v?: string) => v ?? '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: TaskStatus) => {
        const cfg = STATUS_CONFIG[status]
        return (
          <Badge status={cfg.color as 'default' | 'processing' | 'success' | 'error'} text={cfg.label} />
        )
      },
    },
    {
      title: '进度',
      key: 'progress',
      width: 120,
      render: (_, record) => {
        if (record.status === 'succeeded') return <Badge status="success" text="完成" />
        if (record.status === 'failed') return <Badge status="error" text="失败" />
        if (record.status === 'pending') return <Badge status="default" text="等待" />
        // running: 估算进度
        const tokens = (record.token_input ?? 0) + (record.token_output ?? 0)
        if (tokens > 0) {
          const pct = Math.min(90, Math.round(tokens / 50))
          return <span>{pct}%</span>
        }
        return <Badge status="processing" text="运行中" />
      },
    },
    {
      title: '耗时',
      key: 'duration',
      width: 80,
      render: (_, record) => formatDuration(record.started_at, record.finished_at),
    },
    {
      title: '开始时间',
      dataIndex: 'started_at',
      key: 'started_at',
      width: 160,
      render: (v: string) => new Date(v).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      key: 'action',
      width: 140,
      fixed: 'right',
      render: (_, record) => (
        <Space size={4}>
          <Tooltip title="查看详情">
            <Button size="small" icon={<EyeOutlined />} onClick={() => handleViewDetail(record)} />
          </Tooltip>
          {(record.status === 'failed' || record.status === 'pending') && (
            <Tooltip title={record.status === 'pending' ? '重新入队' : '重试'}>
              <Popconfirm
                title={record.status === 'pending' ? '任务可能卡住，确认重新入队？' : '确认重试？'}
                onConfirm={() => handleRetry(record.id)}
              >
                <Button size="small" icon={<ReloadOutlined />} />
              </Popconfirm>
            </Tooltip>
          )}
          {(record.status === 'pending' || record.status === 'running') && (
            <Tooltip title="取消">
              <Popconfirm title="确认取消？" onConfirm={() => handleCancel(record.id)}>
                <Button size="small" danger icon={<DeleteOutlined />} />
              </Popconfirm>
            </Tooltip>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div>
      {contextHolder}

      <Breadcrumb style={{ marginBottom: 16 }} items={[{ title: '首页' }, { title: '任务管理' }]} />

      {/* 统计卡片 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 24 }}>
        <Card size="small" variant="outlined">
          <Statistic
            title="全部任务"
            value={tasks.length}
            valueStyle={{ color: '#1677ff' }}
          />
        </Card>
        <Card size="small" variant="outlined">
          <Statistic
            title="等待中"
            value={taskCount.pending}
            valueStyle={{ color: '#8c8c8c' }}
            prefix={<ClockCircleOutlined />}
          />
        </Card>
        <Card size="small" variant="outlined">
          <Statistic
            title="进行中"
            value={taskCount.running}
            valueStyle={{ color: '#1677ff' }}
            prefix={<SyncOutlined spin />}
          />
        </Card>
        <Card size="small" variant="outlined">
          <Statistic
            title="已完成"
            value={taskCount.succeeded}
            valueStyle={{ color: '#52c41a' }}
            prefix={<CheckCircleOutlined />}
          />
        </Card>
      </div>

      {/* 任务表格 */}
      <Card
        title="抽取任务列表"
        extra={
          <Button icon={<ReloadOutlined />} onClick={loadTasks} loading={loading}>
            刷新
          </Button>
        }
        style={{ borderRadius: 8 }}
      >
        <Table
          columns={columns}
          dataSource={tasks}
          rowKey="id"
          scroll={{ x: 1200 }}
          loading={loading}
          pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (total) => `共 ${total} 条` }}
        />
      </Card>

      {polling && (
        <Text type="secondary" style={{ position: 'fixed', bottom: 16, right: 16 }}>
          轮询中... <SyncOutlined spin />
        </Text>
      )}
    </div>
  )
}

export default TaskPage