/** 任务详情页 */

import React, { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Card,
  Descriptions,
  Tag,
  Timeline,
  Button,
  Space,
  Typography,
  Breadcrumb,
  Result,
  Divider,
  Row,
  Col,
  Statistic,
  Badge,
  message,
  Tooltip,
} from 'antd'
import {
  ArrowLeftOutlined,
  CheckCircleOutlined,
  SyncOutlined,
  ExclamationCircleOutlined,
  ClockCircleOutlined,
  ReloadOutlined,
  NodeIndexOutlined,
  FileTextOutlined,
} from '@ant-design/icons'

import { PageSpin } from '../components/PageSpin'
import { useTaskPolling } from '../hooks/useTaskPolling'
import { taskApi, extractionApi } from '../api'
import { isUuid } from '../utils/uuid'
import type { Task, TaskStatus, ExtractionResult } from '../types'

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
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${(ms / 60000).toFixed(1)}min`
}

const stageIcon = (ok: boolean) =>
  ok ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> : <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />

export const TaskDetailPage: React.FC = () => {
  const { runId } = useParams<{ runId: string }>()
  const navigate = useNavigate()
  const [messageApi, contextHolder] = message.useMessage()

  const [task, setTask] = useState<Task | null>(null)
  const [extractionResult, setExtractionResult] = useState<ExtractionResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [resultLoading, setResultLoading] = useState(false)

  const loadTask = useCallback(async () => {
    if (!runId || !isUuid(runId)) return
    setLoading(true)
    setError(null)
    try {
      const t = await taskApi.getRun(runId)
      setTask(t)
    } catch {
      setError('任务加载失败')
    } finally {
      setLoading(false)
    }
  }, [runId])

  useEffect(() => {
    if (!runId || runId === 'list' || !isUuid(runId)) {
      navigate('/extraction', { replace: true })
      return
    }
    const timer = window.setTimeout(() => {
      void loadTask()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [runId, navigate, loadTask])

  // 轮询直至 succeeded / failed（解决页面停在「等待中」不刷新）
  useTaskPolling(isUuid(runId) ? runId : undefined, (t) => setTask(t))

  const loadResult = async () => {
    if (!runId) return
    setResultLoading(true)
    try {
      const r = await extractionApi.getResult(runId)
      setExtractionResult(r)
    } catch {
      messageApi.error('抽取结果加载失败')
    } finally {
      setResultLoading(false)
    }
  }

  const handleRetry = async () => {
    if (!runId) return
    try {
      await taskApi.retry(runId)
      messageApi.success('任务已重新提交')
      loadTask()
    } catch {
      messageApi.error('重试失败')
    }
  }

  if (loading && !task) {
    return <PageSpin />
  }

  if (error || !task) {
    return (
      <Result
        status="error"
        title="任务加载失败"
        subTitle={error}
        extra={<Button type="primary" onClick={() => navigate(-1)}>返回</Button>}
      />
    )
  }

  const cfg = STATUS_CONFIG[task.status]
  const metrics = Array.isArray(task.stage_metrics) ? task.stage_metrics : []
  const stageMetricCount = Array.isArray(task.stage_metrics)
    ? task.stage_metrics.length
    : task.stage_metrics && typeof task.stage_metrics === 'object'
      ? Object.keys(task.stage_metrics).length
      : 0
  const stageMetricEntries =
    !Array.isArray(task.stage_metrics) && task.stage_metrics ? Object.entries(task.stage_metrics) : []
  const tokens = (task.token_input ?? 0) + (task.token_output ?? 0)

  return (
    <div className="detail-page">
      {contextHolder}

      {/* 面包屑 */}
      <Breadcrumb style={{ marginBottom: 16 }}
        items={[
          { title: '首页' },
          { title: '任务管理', onClick: () => navigate('/extraction') },
          { title: `任务 ${runId?.slice(0, 8)}...` },
        ]}
      />

      {/* 基本信息 */}
      <Card
        title={
          <Space>
            <Badge status={cfg.color as 'default' | 'processing' | 'success' | 'error'} />
            <Text strong>{cfg.label}</Text>
            <Text type="secondary" style={{ fontFamily: 'monospace', fontSize: 12 }}>
              {task.id}
            </Text>
          </Space>
        }
        extra={
          <Space>
            {task.status === 'failed' && (
              <Button icon={<ReloadOutlined />} onClick={handleRetry}>重试</Button>
            )}
            <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)}>返回</Button>
          </Space>
        }
        style={{ borderRadius: 8, marginBottom: 16 }}
      >
        <Descriptions column={4} bordered size="small">
          <Descriptions.Item label="任务ID" span={2}>
            <Text copyable style={{ fontFamily: 'monospace', fontSize: 11 }}>{task.id}</Text>
          </Descriptions.Item>
          <Descriptions.Item label="文档名称" span={2}>
            <Tooltip title={`文档ID: ${task.document_id}`}>
              <Text ellipsis style={{ maxWidth: 480 }}>
                {task.document_file_name || task.document_id}
              </Text>
            </Tooltip>
          </Descriptions.Item>
          <Descriptions.Item label="Pipeline">
            <Tag>{task.pipeline_version}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="LLM 模型">
            <Text code>{task.llm_model ?? '-'}</Text>
          </Descriptions.Item>
          <Descriptions.Item label="开始时间">
            {new Date(task.started_at).toLocaleString('zh-CN')}
          </Descriptions.Item>
          <Descriptions.Item label="结束时间">
            {task.finished_at ? new Date(task.finished_at).toLocaleString('zh-CN') : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="耗时">
            {formatDuration(task.started_at, task.finished_at)}
          </Descriptions.Item>
          <Descriptions.Item label="Token">
            <Text>{tokens > 0 ? `${task.token_input} in / ${task.token_output} out` : '-'}</Text>
          </Descriptions.Item>
        </Descriptions>

        {/* 错误详情 */}
        {task.status === 'failed' && task.error_detail && (
          <>
            <Divider orientation="left">错误信息</Divider>
            <div className="task-detail__log">
              <pre style={{ margin: 0, whiteSpace: 'pre-wrap', color: '#f5222d' }}>
                {JSON.stringify(task.error_detail, null, 2)}
              </pre>
            </div>
          </>
        )}
      </Card>

      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small" variant="outlined">
            <Statistic
              title="输入Token"
              value={task.token_input ?? 0}
              prefix={<FileTextOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" variant="outlined">
            <Statistic
              title="输出Token"
              value={task.token_output ?? 0}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" variant="outlined">
            <Statistic
              title="费用估算"
              value={task.cost_estimate ?? 0}
              prefix="¥"
              precision={4}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" variant="outlined">
            <Statistic
              title="阶段数"
              value={stageMetricCount}
              suffix={`/${task.status === 'succeeded' ? stageMetricCount : '?'}`}
            />
          </Card>
        </Col>
      </Row>

      {/* Stage 执行日志 */}
      {metrics.length > 0 ? (
        <Card title="执行阶段" size="small" style={{ borderRadius: 8, marginBottom: 16 }}>
          <Timeline
            className="task-detail__timeline"
            items={metrics.map((m) => ({
              dot: stageIcon(m.ok),
              children: (
                <div>
                  <Space>
                    <Text strong>{m.stage_name}</Text>
                    {m.duration_ms !== undefined && (
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        {m.duration_ms < 1000 ? `${m.duration_ms}ms` : `${(m.duration_ms / 1000).toFixed(1)}s`}
                      </Text>
                    )}
                    {!m.ok && m.error && (
                      <Tag color="error" style={{ fontSize: 10 }}>{m.error}</Tag>
                    )}
                  </Space>
                  {Object.keys(m.output_summary ?? {}).length > 0 && (
                    <div style={{ marginTop: 4 }}>
                      {Object.entries(m.output_summary).slice(0, 5).map(([k, v]) => (
                        <Text key={k} type="secondary" style={{ fontSize: 11 }}>
                          {k}={String(v)}{' '}
                        </Text>
                      ))}
                    </div>
                  )}
                </div>
              ),
            }))}
          />
        </Card>
      ) : stageMetricEntries.length > 0 ? (
        <Card title="执行阶段" size="small" style={{ borderRadius: 8, marginBottom: 16 }}>
          <Descriptions column={2} bordered size="small">
            {stageMetricEntries.map(([key, value]) => (
              <Descriptions.Item key={key} label={key}>
                <Text>{String(value)}</Text>
              </Descriptions.Item>
            ))}
          </Descriptions>
        </Card>
      ) : null}

      {/* 抽取结果 */}
      <Card
        title="抽取结果"
        size="small"
        extra={
          task.status === 'succeeded' && !extractionResult && (
            <Button size="small" icon={<ReloadOutlined />} onClick={loadResult} loading={resultLoading}>
              加载结果
            </Button>
          )
        }
        style={{ borderRadius: 8 }}
      >
        {extractionResult ? (
          <Descriptions column={2} bordered size="small">
            {extractionResult.report && (
              <>
                <Descriptions.Item label="8D报告" span={2}>
                  <Tag color="blue">{extractionResult.report.business_key}</Tag>
                  {extractionResult.report.issue_title && (
                    <Text type="secondary"> — {extractionResult.report.issue_title}</Text>
                  )}
                </Descriptions.Item>
              </>
            )}
            <Descriptions.Item label="产品事件">
              <Tag>{extractionResult.event?.business_key ?? '-'}</Tag>
              {extractionResult.event?.symptom && (
                <Text type="secondary"> — {extractionResult.event.symptom}</Text>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="失效模式数量">
              <Badge count={extractionResult.failure_modes.length} showZero color="orange" />
            </Descriptions.Item>
            <Descriptions.Item label="原因项数量">
              <Badge count={extractionResult.causes.length} showZero color="red" />
            </Descriptions.Item>
            <Descriptions.Item label="措施项数量">
              <Badge count={extractionResult.actions.length} showZero color="green" />
            </Descriptions.Item>
            <Descriptions.Item label="关系边数量">
              <Badge count={extractionResult.relationships.length} showZero />
            </Descriptions.Item>
            <Descriptions.Item label="关联实体数量">
              <Badge count={extractionResult.organizations.length + extractionResult.part_serials.length + extractionResult.product_instances.length} showZero />
            </Descriptions.Item>
            <Descriptions.Item label="操作">
              {extractionResult.report && (
                <Button
                  size="small"
                  icon={<NodeIndexOutlined />}
                  onClick={() => navigate(`/graph/EightDReport/${extractionResult.report!.business_key}`)}
                >
                  查看图谱
                </Button>
              )}
            </Descriptions.Item>
          </Descriptions>
        ) : (
          <div style={{ textAlign: 'center', padding: '24px 0' }}>
            {resultLoading ? (
              <PageSpin tip="加载抽取结果..." fullPage={false} size="default" />
            ) : (
              <Text type="secondary">
                {task.status === 'succeeded'
                  ? '点击"加载结果"查看抽取详情'
                  : '任务完成后可查看抽取结果'}
              </Text>
            )}
          </div>
        )}
      </Card>
    </div>
  )
}

export default TaskDetailPage