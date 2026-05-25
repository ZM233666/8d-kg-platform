/** 文档列表页（占位） */

import React from 'react'
import { Card, Typography, Space, Table, Tag, Button, message, Grid, Empty } from 'antd'
import { DeleteOutlined, UploadOutlined, FileTextOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { useNavigate } from 'react-router-dom'

import { uploadApi, taskApi } from '../api'
import { useTaskStore } from '../store'
import type { DocumentResponse } from '../types'
import styles from './DocumentListPage.module.css'

const { Text } = Typography
const STATUS_META: Record<string, { color: string; text: string }> = {
  uploaded: { color: 'processing', text: '已上传' },
  extracted: { color: 'success', text: '已抽取' },
  failed: { color: 'error', text: '失败' },
}

export const DocumentListPage: React.FC = () => {
  const navigate = useNavigate()
  const screens = Grid.useBreakpoint()
  const [messageApi, contextHolder] = message.useMessage()
  const [data, setData] = React.useState<DocumentResponse[]>([])
  const [loading, setLoading] = React.useState(false)
  const addTask = useTaskStore((s) => s.addTask)
  const isMobile = !screens.md

  const loadData = React.useCallback(async () => {
    setLoading(true)
    try {
      const res = await uploadApi.list({ limit: 100 })
      setData(res.items)
    } catch {
      messageApi.error('加载失败')
    } finally {
      setLoading(false)
    }
  }, [messageApi])

  React.useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadData()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [loadData])

  const handleDelete = async (doc: DocumentResponse) => {
    try {
      await uploadApi.delete(doc.id)
      messageApi.success('已删除')
      setData((prev) => prev.filter((d) => d.id !== doc.id))
    } catch {
      messageApi.error('删除失败')
    }
  }

  const handleExtract = async (doc: DocumentResponse) => {
    try {
      const trigger = await taskApi.trigger(doc.id)
      // 拉取完整 run 对象写入 store，TaskPage 才能感知到新任务
      try {
        const fullRun = await taskApi.getRun(trigger.run_id)
        addTask(fullRun)
      } catch {
        // 写入 store 失败不影响主流程
      }
      messageApi.success('抽取任务已创建')
      navigate(`/extraction/${trigger.run_id}`)
    } catch {
      messageApi.error('创建抽取任务失败')
    }
  }

  const columns: ColumnsType<DocumentResponse> = [
    {
      title: '文件名',
      dataIndex: 'file_name',
      key: 'file_name',
      ellipsis: true,
      render: (v: string, record) => (
        <Button type="link" onClick={() => navigate(`/extraction?document_id=${record.id}`)}>
          {v}
        </Button>
      ),
    },
    {
      title: '大小',
      dataIndex: 'file_size',
      key: 'file_size',
      width: 100,
      responsive: ['sm'],
      render: (v: number) => v < 1024 * 1024 ? `${(v / 1024).toFixed(1)} KB` : `${(v / 1024 / 1024).toFixed(1)} MB`,
    },
    {
      title: '类型',
      dataIndex: 'mime_type',
      key: 'mime_type',
      width: 80,
      responsive: ['md'],
      render: (v: string) => (
        <Tag color={v.includes('word') || v.includes('officedocument.wordprocessingml') ? 'blue' : 'default'}>
          {v.includes('word') || v.includes('officedocument.wordprocessingml')
            ? 'Word'
            : '未知'}
        </Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      responsive: ['sm'],
      render: (v: string) => {
        const meta = STATUS_META[v] ?? { color: 'default', text: v || '未知' }
        return <Tag color={meta.color}>{meta.text}</Tag>
      },
    },
    {
      title: '上传时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      responsive: ['lg'],
      render: (v: string) => new Date(v).toLocaleString('zh-CN'),
    },
    {
      title: 'SHA256',
      dataIndex: 'sha256',
      key: 'sha256',
      ellipsis: true,
      responsive: ['xl'],
      render: (v: string) => <Text type="secondary" style={{ fontSize: 11, fontFamily: 'monospace' }}>{v.slice(0, 12)}...</Text>,
    },
    {
      title: '操作',
      key: 'action',
      width: 140,
      render: (_, record) => (
        <Space>
          <Button size={isMobile ? 'small' : 'middle'} type="primary" onClick={() => handleExtract(record)}>
            抽取
          </Button>
          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(record)} />
        </Space>
      ),
    },
  ]

  return (
    <div className={styles.page}>
      {contextHolder}
      <header className={styles.header}>
        <div>
          <Typography.Title level={3} className={styles.title}>
            文档列表
          </Typography.Title>
          <p className={styles.subtitle}>集中管理已上传文档，并可一键触发抽取任务</p>
        </div>
      </header>
      <Card
        className={styles.card}
        title={
          <Space size={8}>
            <FileTextOutlined style={{ color: '#1677ff' }} />
            <span>文档管理</span>
          </Space>
        }
        extra={
          <Button
            size={isMobile ? 'small' : 'middle'}
            type="primary"
            icon={<UploadOutlined />}
            onClick={() => navigate('/upload')}
          >
            上传文档
          </Button>
        }
      >
        <Table
          className={styles.table}
          size={isMobile ? 'small' : 'middle'}
          columns={columns}
          dataSource={data}
          rowKey="id"
          loading={loading}
          scroll={{ x: 1000 }}
          pagination={{
            pageSize: 20,
            showTotal: (t) => `共 ${t} 条`,
            simple: isMobile,
            size: isMobile ? 'small' : 'default',
          }}
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无文档" /> }}
        />
      </Card>
    </div>
  )
}

export default DocumentListPage
