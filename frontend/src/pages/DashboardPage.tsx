/** 仪表盘：平台概览、健康状态、图谱与任务摘要 */

import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Badge,
  Button,
  Card,
  Grid,
  Progress,
  Space,
  Statistic,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import {
  ApartmentOutlined,
  CheckCircleOutlined,
  CloudServerOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  NodeIndexOutlined,
  ReloadOutlined,
  SearchOutlined,
  ShareAltOutlined,
  SyncOutlined,
  UploadOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'

import { graphApi, healthApi, taskApi, uploadApi } from '../api'
import type {
  DocumentResponse,
  GraphCenterItem,
  GraphStatsResponse,
  HealthCheckResponse,
  Task,
  TaskStatus,
} from '../types'
import styles from './DashboardPage.module.css'

const { Title, Text } = Typography

const LABEL_CN: Record<string, string> = {
  EightDReport: '8D报告',
  ProductEvent: '产品事件',
  FailureMode: '失效模式',
  CauseItem: '原因项',
  ActionItem: '措施项',
  ProductInstance: '产品实例',
  PartSerial: '部件序列',
  Organization: '组织',
  Person: '人员',
  Chunk: '文档块',
  FailureProduct: '失效产品',
  FailureProductMention: '失效提及',
}

const LABEL_COLOR: Record<string, string> = {
  EightDReport: '#3b82f6',
  ProductEvent: '#8b5cf6',
  FailureMode: '#f59e0b',
  CauseItem: '#ef4444',
  ActionItem: '#10b981',
  ProductInstance: '#06b6d4',
  PartSerial: '#94a3b8',
  Organization: '#6366f1',
  Person: '#a3a3a3',
  Chunk: '#64748b',
}

const TASK_STATUS: Record<TaskStatus, { color: string; label: string }> = {
  pending: { color: 'default', label: '等待' },
  running: { color: 'processing', label: '运行中' },
  succeeded: { color: 'success', label: '成功' },
  failed: { color: 'error', label: '失败' },
}

const HEALTH_ITEMS: Array<{ key: keyof HealthCheckResponse; label: string; icon: React.ReactNode }> = [
  { key: 'db', label: 'PostgreSQL', icon: <DatabaseOutlined /> },
  { key: 'neo4j', label: 'Neo4j', icon: <ApartmentOutlined /> },
  { key: 'redis', label: 'Redis', icon: <CloudServerOutlined /> },
  { key: 'minio', label: 'MinIO', icon: <CloudServerOutlined /> },
]

function formatTime(iso?: string) {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function topEntries(map: Record<string, number>, limit = 6) {
  return Object.entries(map)
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
}

export const DashboardPage: React.FC = () => {
  const navigate = useNavigate()
  const screens = Grid.useBreakpoint()
  const [messageApi, contextHolder] = message.useMessage()
  const isMobile = !screens.md

  const [loading, setLoading] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  const [documents, setDocuments] = useState<DocumentResponse[]>([])
  const [docTotal, setDocTotal] = useState(0)
  const [tasks, setTasks] = useState<Task[]>([])
  const [graphStats, setGraphStats] = useState<GraphStatsResponse | null>(null)
  const [centers, setCenters] = useState<GraphCenterItem[]>([])
  const [health, setHealth] = useState<HealthCheckResponse | null>(null)
  const [loadErrors, setLoadErrors] = useState<string[]>([])

  const loadDashboard = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    const errors: string[] = []

    const [docRes, taskRes, statsRes, centersRes, healthRes] = await Promise.allSettled([
      uploadApi.list({ limit: 100 }),
      taskApi.listRuns({ limit: 30 }),
      graphApi.getStats({ exclude_chunks: true }),
      graphApi.listCenters(8),
      healthApi.check(),
    ])

    if (docRes.status === 'fulfilled') {
      setDocuments(docRes.value.items)
      setDocTotal(docRes.value.total)
    } else {
      errors.push('文档列表')
    }

    if (taskRes.status === 'fulfilled') {
      setTasks(taskRes.value.items)
    } else {
      errors.push('抽取任务')
    }

    if (statsRes.status === 'fulfilled') {
      setGraphStats(statsRes.value)
    } else {
      errors.push('图谱统计')
    }

    if (centersRes.status === 'fulfilled') {
      setCenters(centersRes.value.items ?? [])
    } else {
      errors.push('报告中心')
    }

    if (healthRes.status === 'fulfilled') {
      setHealth(healthRes.value)
    } else {
      errors.push('健康检查')
    }

    setLoadErrors(errors)
    setLastUpdated(new Date())
    if (!silent) setLoading(false)
    if (errors.length > 0 && !silent) {
      messageApi.warning(`部分数据加载失败：${errors.join('、')}`)
    }
  }, [messageApi])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadDashboard()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [loadDashboard])

  const taskCounts = useMemo(() => {
    const counts = { pending: 0, running: 0, succeeded: 0, failed: 0 }
    tasks.forEach((t) => {
      counts[t.status] += 1
    })
    return counts
  }, [tasks])

  const docStatusCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    documents.forEach((d) => {
      counts[d.status] = (counts[d.status] ?? 0) + 1
    })
    return counts
  }, [documents])

  const healthAllOk = health ? Object.values(health).every((v) => v === 'ok') : false
  const activeTasks = taskCounts.pending + taskCounts.running

  const recentTasks = tasks.slice(0, 5)
  const labelBars = topEntries(graphStats?.nodes_by_label ?? {}, 8)
  const maxLabelCount = labelBars[0]?.[1] ?? 1
  const centerPreview = centers.slice(0, 5)

  const taskColumns: ColumnsType<Task> = [
    {
      title: '文档',
      dataIndex: 'document_file_name',
      ellipsis: true,
      render: (name: string | undefined, record) => (
        <Text ellipsis style={{ maxWidth: 180 }}>
          {name || record.document_id.slice(0, 10)}
        </Text>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 88,
      render: (status: TaskStatus) => {
        const cfg = TASK_STATUS[status]
        return <Badge status={cfg.color as 'default' | 'processing' | 'success' | 'error'} text={cfg.label} />
      },
    },
    {
      title: '时间',
      dataIndex: 'started_at',
      width: 120,
      responsive: ['md'],
      render: (v: string) => formatTime(v),
    },
    {
      title: '',
      key: 'action',
      width: 56,
      render: (_, record) => (
        <Button type="link" size="small" onClick={() => navigate(`/extraction/${record.id}`)}>
          详情
        </Button>
      ),
    },
  ]

  return (
    <div className={styles.page}>
      {contextHolder}

      <header className={styles.header}>
        <div>
          <Title level={3} className={styles.title}>
            仪表盘
          </Title>
          <p className={styles.subtitle}>
            8D 知识图谱平台运行概览
            {lastUpdated && (
              <span className={styles.updatedAt}> · 更新于 {formatTime(lastUpdated.toISOString())}</span>
            )}
          </p>
        </div>
        <Space wrap>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void loadDashboard()}>
            刷新
          </Button>
          <Button type="primary" icon={<UploadOutlined />} onClick={() => navigate('/upload')}>
            上传文档
          </Button>
        </Space>
      </header>

      {loadErrors.length > 0 && (
        <div className={styles.warnBanner}>
          <WarningOutlined />
          <span>部分接口不可用（{loadErrors.join('、')}），请确认后端与隧道已启动</span>
        </div>
      )}

      <section className={styles.kpiGrid}>
        <Card className={styles.kpiCard} variant="borderless">
          <Statistic
            title="文档总数"
            value={docTotal}
            prefix={<FileTextOutlined className={styles.kpiIconDoc} />}
            suffix={
              <span className={styles.kpiSuffix}>
                已抽取 {docStatusCounts.extracted ?? 0}
              </span>
            }
          />
        </Card>
        <Card className={styles.kpiCard} variant="borderless">
          <Statistic
            title="抽取任务"
            value={tasks.length}
            prefix={<SyncOutlined className={styles.kpiIconTask} spin={activeTasks > 0} />}
            suffix={
              <span className={styles.kpiSuffix}>
                进行中 {activeTasks}
              </span>
            }
          />
        </Card>
        <Card className={styles.kpiCard} variant="borderless">
          <Statistic
            title="图谱节点"
            value={graphStats?.total_nodes ?? 0}
            prefix={<NodeIndexOutlined className={styles.kpiIconGraph} />}
            suffix={
              <span className={styles.kpiSuffix}>
                8D报告 {graphStats?.report_count ?? 0}
              </span>
            }
          />
        </Card>
        <Card className={styles.kpiCard} variant="borderless">
          <Statistic
            title="图谱关系"
            value={graphStats?.total_relationships ?? 0}
            prefix={<ShareAltOutlined className={styles.kpiIconRel} />}
            suffix={<span className={styles.kpiSuffix}>不含 Chunk</span>}
          />
        </Card>
      </section>

      <section className={styles.healthRow}>
        {HEALTH_ITEMS.map((item) => {
          const status = health?.[item.key]
          const ok = status === 'ok'
          return (
            <div key={item.key} className={`${styles.healthPill} ${ok ? styles.healthOk : styles.healthFail}`}>
              <span className={styles.healthIcon}>{item.icon}</span>
              <div>
                <div className={styles.healthLabel}>{item.label}</div>
                <div className={styles.healthStatus}>
                  {ok ? (
                    <>
                      <CheckCircleOutlined /> 正常
                    </>
                  ) : (
                    <>
                      <WarningOutlined /> {status ? '异常' : '未知'}
                    </>
                  )}
                </div>
              </div>
            </div>
          )
        })}
        <div className={`${styles.healthSummary} ${healthAllOk ? styles.healthSummaryOk : styles.healthSummaryWarn}`}>
          {healthAllOk ? '四件套全部就绪' : '存在服务异常，请检查隧道与依赖'}
        </div>
      </section>

      <section className={styles.modulesGrid}>
        <Card
          className={`${styles.panelCard} ${styles.panelCardTop}`}
          title="最近抽取任务"
          extra={
            <Button type="link" size="small" onClick={() => navigate('/extraction')}>
              查看全部
            </Button>
          }
        >
          <div className={styles.taskSummary}>
            {(['pending', 'running', 'succeeded', 'failed'] as TaskStatus[]).map((s) => (
              <Tag key={s} color={TASK_STATUS[s].color}>
                {TASK_STATUS[s].label} {taskCounts[s]}
              </Tag>
            ))}
          </div>
          <div className={`${styles.moduleScroll} ${styles.moduleScrollTop}`}>
            <Table
              size="small"
              rowKey="id"
              loading={loading}
              columns={taskColumns}
              dataSource={recentTasks}
              pagination={false}
              locale={{ emptyText: '暂无抽取任务' }}
              scroll={isMobile ? { x: 360 } : undefined}
            />
          </div>
        </Card>

        <Card
          className={`${styles.panelCard} ${styles.panelCardTop}`}
          title="图谱实体分布"
          extra={
            <Button type="link" size="small" onClick={() => navigate('/graph')}>
              打开图谱
            </Button>
          }
        >
          {labelBars.length === 0 ? (
            <Text type="secondary">暂无图谱数据</Text>
          ) : (
            <div className={styles.moduleGraphBody}>
              <div className={styles.barList}>
                {labelBars.map(([label, count]) => (
                  <div key={label} className={styles.barRow}>
                    <div className={styles.barMeta}>
                      <span className={styles.barDot} style={{ background: LABEL_COLOR[label] ?? '#94a3b8' }} />
                      <span className={styles.barLabel}>{LABEL_CN[label] ?? label}</span>
                      <span className={styles.barCount}>{count}</span>
                    </div>
                    <Progress
                      percent={Math.round((count / maxLabelCount) * 100)}
                      showInfo={false}
                      strokeColor={LABEL_COLOR[label] ?? '#94a3b8'}
                      size="small"
                    />
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>

        <Card
          className={`${styles.panelCard} ${styles.panelCardBottom}`}
          title="高关联 8D 报告"
          extra={
            <Tooltip title="按图谱关联度排序">
              <Tag color="blue">Top {centerPreview.length}</Tag>
            </Tooltip>
          }
        >
          {centers.length === 0 ? (
            <Text type="secondary">暂无已抽取报告，请先上传并运行抽取</Text>
          ) : (
            <div className={`${styles.moduleScroll} ${styles.moduleScrollBottom}`}>
              <div className={styles.reportList}>
                {centerPreview.map((c) => (
                  <button
                    key={c.business_key}
                    type="button"
                    className={styles.reportItem}
                    onClick={() => navigate(`/graph/EightDReport/${encodeURIComponent(c.business_key)}`)}
                  >
                    <div className={styles.reportTitle}>{c.title || c.business_key}</div>
                    <div className={styles.reportMeta}>
                      <code>{c.business_key}</code>
                      <span>关联 {c.degree}</span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </Card>

        <Card className={`${styles.panelCard} ${styles.panelCardBottom}`} title="快捷入口">
          <div className={styles.quickGrid}>
            <button type="button" className={styles.quickBtn} onClick={() => navigate('/upload')}>
              <UploadOutlined />
              <span>上传文档</span>
            </button>
            <button type="button" className={styles.quickBtn} onClick={() => navigate('/documents')}>
              <FileTextOutlined />
              <span>文档列表</span>
            </button>
            <button type="button" className={styles.quickBtn} onClick={() => navigate('/graph')}>
              <ShareAltOutlined />
              <span>知识图谱</span>
            </button>
            <button type="button" className={styles.quickBtn} onClick={() => navigate('/query')}>
              <SearchOutlined />
              <span>语义检索</span>
            </button>
            <button type="button" className={styles.quickBtn} onClick={() => navigate('/extraction')}>
              <SyncOutlined />
              <span>抽取任务</span>
            </button>
            <button type="button" className={styles.quickBtn} onClick={() => navigate('/graph')}>
              <ApartmentOutlined />
              <span>全图浏览</span>
            </button>
          </div>
        </Card>
      </section>
    </div>
  )
}

export default DashboardPage
