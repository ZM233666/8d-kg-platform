/** 实体详情页 */

import React, { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Card,
  Descriptions,
  Tag,
  Table,
  Button,
  Space,
  Typography,
  Breadcrumb,
  Result,
  Divider,
  Tooltip,
  Badge,
  Row,
  Col,
} from 'antd'
import {
  ArrowLeftOutlined,
  NodeIndexOutlined,
  ShareAltOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'

import { PageSpin } from '../components/PageSpin'
import { graphApi } from '../api'
import { useSelectedEntityStore } from '../store'
import { REVIEW_STATUS_OPTIONS, SENSITIVITY_OPTIONS, ENTITY_LABELS } from '../types'
import type { SubgraphNode, SubgraphRelationship, SubgraphResponse } from '../types'

const { Text, Title } = Typography

const LABEL_COLORS: Record<string, string> = {
  EightDReport: '#1677ff',
  ProductEvent: '#722ed1',
  FailureMode: '#d46b08',
  CauseItem: '#d4380d',
  ActionItem: '#389e0d',
  ProductInstance: '#08979c',
  PartSerial: '#c2c2c2',
  Organization: '#531dab',
  Chunk: '#8c8c8c',
}

const LABEL_CHINESE: Record<string, string> = {
  EightDReport: '8D报告',
  ProductEvent: '产品事件',
  FailureMode: '失效模式',
  CauseItem: '原因项',
  ActionItem: '措施项',
  ProductInstance: '产品实例',
  PartSerial: '部件序列',
  Organization: '组织',
  Chunk: '文档块',
}

// 关系显示配置
const REL_CN: Record<string, string> = {
  HAS_8D_REPORT: '关联8D报告',
  RELATED_FAILURE_MODE: '关联失效模式',
  ROOT_CAUSE: '根因',
  CORRECTIVE_ACTION: '纠正措施',
  PREVENTIVE_ACTION: '预防措施',
  VERIFIES_CAUSE: '验证原因',
  RESPONSIBLE_ORG: '责任组织',
  SUPPLIED_BY: '供应商',
  MENTIONED_IN: '提及',
  MENTIONS: '被提及',
  HAPPENED_ON: '发生于',
}

interface EntityNode extends SubgraphNode {
  label: string
}

export const EntityDetailPage: React.FC = () => {
  const { label, businessKey } = useParams<{ label: string; businessKey: string }>()
  const navigate = useNavigate()
  const { setEntity } = useSelectedEntityStore()

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [node, setNode] = useState<EntityNode | null>(null)
  const [subgraph, setSubgraph] = useState<SubgraphResponse | null>(null)

  useEffect(() => {
    if (!label || !businessKey) return
    loadEntity()
  }, [label, businessKey])

  const loadEntity = async () => {
    if (!label || !businessKey) return
    setLoading(true)
    setError(null)
    try {
      const data = await graphApi.getSubgraph({
        label,
        business_key: businessKey,
        depth: 1,
        exclude_chunks: true,
      })
      setSubgraph(data)
      const found = data.nodes.find((n) => n.business_key === businessKey)
      if (found) {
        setNode({ ...found, label })
        setEntity(found, label, businessKey)
      } else {
        setError('实体未找到')
      }
    } catch {
      setError('加载失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }

  // 邻居关系
  const relationships: SubgraphRelationship[] = subgraph?.relationships ?? []

  // 邻居节点
  const neighborNodes: EntityNode[] = (subgraph?.nodes ?? [])
    .filter((n) => n.business_key !== businessKey)
    .map((n) => ({
      ...n,
      label: n.labels?.[0] ?? 'Unknown',
    }))

  // 关系列
  const relColumns: ColumnsType<SubgraphRelationship> = [
    {
      title: '关系类型',
      dataIndex: 'type',
      key: 'type',
      width: 160,
      render: (v: string) => (
        <Tag color={v.startsWith('ROOT') ? 'red' : v.startsWith('CORRECTIVE') ? 'green' : 'blue'}>
          {REL_CN[v] ?? v}
        </Tag>
      ),
    },
    {
      title: '方向',
      key: 'direction',
      width: 80,
      render: (_, r) => (
        <Text type="secondary">
          {r.start_bk === businessKey ? '→ 出' : '← 入'}
        </Text>
      ),
    },
    {
      title: '关联实体',
      key: 'target',
      render: (_, r) => {
        const isStart = r.start_bk === businessKey
        const bk = isStart ? r.end_bk : r.start_bk
        const lt = isStart ? r.end_label : r.start_label
        return (
          <Button
            type="link"
            size="small"
            onClick={() => navigate(`/entity/${lt}/${bk}`)}
          >
            {LABEL_CHINESE[lt ?? ''] ?? lt}：{bk}
          </Button>
        )
      },
    },
    {
      title: '属性',
      key: 'props',
      ellipsis: true,
      render: (_, r) => {
        const props = r.properties ?? {}
        const entries = Object.entries(props).slice(0, 3)
        return entries.length > 0 ? (
          <Text type="secondary" style={{ fontSize: 11 }}>
            {entries.map(([k, v]) => `${k}=${String(v)}`).join(', ')}
          </Text>
        ) : '-'
      },
    },
  ]

  const neighborColumns: ColumnsType<EntityNode> = [
    {
      title: '类型',
      dataIndex: 'label',
      key: 'label',
      width: 120,
      render: (v: string) => (
        <Tag color={LABEL_COLORS[v] ?? 'default'}>
          {LABEL_CHINESE[v] ?? v}
        </Tag>
      ),
    },
    {
      title: 'business_key',
      dataIndex: 'business_key',
      key: 'business_key',
      ellipsis: true,
      render: (v: string, record) => (
        <Button type="link" size="small" onClick={() => navigate(`/entity/${record.label}/${v}`)}>
          {v}
        </Button>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_, record) => (
        <Space>
          <Button size="small" icon={<NodeIndexOutlined />} onClick={() => navigate(`/graph/${record.label}/${record.business_key}`)}>
            图谱
          </Button>
        </Space>
      ),
    },
  ]

  if (loading) {
    return <PageSpin />
  }

  if (error || !node) {
    return (
      <Result
        status="error"
        title="实体加载失败"
        subTitle={error}
        extra={<Button type="primary" onClick={() => navigate(-1)}>返回</Button>}
      />
    )
  }

  const props = node.properties ?? {}
  const statusValue = (props.review_status as string) ?? 'auto_committed'
  const sensitivityValue = (props.sensitivity as string) ?? 'restricted'

  return (
    <div className="detail-page">
      {/* 面包屑 */}
      <Breadcrumb
        style={{ marginBottom: 16 }}
        items={[
          { title: '首页' },
          { title: '知识图谱', onClick: () => navigate('/graph') },
          { title: LABEL_CHINESE[label ?? ''] ?? label, onClick: () => navigate(`/entity/${label}/${businessKey}`) },
        ]}
      />

      {/* 基本信息 */}
      <Card
        title={
          <Space>
            <Tag color={LABEL_COLORS[label ?? ''] ?? 'default'} style={{ fontSize: 14, padding: '2px 8px' }}>
              {LABEL_CHINESE[label ?? ''] ?? label}
            </Tag>
            <Text code>{businessKey}</Text>
          </Space>
        }
        extra={
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)}>返回</Button>
        }
        style={{ borderRadius: 8, marginBottom: 16 }}
      >
        <Descriptions column={3} bordered size="small">
          <Descriptions.Item label="business_key" span={2}>
            <Text copyable style={{ fontFamily: 'monospace' }}>{businessKey}</Text>
          </Descriptions.Item>
          <Descriptions.Item label="类型">
            <Tag color={LABEL_COLORS[label ?? ''] ?? 'default'}>{LABEL_CHINESE[label ?? ''] ?? label}</Tag>
          </Descriptions.Item>

          {/* 通用治理字段 */}
          {props.confidence !== undefined && (
            <Descriptions.Item label="置信度">
              <Badge
                status={Number(props.confidence) > 0.8 ? 'success' : Number(props.confidence) > 0.5 ? 'processing' : 'error'}
                text={`${(Number(props.confidence) * 100).toFixed(0)}%`}
              />
            </Descriptions.Item>
          )}
          {props.review_status && (
            <Descriptions.Item label="审核状态">
              <Text>{REVIEW_STATUS_OPTIONS.find((s) => s === statusValue) ? statusValue : statusValue}</Text>
            </Descriptions.Item>
          )}
          {props.sensitivity && (
            <Descriptions.Item label="敏感级别">
              <Text>{SENSITIVITY_OPTIONS.find((s) => s === sensitivityValue) ? sensitivityValue : sensitivityValue}</Text>
            </Descriptions.Item>
          )}
          {props.created_at && (
            <Descriptions.Item label="创建时间">
              {new Date(props.created_at as string).toLocaleString('zh-CN')}
            </Descriptions.Item>
          )}
          {props.updated_at && (
            <Descriptions.Item label="更新时间">
              {new Date(props.updated_at as string).toLocaleString('zh-CN')}
            </Descriptions.Item>
          )}
        </Descriptions>

        {/* 业务特有字段（除治理字段外的其他字段） */}
        {Object.entries(props).filter(([k]) => !['confidence', 'review_status', 'sensitivity', 'created_at', 'updated_at', 'owner_id', 'extraction_version', 'schema_version'].includes(k)).length > 0 && (
          <>
            <Divider orientation="left">业务属性</Divider>
            <Row gutter={[16, 12]}>
              {Object.entries(props)
                .filter(([k]) => !['confidence', 'review_status', 'sensitivity', 'created_at', 'updated_at', 'owner_id', 'extraction_version', 'schema_version', 'supporting_chunks', 'source_doc_id', 'source_section', 'node_id', 'business_key'].includes(k))
                .map(([k, v]) => (
                  <Col key={k} span={12}>
                    <Text type="secondary" style={{ fontSize: 12 }}>{k}</Text>
                    <div style={{ wordBreak: 'break-all' }}>
                      <Text>{typeof v === 'object' ? JSON.stringify(v) : String(v ?? '-')}</Text>
                    </div>
                  </Col>
                ))}
            </Row>
          </>
        )}
      </Card>

      {/* 邻居节点 */}
      {neighborNodes.length > 0 && (
        <Card title={`关联实体（${neighborNodes.length}）`} size="small" style={{ borderRadius: 8, marginBottom: 16 }}>
          <Table
            columns={neighborColumns}
            dataSource={neighborNodes}
            rowKey="business_key"
            pagination={false}
            size="small"
          />
        </Card>
      )}

      {/* 关系列表 */}
      {relationships.length > 0 && (
        <Card title={`关系边（${relationships.length}）`} size="small" style={{ borderRadius: 8 }}>
          <Table
            columns={relColumns}
            dataSource={relationships}
            rowKey={(_, i) => String(i)}
            pagination={false}
            size="small"
            scroll={{ x: 600 }}
          />
        </Card>
      )}
    </div>
  )
}

export default EntityDetailPage