/** 知识图谱可视化页面 */

import React, { useEffect, useRef, useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import {
  Card,
  Input,
  Button,
  Typography,
  Tag,
  message,
  Tooltip,
  Switch,
  Segmented,
} from 'antd'
import { PageSpin } from '../../components/PageSpin'
import {
  SearchOutlined,
  ReloadOutlined,
  ClearOutlined,
  ExpandOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
  ApartmentOutlined,
  NodeIndexOutlined,
} from '@ant-design/icons'
import type { Graph, GraphData, NodeData } from '@antv/g6'

import { graphApi } from '../../api'
import { useSelectedEntityStore } from '../../store'
import type {
  GraphCenterItem,
  SubgraphResponse,
  SubgraphNode,
} from '../../types'
import styles from './GraphPage.module.css'

const { Text, Title } = Typography

const LABEL_COLORS: Record<string, string> = {
  EightDReport: '#3b82f6',
  ProductEvent: '#8b5cf6',
  FailureMode: '#f59e0b',
  CauseItem: '#ef4444',
  ActionItem: '#10b981',
  ProductInstance: '#06b6d4',
  PartSerial: '#94a3b8',
  Organization: '#6366f1',
  Chunk: '#64748b',
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

const REL_CN: Record<string, string> = {
  HAS_8D_REPORT: '关联报告',
  RELATED_FAILURE_MODE: '失效模式',
  ROOT_CAUSE: '根因',
  CORRECTIVE_ACTION: '纠正措施',
  PREVENTIVE_ACTION: '预防措施',
  VERIFIES_CAUSE: '验证原因',
  RESPONSIBLE_ORG: '责任组织',
  SUPPLIED_BY: '供应商',
  MENTIONED_IN: '提及',
  HAPPENED_ON: '发生于',
  RELATED_SERIAL: '关联序列',
  AFFECTED_PRODUCT: '影响产品',
  AFFECTED_SERIAL: '影响部件',
  TARGET_PRODUCT: '针对产品',
  TARGET_SERIAL: '针对部件',
  INSTALLED_ON: '安装于',
}

const HIDDEN_PROPS = new Set([
  'extraction_version',
  'schema_version',
  'review_status',
  'sensitivity',
  'confidence',
  'supporting_chunks',
  'source_section',
  'source_doc_id',
  'node_id',
  'created_at',
  'updated_at',
])

const PROP_LABELS: Record<string, string> = {
  issue_title: '问题标题',
  report_no: '报告编号',
  report_status: '状态',
  symptom: '现象',
  event_type: '事件类型',
  title: '标题',
  mode_name: '失效描述',
  cause_type: '原因类型',
  action_type: '措施类型',
  org_name: '组织名称',
  d2_problem_statement: 'D2 问题',
  d4_root_cause_summary: 'D4 根因',
}

let G6: typeof import('@antv/g6') | null = null

async function getG6() {
  if (!G6) {
    G6 = await import('@antv/g6')
  }
  return G6
}

function nodeDisplayName(n: SubgraphNode): string {
  const props = n.properties ?? {}
  const candidates = [
    props.issue_title,
    props.title,
    props.mode_name,
    props.symptom,
    props.org_name,
  ]
  for (const c of candidates) {
    if (typeof c === 'string' && c.trim()) {
      const t = c.trim()
      return t.length > 14 ? `${t.slice(0, 14)}…` : t
    }
  }
  const bk = n.business_key ?? ''
  return bk.length > 16 ? `${bk.slice(0, 16)}…` : bk
}

function nodeSize(label: string): number {
  if (label === 'EightDReport') return 44
  if (label === 'ProductEvent') return 38
  return 32
}

function resolveNodeColor(labelType: string): string {
  return LABEL_COLORS[labelType] ?? '#64748b'
}

/** G6 全局 node.style 会覆盖 datum.style，必须用函数按 labelType 着色 */
function buildNodeStyle(datum: NodeData, centerBk: string) {
  const labelType = String(datum.data?.labelType ?? 'Unknown')
  const color = String(datum.data?.nodeColor ?? resolveNodeColor(labelType))
  const isCenter = datum.id === centerBk
  const displayName = String(datum.data?.displayName ?? datum.id ?? '')
  return {
    size: nodeSize(labelType),
    fill: color,
    stroke: isCenter ? '#ffffff' : color,
    lineWidth: isCenter ? 3 : 1.5,
    shadowColor: isCenter ? color : 'transparent',
    shadowBlur: isCenter ? 14 : 0,
    labelText: displayName,
    labelFill: '#e2e8f0',
    labelFontSize: 10,
    labelFontWeight: 500,
    labelPlacement: 'bottom' as const,
    labelOffsetY: 8,
  }
}

function buildGraphSpec(
  subgraph: SubgraphResponse,
  showEdgeLabels: boolean
): GraphData {
  const nodeIds = new Set(
    subgraph.nodes.map((n) => n.business_key).filter((bk): bk is string => Boolean(bk))
  )

  const nodes = subgraph.nodes
    .filter((n) => n.business_key)
    .map((n) => {
      const labelType = n.labels?.[0] ?? 'Unknown'
      const color = resolveNodeColor(labelType)
      return {
        id: n.business_key as string,
        data: {
          label: LABEL_CHINESE[labelType] ?? labelType,
          labelType,
          nodeColor: color,
          business_key: n.business_key ?? '',
          displayName: nodeDisplayName(n),
          properties: n.properties ?? {},
        },
      }
    })

  const edges = subgraph.relationships
    .filter(
      (r) =>
        r.start_bk &&
        r.end_bk &&
        nodeIds.has(r.start_bk) &&
        nodeIds.has(r.end_bk)
    )
    .map((r, i) => ({
      id: `e-${i}-${r.type}`,
      source: r.start_bk as string,
      target: r.end_bk as string,
      data: { label: r.type, relCn: REL_CN[r.type ?? ''] ?? r.type },
      style: {
        stroke: '#475569',
        lineWidth: 1.2,
        opacity: 0.55,
        endArrow: true,
        ...(showEdgeLabels
          ? {
              labelText: REL_CN[r.type ?? ''] ?? r.type ?? '',
              labelFill: '#94a3b8',
              labelFontSize: 9,
              labelBackground: true,
              labelBackgroundFill: 'rgba(15, 23, 42, 0.85)',
              labelPadding: [2, 4, 2, 4],
            }
          : { labelText: '' }),
      },
    }))

  return { nodes, edges } as GraphData
}

function pickDisplayProps(properties: Record<string, unknown>): [string, unknown][] {
  return Object.entries(properties)
    .filter(([k, v]) => !HIDDEN_PROPS.has(k) && v != null && v !== '' && k !== 'business_key')
    .slice(0, 8)
}

export const GraphPage: React.FC = () => {
  const routeParams = useParams<{ label?: string; businessKey?: string }>()
  const containerRef = useRef<HTMLDivElement>(null)
  const graphRef = useRef<Graph | null>(null)
  const subgraphRef = useRef<SubgraphResponse | null>(null)
  const centerBkRef = useRef('')

  const [loading, setLoading] = useState(false)
  const [initialized, setInitialized] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [centerLabel, setCenterLabel] = useState('')
  const [centerKey, setCenterKey] = useState('')
  const [subgraph, setSubgraph] = useState<SubgraphResponse | null>(null)
  const [centers, setCenters] = useState<GraphCenterItem[]>([])
  const [searchLabel, setSearchLabel] = useState('EightDReport')
  const [showEdgeLabels, setShowEdgeLabels] = useState(false)

  const { entity, label, setEntity, clearEntity } = useSelectedEntityStore()
  const [messageApi, contextHolder] = message.useMessage()

  const selectNode = useCallback(
    (nodeId: string) => {
      const found = subgraphRef.current?.nodes.find((n) => n.business_key === nodeId)
      if (!found) return
      const lt = found.labels?.[0] ?? 'Unknown'
      setEntity(found, lt, nodeId)
    },
    [setEntity]
  )

  const renderGraph = useCallback(
    async (data: SubgraphResponse, centerBk: string) => {
      const graph = graphRef.current
      if (!graph) return
      const spec = buildGraphSpec(data, showEdgeLabels)
      graph.setData(spec)
      await graph.render()
      graph.fitView()
    },
    [showEdgeLabels]
  )

  const initGraph = useCallback(async () => {
    if (!containerRef.current || graphRef.current) return

    const G = await getG6()
    const container = containerRef.current

    const graph = new G.Graph({
      container,
      width: container.clientWidth,
      height: container.clientHeight,
      background: 'transparent',
      node: {
        type: 'circle',
        style: (datum: NodeData) => buildNodeStyle(datum, centerBkRef.current),
        state: {
          selected: {
            stroke: '#ffffff',
            lineWidth: 3,
            shadowBlur: 18,
          },
        },
      },
      edge: {
        type: 'line',
        style: { stroke: '#475569', lineWidth: 1.2, endArrow: true },
      },
      layout: {
        type: 'force',
        preventOverlap: true,
        nodeSpacing: 28,
        linkDistance: 120,
        nodeStrength: -180,
        edgeStrength: 0.35,
        collideStrength: 1,
      },
      behaviors: ['drag-canvas', 'zoom-canvas', 'drag-element', 'click-select'],
    })

    graph.on('node:click', (evt) => {
      const target = (evt as { target?: { id?: string } }).target
      const id = target?.id
      if (id) selectNode(String(id))
    })

    graphRef.current = graph
    setInitialized(true)

    const ro = new ResizeObserver(() => {
      if (container && graph) {
        graph.setSize(container.clientWidth, container.clientHeight)
      }
    })
    ro.observe(container)

    return () => {
      ro.disconnect()
      graph.destroy()
      graphRef.current = null
      setInitialized(false)
    }
  }, [selectNode])

  const loadSubgraph = useCallback(
    async (nodeLabel: string, nodeBusinessKey: string) => {
      setLoading(true)
      setKeyword(nodeBusinessKey)
      setSearchLabel(nodeLabel)
      try {
        const data = await graphApi.getSubgraph({
          label: nodeLabel,
          business_key: nodeBusinessKey,
          depth: 2,
          exclude_chunks: true,
        })
        subgraphRef.current = data
        setSubgraph(data)
        setCenterLabel(nodeLabel)
        setCenterKey(nodeBusinessKey)
        centerBkRef.current = nodeBusinessKey
        clearEntity()
        await renderGraph(data, nodeBusinessKey)
      } catch {
        messageApi.error(`未找到实体：${nodeLabel} / ${nodeBusinessKey}`)
        setSubgraph(null)
        subgraphRef.current = null
      } finally {
        setLoading(false)
      }
    },
    [messageApi, renderGraph, clearEntity]
  )

  useEffect(() => {
    const cleanup = initGraph()
    return () => {
      cleanup.then((fn) => fn?.())
    }
  }, [initGraph])

  useEffect(() => {
    if (!initialized) return

    const boot = async () => {
      try {
        const res = await graphApi.listCenters(20)
        setCenters(res.items ?? [])
        if (routeParams.label && routeParams.businessKey) {
          await loadSubgraph(
            routeParams.label,
            decodeURIComponent(routeParams.businessKey)
          )
          return
        }
        const first = res.items?.[0]
        if (first?.business_key) {
          await loadSubgraph(first.label, first.business_key)
        }
      } catch {
        /* ignore */
      }
    }

    void boot()
  }, [initialized, routeParams.label, routeParams.businessKey, loadSubgraph])

  useEffect(() => {
    if (subgraph && centerKey) {
      void renderGraph(subgraph, centerKey)
    }
  }, [showEdgeLabels, subgraph, centerKey, renderGraph])

  const handleSearch = async () => {
    const bk = keyword.trim()
    if (!bk) return
    try {
      await loadSubgraph(searchLabel, bk)
    } catch {
      if (searchLabel === 'EightDReport') {
        try {
          await loadSubgraph('ProductEvent', bk)
          setSearchLabel('ProductEvent')
        } catch {
          messageApi.error('未找到该 business_key')
        }
      }
    }
  }

  const handleZoom = (factor: number) => {
    const graph = graphRef.current
    if (!graph) return
    const zoom = graph.getZoom()
    void graph.zoomTo(zoom * factor, { duration: 200 })
  }

  const entityProps = entity?.properties ? pickDisplayProps(entity.properties) : []
  const entityType = entity?.labels?.[0] ?? label ?? ''
  const entityColor = LABEL_COLORS[entityType] ?? '#64748b'

  return (
    <div className={styles.page}>
      {contextHolder}

      <header className={styles.header}>
        <div>
          <Title level={3} className={styles.headerTitle}>
            知识图谱
          </Title>
          <p className={styles.headerSub}>8D 报告实体关系可视化 · 点击节点查看详情</p>
        </div>
      </header>

      <div className={styles.workspace}>
        <Card className={styles.graphCard} bordered={false}>
          <div className={styles.toolbar}>
            <div className={styles.toolbarRow}>
              <div className={styles.searchGroup}>
                <Segmented
                  size="small"
                  value={searchLabel}
                  onChange={(v) => setSearchLabel(v as string)}
                  options={[
                    { value: 'EightDReport', label: '8D报告' },
                    { value: 'ProductEvent', label: '产品事件' },
                  ]}
                />
                <Input
                  placeholder="business_key"
                  prefix={<SearchOutlined style={{ color: '#94a3b8' }} />}
                  value={keyword}
                  onChange={(e) => setKeyword(e.target.value)}
                  onPressEnter={() => void handleSearch()}
                  allowClear
                  style={{ flex: 1, maxWidth: 320 }}
                />
                <Button type="primary" icon={<SearchOutlined />} onClick={() => void handleSearch()}>
                  查询
                </Button>
              </div>
              <Tooltip title="显示关系标签（节点多时建议关闭）">
                <Switch
                  size="small"
                  checked={showEdgeLabels}
                  onChange={setShowEdgeLabels}
                  checkedChildren="标签"
                  unCheckedChildren="标签"
                />
              </Tooltip>
              <Tooltip title="适应画布">
                <Button size="small" icon={<ExpandOutlined />} onClick={() => graphRef.current?.fitView()} />
              </Tooltip>
              <Tooltip title="刷新子图">
                <Button
                  size="small"
                  icon={<ReloadOutlined />}
                  onClick={() => centerKey && void loadSubgraph(centerLabel, centerKey)}
                  disabled={!centerKey}
                />
              </Tooltip>
              <Tooltip title="清空">
                <Button
                  size="small"
                  icon={<ClearOutlined />}
                  onClick={() => {
                    setKeyword('')
                    setSubgraph(null)
                    subgraphRef.current = null
                    setCenterLabel('')
                    setCenterKey('')
                    clearEntity()
                    graphRef.current?.setData({ nodes: [], edges: [] })
                    void graphRef.current?.render()
                  }}
                />
              </Tooltip>
            </div>
            <div className={styles.legendRow}>
              {Object.entries(LABEL_COLORS)
                .filter(([k]) => k !== 'Chunk')
                .map(([k, color]) => (
                  <span key={k} className={styles.legendChip}>
                    <span className={styles.legendDot} style={{ background: color }} />
                    {LABEL_CHINESE[k]}
                  </span>
                ))}
            </div>
          </div>

          <div className={styles.canvasWrap} ref={containerRef}>
            {loading && (
              <div className={styles.loadingMask}>
                <PageSpin tip="加载子图..." fullPage={false} />
              </div>
            )}

            {!subgraph && !loading && (
              <div className={styles.emptyState}>
                <div className={styles.emptyInner}>
                  <NodeIndexOutlined style={{ fontSize: 36, color: '#14b8a6', marginBottom: 12 }} />
                  <Text strong style={{ fontSize: 16 }}>选择中心节点以展开图谱</Text>
                  <br />
                  <Text type="secondary" style={{ fontSize: 13 }}>
                    输入 business_key 查询，或点击下方报告
                  </Text>
                  {centers.length > 0 && (
                    <div className={styles.quickReports}>
                      {centers.map((c) => (
                        <Button
                          key={c.business_key}
                          type="primary"
                          ghost
                          onClick={() => void loadSubgraph(c.label, c.business_key)}
                        >
                          {c.title || c.business_key}
                        </Button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            <div className={styles.floatingControls}>
              <Tooltip title="放大" placement="left">
                <Button className={styles.floatingBtn} icon={<ZoomInOutlined />} onClick={() => handleZoom(1.25)} />
              </Tooltip>
              <Tooltip title="缩小" placement="left">
                <Button className={styles.floatingBtn} icon={<ZoomOutOutlined />} onClick={() => handleZoom(0.8)} />
              </Tooltip>
              <Tooltip title="适应视图" placement="left">
                <Button
                  className={styles.floatingBtn}
                  icon={<ApartmentOutlined />}
                  onClick={() => graphRef.current?.fitView()}
                />
              </Tooltip>
            </div>
          </div>

          {subgraph && (
            <div className={styles.statsBar}>
              <span className={styles.statPill}>
                节点 <strong>{subgraph.stats?.node_count ?? subgraph.nodes.length}</strong>
              </span>
              <span className={styles.statPill}>
                关系 <strong>{subgraph.stats?.relationship_count ?? subgraph.relationships.length}</strong>
              </span>
              {centerKey && (
                <span className={styles.statPill}>
                  中心 <code>{centerLabel}/{centerKey}</code>
                </span>
              )}
            </div>
          )}
        </Card>

        <Card
          className={styles.detailCard}
          title={
            <span>
              <NodeIndexOutlined style={{ marginRight: 8, color: '#14b8a6' }} />
              节点详情
            </span>
          }
          bordered={false}
        >
          {entity ? (
            <>
              <div className={styles.entityHeader}>
                <span className={styles.entityBadge} style={{ background: entityColor }} />
                <div>
                  <Tag color={entityColor} style={{ marginBottom: 6 }}>
                    {LABEL_CHINESE[entityType] ?? entityType}
                  </Tag>
                  <p className={styles.entityTitle}>
                    {(entity.properties?.issue_title as string) ||
                      (entity.properties?.title as string) ||
                      (entity.properties?.symptom as string) ||
                      entity.business_key}
                  </p>
                  <div className={styles.entityKey}>{entity.business_key}</div>
                </div>
              </div>
              {entityProps.length > 0 && (
                <div className={styles.propList}>
                  {entityProps.map(([k, v]) => (
                    <div key={k} className={styles.propItem}>
                      <div className={styles.propKey}>{PROP_LABELS[k] ?? k}</div>
                      <div className={styles.propVal}>{String(v)}</div>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className={styles.detailEmpty}>
              <ApartmentOutlined style={{ fontSize: 28, color: '#cbd5e1', marginBottom: 8 }} />
              <div>点击图谱中的节点</div>
              <div style={{ fontSize: 12, marginTop: 4 }}>查看属性与关联</div>
            </div>
          )}

          {centers.length > 0 && (
            <div className={styles.reportList}>
              <div className={styles.reportListTitle}>已抽取报告</div>
              {centers.map((c) => (
                <button
                  key={c.business_key}
                  type="button"
                  className={`${styles.reportItem} ${centerKey === c.business_key ? styles.reportItemActive : ''}`}
                  onClick={() => void loadSubgraph(c.label, c.business_key)}
                >
                  <div className={styles.reportItemTitle}>{c.title || c.business_key}</div>
                  <div className={styles.reportItemMeta}>
                    {c.business_key} · {c.degree} 条关联
                  </div>
                </button>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}

export default GraphPage
