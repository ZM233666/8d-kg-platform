/** 文档列表页（占位） */

import React from 'react'
import { Card, Typography, Space, Table, Tag, Button, message } from 'antd'
import { DeleteOutlined, UploadOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { useNavigate } from 'react-router-dom'

import { uploadApi, taskApi } from '../api'
import { useTaskStore } from '../store'
import type { DocumentResponse } from '../types'

const { Text } = Typography

export const DocumentListPage: React.FC = () => {
  const navigate = useNavigate()
  const [messageApi, contextHolder] = message.useMessage()
  const [data, setData] = React.useState<DocumentResponse[]>([])
  const [loading, setLoading] = React.useState(false)
  const addTask = useTaskStore((s) => s.addTask)

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
      render: (v: number) => v < 1024 * 1024 ? `${(v / 1024).toFixed(1)} KB` : `${(v / 1024 / 1024).toFixed(1)} MB`,
    },
    {
      title: '类型',
      dataIndex: 'mime_type',
      key: 'mime_type',
      width: 80,
      render: (v: string) => <Tag>{v.includes('word') ? 'Word' : v.includes('pdf') ? 'PDF' : 'Excel'}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (v: string) => <Tag color={v === 'extracted' ? 'green' : 'default'}>{v}</Tag>,
    },
    {
      title: '上传时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (v: string) => new Date(v).toLocaleString('zh-CN'),
    },
    {
      title: 'SHA256',
      dataIndex: 'sha256',
      key: 'sha256',
      ellipsis: true,
      render: (v: string) => <Text type="secondary" style={{ fontSize: 11, fontFamily: 'monospace' }}>{v.slice(0, 12)}...</Text>,
    },
    {
      title: '操作',
      key: 'action',
      width: 140,
      render: (_, record) => (
        <Space>
          <Button size="small" type="primary" onClick={() => handleExtract(record)}>
            抽取
          </Button>
          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(record)} />
        </Space>
      ),
    },
  ]

  return (
    <div>
      {contextHolder}
      <Card
        title="文档列表"
        extra={<Button type="primary" icon={<UploadOutlined />} onClick={() => navigate('/upload')}>上传</Button>}
        style={{ borderRadius: 8 }}
      >
        <Table
          columns={columns}
          dataSource={data}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 条` }}
        />
      </Card>
    </div>
  )
}

export default DocumentListPage