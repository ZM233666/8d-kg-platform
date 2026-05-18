/** 语义检索页面 */

import React, { useState, useCallback } from 'react'
import {
  Input,
  Select,
  Table,
  Card,
  Tag,
  Space,
  Typography,
  Breadcrumb,
  Button,
  message,
  Tooltip,
  Row,
  Col,
  Empty,
} from 'antd'
import {
  SearchOutlined,
  DeleteOutlined,
  HistoryOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'

import { useQueryHistoryStore } from '../../store'
import { queryApi } from '../../api'
import type { QueryHistoryItem } from '../../store'

const { Text } = Typography

const ENTITY_FILTER_OPTIONS = [
  { label: '全部', value: '' },
  { label: '8D报告', value: 'EightDReport' },
  { label: '产品事件', value: 'ProductEvent' },
  { label: '失效模式', value: 'FailureMode' },
  { label: '原因项', value: 'CauseItem' },
  { label: '措施项', value: 'ActionItem' },
  { label: '产品实例', value: 'ProductInstance' },
  { label: '部件序列', value: 'PartSerial' },
  { label: '组织', value: 'Organization' },
]

interface SearchResult {
  id: string
  content: string
  entity_type: string
  match_score: number
  timestamp: string
}

export const QueryPage: React.FC = () => {
  const [messageApi, contextHolder] = message.useMessage()
  const [keyword, setKeyword] = useState('')
  const [entityFilter, setEntityFilter] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [hasSearched, setHasSearched] = useState(false)

  const { history, addQuery, removeQuery, clearHistory } = useQueryHistoryStore()

  const handleSearch = useCallback(async () => {
    if (!keyword.trim()) {
      messageApi.warning('请输入搜索关键词')
      return
    }

    setLoading(true)
    setHasSearched(true)
    try {
      const data = await queryApi.search(keyword, 20)
      // 后端返回类型未知，暂做兜底处理
      const items = Array.isArray(data) ? data : (data as { items?: SearchResult[] }).items ?? []
      setResults(items as SearchResult[])
      addQuery({
        id: Date.now().toString(),
        query: keyword,
        timestamp: new Date().toISOString(),
        resultCount: items.length,
      })
    } catch {
      messageApi.error('搜索失败，请稍后重试')
      setResults([])
    } finally {
      setLoading(false)
    }
  }, [keyword, addQuery, messageApi])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') handleSearch()
  }

  const filteredResults = entityFilter
    ? results.filter((r) => r.entity_type === entityFilter)
    : results

  const resultColumns: ColumnsType<SearchResult> = [
    {
      title: '实体类型',
      dataIndex: 'entity_type',
      key: 'entity_type',
      width: 120,
      render: (v: string) => (
        <Tag color={v === 'EightDReport' ? 'blue' : v === 'ActionItem' ? 'green' : 'default'}>
          {v}
        </Tag>
      ),
    },
    {
      title: '内容摘要',
      dataIndex: 'content',
      key: 'content',
      ellipsis: true,
      render: (v: string) => (
        <Tooltip title={v}>
          <Text>{v.length > 80 ? v.slice(0, 80) + '...' : v}</Text>
        </Tooltip>
      ),
    },
    {
      title: '匹配度',
      dataIndex: 'match_score',
      key: 'match_score',
      width: 80,
      sorter: (a, b) => a.match_score - b.match_score,
      render: (v: number) => (
        <Text strong style={{ color: v > 0.8 ? '#52c41a' : v > 0.5 ? '#faad14' : '#8c8c8c' }}>
          {(v * 100).toFixed(0)}%
        </Text>
      ),
    },
    {
      title: '查询时间',
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 160,
      render: (v: string) => new Date(v).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_, record) => (
        <Space>
          <Tooltip title="查看实体详情">
            <Button size="small" icon={<SearchOutlined />} />
          </Tooltip>
        </Space>
      ),
    },
  ]

  const historyColumns: ColumnsType<QueryHistoryItem> = [
    {
      title: '查询内容',
      dataIndex: 'query',
      key: 'query',
      ellipsis: true,
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: '结果数',
      dataIndex: 'resultCount',
      key: 'resultCount',
      width: 80,
      render: (v?: number) => v ?? '-',
    },
    {
      title: '查询时间',
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 160,
      render: (v: string) => new Date(v).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_, record) => (
        <Space>
          <Tooltip title="重新搜索">
            <Button
              size="small"
              icon={<ReloadOutlined />}
              onClick={() => { setKeyword(record.query); handleSearch() }}
            />
          </Tooltip>
          <Tooltip title="删除">
            <Button size="small" danger icon={<DeleteOutlined />} onClick={() => removeQuery(record.id)} />
          </Tooltip>
        </Space>
      ),
    },
  ]

  return (
    <div>
      {contextHolder}

      <Breadcrumb style={{ marginBottom: 16 }} items={[{ title: '首页' }, { title: '语义检索' }]} />

      <Row gutter={16}>
        {/* 左侧：搜索 */}
        <Col span={17}>
          <Card title="实体检索" style={{ borderRadius: 8, marginBottom: 16 }}>
            <Space direction="vertical" style={{ width: '100%' }} size={12}>
              <Space style={{ width: '100%' }}>
                <Input
                  size="large"
                  placeholder="输入关键词，按 Enter 搜索..."
                  prefix={<SearchOutlined />}
                  value={keyword}
                  onChange={(e) => setKeyword(e.target.value)}
                  onKeyDown={handleKeyDown}
                  style={{ flex: 1 }}
                  allowClear
                />
                <Select
                  options={ENTITY_FILTER_OPTIONS}
                  value={entityFilter}
                  onChange={setEntityFilter}
                  style={{ width: 140 }}
                  placeholder="实体类型"
                />
                <Button type="primary" size="large" icon={<SearchOutlined />} onClick={handleSearch} loading={loading}>
                  搜索
                </Button>
              </Space>
            </Space>
          </Card>

          {/* 搜索结果 */}
          <Card title="检索结果" extra={<Text type="secondary">共 {filteredResults.length} 条</Text>} style={{ borderRadius: 8 }}>
            {filteredResults.length > 0 ? (
              <Table
                columns={resultColumns}
                dataSource={filteredResults}
                rowKey="id"
                loading={loading}
                pagination={{ pageSize: 10, showTotal: (t) => `共 ${t} 条` }}
              />
            ) : hasSearched ? (
              <Empty description="未找到匹配结果" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <Empty description="输入关键词开始检索" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>

        {/* 右侧：查询历史 */}
        <Col span={7}>
          <Card
            title={<><HistoryOutlined /> 查询历史</>}
            extra={
              history.length > 0 ? (
                <Button size="small" danger onClick={clearHistory}>清空</Button>
              ) : null
            }
            style={{ borderRadius: 8 }}
          >
            {history.length > 0 ? (
              <Table
                columns={historyColumns}
                dataSource={history}
                rowKey="id"
                size="small"
                pagination={{ pageSize: 10 }}
              />
            ) : (
              <Empty description="暂无查询历史" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}

export default QueryPage