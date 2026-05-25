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
  Button,
  message,
  Tooltip,
  Row,
  Col,
  Empty,
  DatePicker,
  Divider,
  Grid,
} from 'antd'
import {
  SearchOutlined,
  DeleteOutlined,
  HistoryOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import type { DatePickerProps } from 'antd'

import { useQueryHistoryStore } from '../../store'
import { queryApi } from '../../api'
import type { QueryHistoryItem } from '../../store'
import type { StructuredQueryEntityType, StructuredQueryResponse } from '../../types'
import styles from './QueryPage.module.css'

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
const ENTITY_TAG_COLOR: Record<string, string> = {
  EightDReport: 'blue',
  ProductEvent: 'purple',
  FailureMode: 'gold',
  CauseItem: 'volcano',
  ActionItem: 'green',
  ProductInstance: 'cyan',
  PartSerial: 'geekblue',
  Organization: 'magenta',
}

interface SearchResult {
  id: string
  content: string
  entity_type: string
  match_score: number
  timestamp: string
  business_key?: string
  source_doc_id?: string | null
}

const TEMPORAL_ENTITY_OPTIONS: { label: string; value: StructuredQueryEntityType }[] = [
  { label: '8D报告', value: 'EightDReport' },
  { label: '产品事件', value: 'ProductEvent' },
]

const normalizeStructuredResults = (
  data: StructuredQueryResponse,
  queriedAt: string
): SearchResult[] =>
  data.items.map((item) => ({
    id: item.business_key,
    business_key: item.business_key,
    content: item.summary || item.source_doc_id || item.business_key,
    entity_type: item.entity_type,
    match_score: item.confidence ?? 0,
    timestamp: queriedAt,
    source_doc_id: item.source_doc_id,
  }))

export const QueryPage: React.FC = () => {
  const screens = Grid.useBreakpoint()
  const [messageApi, contextHolder] = message.useMessage()
  const [keyword, setKeyword] = useState('')
  const [entityFilter, setEntityFilter] = useState('')
  const [temporalEntityType, setTemporalEntityType] = useState<StructuredQueryEntityType>('EightDReport')
  const [temporalStart, setTemporalStart] = useState<string | null>(null)
  const [temporalEnd, setTemporalEnd] = useState<string | null>(null)
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [hasSearched, setHasSearched] = useState(false)

  const { history, addQuery, removeQuery, clearHistory } = useQueryHistoryStore()
  const isMobile = !screens.md

  const handleSearch = useCallback(async (inputKeyword?: string) => {
    const resolvedKeyword = (inputKeyword ?? keyword).trim()
    if (!resolvedKeyword) {
      messageApi.warning('请输入搜索关键词')
      return
    }

    setLoading(true)
    setHasSearched(true)
    try {
      const data = await queryApi.search(resolvedKeyword, 20)
      // 后端返回类型未知，暂做兜底处理
      const items = Array.isArray(data) ? data : (data as { items?: SearchResult[] }).items ?? []
      setResults(items as SearchResult[])
      addQuery({
        id: Date.now().toString(),
        query: resolvedKeyword,
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

  const handleTemporalStartChange: DatePickerProps['onChange'] = (value) => {
    setTemporalStart(value ? value.startOf('day').toISOString() : null)
  }

  const handleTemporalEndChange: DatePickerProps['onChange'] = (value) => {
    setTemporalEnd(value ? value.endOf('day').toISOString() : null)
  }

  const handleStructuredSearch = useCallback(async () => {
    if (!temporalStart && !temporalEnd) {
      messageApi.warning('请至少选择一个时间边界')
      return
    }

    setLoading(true)
    setHasSearched(true)
    try {
      const queriedAt = new Date().toISOString()
      const filters =
        temporalEntityType === 'EightDReport'
          ? {
              report_date_from: temporalStart || undefined,
              report_date_to: temporalEnd || undefined,
            }
          : {
              occurred_at_from: temporalStart || undefined,
              occurred_at_to: temporalEnd || undefined,
            }

      const data = await queryApi.structuredSearch({
        entity_type: temporalEntityType,
        filters,
        page: 1,
        page_size: 20,
        sort_by: temporalEntityType === 'EightDReport' ? 'report_date' : 'occurred_at',
        sort_order: 'desc',
      })

      setResults(normalizeStructuredResults(data, queriedAt))
      setEntityFilter(temporalEntityType)
      messageApi.success(`已返回 ${data.pagination.total} 条时间筛选结果`)
    } catch {
      messageApi.error('时间筛选失败，请稍后重试')
      setResults([])
    } finally {
      setLoading(false)
    }
  }, [messageApi, temporalEnd, temporalEntityType, temporalStart])

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
      responsive: ['sm'],
      render: (v: string) => (
        <Tag color={ENTITY_TAG_COLOR[v] ?? 'default'}>
          {v}
        </Tag>
      ),
    },
    {
      title: '业务键',
      dataIndex: 'business_key',
      key: 'business_key',
      width: 180,
      ellipsis: true,
      responsive: ['md'],
      render: (v?: string) => <Text code>{v || '-'}</Text>,
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
      responsive: ['sm'],
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
      responsive: ['lg'],
      render: (v: string) => new Date(v).toLocaleString('zh-CN'),
    },
    {
      title: '来源文档',
      dataIndex: 'source_doc_id',
      key: 'source_doc_id',
      width: 180,
      ellipsis: true,
      responsive: ['xl'],
      render: (v?: string | null) => v || '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: () => (
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
      responsive: ['sm'],
      render: (v?: number) => v ?? '-',
    },
    {
      title: '查询时间',
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 160,
      responsive: ['xl'],
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
              onClick={() => {
                setKeyword(record.query)
                void handleSearch(record.query)
              }}
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
    <div className={styles.page}>
      {contextHolder}

      <header className={styles.header}>
        <div>
          <Typography.Title level={3} className={styles.title}>
            语义检索
          </Typography.Title>
          <p className={styles.subtitle}>关键词检索 + 时间筛选，支持历史回放</p>
        </div>
      </header>

      <Row gutter={[12, 12]}>
        {/* 左侧：搜索 */}
        <Col xs={24} lg={17}>
          <Card className={styles.card} title="实体检索" style={{ marginBottom: 12 }}>
            <Space direction="vertical" style={{ width: '100%' }} size={12}>
              <Space style={{ width: '100%' }} wrap>
                <Input
                  size={isMobile ? 'middle' : 'large'}
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
                <Button
                  type="primary"
                  size={isMobile ? 'middle' : 'large'}
                  icon={<SearchOutlined />}
                  onClick={() => {
                    void handleSearch()
                  }}
                  loading={loading}
                >
                  搜索
                </Button>
              </Space>

              <Divider style={{ margin: '4px 0' }}>时间筛选</Divider>

              <Space wrap style={{ width: '100%' }}>
                <Select
                  value={temporalEntityType}
                  options={TEMPORAL_ENTITY_OPTIONS}
                  onChange={setTemporalEntityType}
                  style={{ width: 140 }}
                />
                <DatePicker
                  placeholder={temporalEntityType === 'EightDReport' ? '报告开始日期' : '事件开始日期'}
                  onChange={handleTemporalStartChange}
                />
                <DatePicker
                  placeholder={temporalEntityType === 'EightDReport' ? '报告结束日期' : '事件结束日期'}
                  onChange={handleTemporalEndChange}
                />
                <Button size={isMobile ? 'small' : 'middle'} onClick={handleStructuredSearch} loading={loading}>
                  按时间筛选
                </Button>
              </Space>
              <Text type="secondary">
                当前支持按 {temporalEntityType === 'EightDReport' ? 'report_date' : 'occurred_at'} 做最小时间过滤。
              </Text>
            </Space>
          </Card>

          {/* 搜索结果 */}
          <Card className={styles.card} title="检索结果" extra={<Text type="secondary">共 {filteredResults.length} 条</Text>}>
            {filteredResults.length > 0 ? (
              <Table
                size={isMobile ? 'small' : 'middle'}
                columns={resultColumns}
                dataSource={filteredResults}
                rowKey="id"
                loading={loading}
                scroll={{ x: 900 }}
                pagination={{
                  pageSize: 10,
                  showTotal: (t) => `共 ${t} 条`,
                  simple: isMobile,
                  size: isMobile ? 'small' : 'default',
                }}
                locale={{ emptyText: <Empty description="暂无检索结果" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
              />
            ) : hasSearched ? (
              <Empty description="未找到匹配结果" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <Empty description="输入关键词开始检索" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>

        {/* 右侧：查询历史 */}
        <Col xs={24} lg={7}>
          <Card
            className={styles.card}
            title={<><HistoryOutlined /> 查询历史</>}
            extra={
              history.length > 0 ? (
                <Button size="small" danger onClick={clearHistory}>清空</Button>
              ) : null
            }
          >
            {history.length > 0 ? (
              <Table
                columns={historyColumns}
                dataSource={history}
                rowKey="id"
                size="small"
                scroll={{ x: 420 }}
                pagination={{ pageSize: 10, simple: true, size: 'small' }}
                locale={{ emptyText: <Empty description="暂无查询历史" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
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
