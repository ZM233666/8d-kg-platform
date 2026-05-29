/** 知识图谱可视化页面（NeoVis 渲染） */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  Button,
  Card,
  Input,
  Select,
  Segmented,
  Switch,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import {
  ApartmentOutlined,
  ClearOutlined,
  ExpandOutlined,
  NodeIndexOutlined,
  ReloadOutlined,
  SearchOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
} from '@ant-design/icons'

import { graphApi } from '../../api'
import { useSelectedEntityStore } from '../../store'
import type { GraphCenterItem, SubgraphNode } from '../../types'
import styles from './GraphPage.module.css'

const { Title } = Typography

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
  MENTIONS: '提及',
  HAPPENED_ON: '发生于',
  RELATED_SERIAL: '关联序列',
  AFFECTED_PRODUCT: '影响产品',
  AFFECTED_SERIAL: '影响部件',
  TARGET_PRODUCT: '针对产品',
  TARGET_SERIAL: '针对部件',
  INSTALLED_ON: '安装于',
}

const NEOVIS_LABEL_COLOR: Record<string, string> = {
  EightDReport: '#3b82f6',
  ProductEvent: '#8b5cf6',
  FailureMode: '#f59e0b',
  CauseItem: '#ef4444',
  ActionItem: '#10b981',
  ProductInstance: '#06b6d4',
  PartSerial: '#94a3b8',
  Organization: '#6366f1',
  Person: '#a3a3a3',
  FailureProduct: '#14b8a6',
  FailureProductMention: '#22d3ee',
  Chunk: '#64748b',
}

const CORE_REL_TYPES = [
  'HAS_8D_REPORT',
  'RELATED_FAILURE_MODE',
  'ROOT_CAUSE',
  'CORRECTIVE_ACTION',
  'PREVENTIVE_ACTION',
  'VERIFIES_CAUSE',
  'HAPPENED_ON',
  'RELATED_SERIAL',
  'AFFECTED_PRODUCT',
  'AFFECTED_SERIAL',
  'RESPONSIBLE_ORG',
  'SUPPLIED_BY',
  'TARGET_PRODUCT',
  'TARGET_SERIAL',
  'INSTALLED_ON',
]

declare global {
  interface Window {
    NeoVis?: unknown
    __neovisReady?: Promise<void>
  }
}

type NeoVisInstance = {
  render: () => void
  renderWithCypher: (query: string, params?: Record<string, unknown>) => void
  registerOnEvent: (eventName: string, handler: (event: unknown) => void) => void
  network?: {
    fit: () => void
    getScale: () => number
    moveTo: (options: { scale?: number }) => void
    setOptions?: (options: Record<string, unknown>) => void
    stabilize?: () => void
    body?: {
      data?: {
        nodes?: { getIds: () => Array<string | number> }
        edges?: { getIds: () => Array<string | number> }
      }
    }
  }
}

type NeoVisCtor = new (config: Record<string, unknown>) => NeoVisInstance

const NEO_VIS_CONTAINER_ID = 'kg-neovis-canvas'
const STATIC_NEOVIS_SCRIPT = '/static/neovis.js'
const NEOVIS_FALLBACK_SCRIPTS = [
  'https://cdn.jsdelivr.net/npm/neovis.js@2.1.0/dist/neovis.js',
  'https://unpkg.com/neovis.js@2.1.0/dist/neovis.js',
]

const DEFAULT_BOLT_URL = 'bolt://127.0.0.1:7687'
const DEFAULT_BOLT_USER = 'neo4j'
const DEFAULT_BOLT_DB = 'neo4j'
const SAFE_INITIAL_CYPHER = 'MATCH (n) WHERE 1=0 RETURN n LIMIT 0'

type LayoutMode = 'neo4j' | 'stable' | 'performance'

function getPhysicsByLayoutMode(mode: LayoutMode, spread = 1.35): Record<string, unknown> {
  const springLength = Math.round(120 * spread)
  const stabilization = {
    enabled: true,
    iterations: mode === 'performance' ? 900 : 2200,
    updateInterval: 25,
    fit: true,
  }

  if (mode === 'stable') {
    return {
      enabled: true,
      solver: 'barnesHut',
      barnesHut: {
        gravitationalConstant: -12000,
        centralGravity: 0.12,
        springLength,
        springConstant: 0.03,
        damping: 0.12,
        avoidOverlap: 1,
      },
      stabilization,
    }
  }
  if (mode === 'performance') {
    return {
      enabled: true,
      solver: 'forceAtlas2Based',
      forceAtlas2Based: {
        gravitationalConstant: -60,
        springLength: Math.round(95 * spread),
        springConstant: 0.12,
        avoidOverlap: 0.6,
      },
      stabilization: { ...stabilization, iterations: 700 },
    }
  }
  // Neo4j Browser 风格：强斥力 + 较长弹簧，让连通分量自然分开
  return {
    enabled: true,
    solver: 'barnesHut',
    barnesHut: {
      gravitationalConstant: -22000,
      centralGravity: 0.08,
      springLength,
      springConstant: 0.035,
      damping: 0.1,
      avoidOverlap: 1,
    },
    stabilization,
  }
}

function buildVisConfig(
  showNodeLabels: boolean,
  _showEdgeLabels: boolean,
  layoutMode: LayoutMode,
  layoutSpread: number
): Record<string, unknown> {
  return {
    nodes: {
      shape: 'dot',
      font: {
        size: showNodeLabels ? 11 : 1,
        color: '#e2e8f0',
      },
      borderWidth: 1.5,
      scaling: {
        min: 8,
        max: 28,
      },
    },
    edges: {
      arrows: { to: { enabled: true, scaleFactor: 0.45 } },
      color: { color: '#64748b', opacity: 0.4 },
      smooth: {
        enabled: true,
        type: 'dynamic',
      },
      font: {
        size: 9,
        color: '#94a3b8',
      },
    },
    layout: {
      randomSeed: 42,
      improvedLayout: true,
    },
    physics: getPhysicsByLayoutMode(layoutMode, layoutSpread),
    interaction: {
      hover: true,
      navigationButtons: false,
      keyboard: true,
    },
  }
}

function buildNeovisLabelConfig(showNodeLabels: boolean): Record<string, unknown> {
  const common = {
    label: showNodeLabels ? 'business_key' : undefined,
    font: {
      size: showNodeLabels ? 10 : 1,
      color: '#e2e8f0',
    },
  }
  const config: Record<string, unknown> = {}
  Object.entries(NEOVIS_LABEL_COLOR).forEach(([label, color]) => {
    config[label] = {
      ...common,
      color,
    }
  })
  return config
}

function toSafeLower(input: string) {
  return input.trim().toLowerCase()
}

function loadScript(src: string, force = false) {
  return new Promise<void>((resolve, reject) => {
    const key = src
    const exists = document.querySelector(`script[data-src="${key}"]`)
    if (exists) {
      resolve()
      return
    }
    const script = document.createElement('script')
    script.src = src
    script.async = true
    script.dataset.src = key
    if (force) {
      script.dataset.force = '1'
    }
    script.onload = () => resolve()
    script.onerror = () => reject(new Error(`script load failed: ${src}`))
    document.body.appendChild(script)
  })
}

function resolveNeoVisCtor(): NeoVisCtor | undefined {
  const w = window as unknown as Record<string, unknown>
  const candidates = [w.NeoVis, w.Neovis, w.neoVis]
  for (const item of candidates) {
    if (!item) continue
    if (typeof item === 'function') {
      return item as NeoVisCtor
    }
    if (typeof (item as { default?: unknown }).default === 'function') {
      return (item as { default: NeoVisCtor }).default
    }
  }
  return undefined
}

async function ensureNeoVisCtor(): Promise<NeoVisCtor> {
  await loadScript(STATIC_NEOVIS_SCRIPT)
  if (window.__neovisReady) {
    try {
      await window.__neovisReady
    } catch {
      // 进入多源重试逻辑
    }
  }

  let ctor = resolveNeoVisCtor()
  if (ctor) return ctor

  for (const src of NEOVIS_FALLBACK_SCRIPTS) {
    try {
      await loadScript(`${src}?t=${Date.now()}`, true)
      ctor = resolveNeoVisCtor()
      if (ctor) return ctor
    } catch {
      // 尝试下一个源
    }
  }

  throw new Error('NeoVis not loaded. Please verify /static/neovis.js or CDN accessibility.')
}

export const GraphPageNeoVis: React.FC = () => {
  const routeParams = useParams<{ label?: string; businessKey?: string }>()
  const [messageApi, contextHolder] = message.useMessage()
  const { entity, label, setEntity, clearEntity } = useSelectedEntityStore()

  const vizRef = useRef<NeoVisInstance | null>(null)
  const [loading, setLoading] = useState(false)
  const [centers, setCenters] = useState<GraphCenterItem[]>([])

  const [searchLabel, setSearchLabel] = useState('EightDReport')
  const [keyword, setKeyword] = useState('')
  const [filterKeyword, setFilterKeyword] = useState('')
  const [showNodeLabels, setShowNodeLabels] = useState(false)
  const [showEdgeLabels, setShowEdgeLabels] = useState(false)
  const [layoutMode, setLayoutMode] = useState<LayoutMode>('neo4j')
  const [layoutSpread, setLayoutSpread] = useState(1.45)
  const [nodeTypeFilters, setNodeTypeFilters] = useState<string[]>([])
  const [relTypeFilters, setRelTypeFilters] = useState<string[]>([])
  const [globalRelLimit, setGlobalRelLimit] = useState(300)
  const [globalExcludeChunks, setGlobalExcludeChunks] = useState(true)

  const [stats, setStats] = useState({ nodes: 0, relationships: 0 })
  const [centerTag, setCenterTag] = useState('GlobalGraph/ALL')
  const [graphError, setGraphError] = useState<string | null>(null)

  const [nodeTypeOptions, setNodeTypeOptions] = useState<Array<{ value: string; label: string }>>([])
  const [relTypeOptions, setRelTypeOptions] = useState<Array<{ value: string; label: string }>>([])

  const boltConfig = useMemo(
    () => ({
      serverUrl: import.meta.env.VITE_NEO4J_BOLT_URL || DEFAULT_BOLT_URL,
      serverUser: import.meta.env.VITE_NEO4J_USERNAME || DEFAULT_BOLT_USER,
      serverPassword: import.meta.env.VITE_NEO4J_PASSWORD ?? '',
      serverDatabase: import.meta.env.VITE_NEO4J_DATABASE || DEFAULT_BOLT_DB,
    }),
    []
  )

  const buildGlobalCypher = useCallback(() => {
    const where: string[] = ['n.business_key IS NOT NULL', 'm.business_key IS NOT NULL']
    if (globalExcludeChunks) {
      where.push('NOT n:Chunk', 'NOT m:Chunk', "type(r) <> 'MENTIONED_IN'", "type(r) <> 'MENTIONS'")
    }
    if (nodeTypeFilters.length > 0) {
      where.push('any(lbl IN labels(n) WHERE lbl IN $nodeTypes)', 'any(lbl IN labels(m) WHERE lbl IN $nodeTypes)')
    }
    if (relTypeFilters.length > 0) {
      where.push('type(r) IN $relTypes')
    }
    const kw = toSafeLower(filterKeyword)
    if (kw) {
      where.push(
        "(toLower(coalesce(n.business_key,'')) CONTAINS $kw OR toLower(coalesce(m.business_key,'')) CONTAINS $kw OR toLower(coalesce(n.title,'')) CONTAINS $kw OR toLower(coalesce(m.title,'')) CONTAINS $kw)"
      )
    }
    return {
      query: `
        MATCH (n)-[r]->(m)
        WHERE ${where.join(' AND ')}
        RETURN n, r, m
        ORDER BY coalesce(r.updated_at, r.created_at) DESC
        LIMIT toInteger($relLimit)
      `,
      params: {
        nodeTypes: nodeTypeFilters,
        relTypes: relTypeFilters,
        kw,
        relLimit: Math.max(1, Math.trunc(globalRelLimit)),
      },
    }
  }, [globalExcludeChunks, nodeTypeFilters, relTypeFilters, filterKeyword, globalRelLimit])

  const buildCenterCypher = useCallback(
    (labelValue: string, businessKey: string) => ({
      query: `
        MATCH (c:\`${labelValue}\` {business_key: $centerBk})
        OPTIONAL MATCH p=(c)-[*1..2]-(n)
        WITH c, collect(DISTINCT n) + [c] AS ns
        UNWIND ns AS a
        UNWIND ns AS b
        OPTIONAL MATCH (a)-[r]->(b)
        WHERE r IS NOT NULL
          AND ($excludeChunks = false OR (NOT a:Chunk AND NOT b:Chunk AND type(r) <> 'MENTIONED_IN' AND type(r) <> 'MENTIONS'))
        RETURN a AS n, r, b AS m
        LIMIT toInteger($relLimit)
      `,
      params: {
        centerBk: businessKey,
        excludeChunks: globalExcludeChunks,
        relLimit: Math.max(1, Math.trunc(globalRelLimit)),
      },
    }),
    [globalExcludeChunks, globalRelLimit]
  )

  const readStatsFromNetwork = useCallback(() => {
    const nodes = vizRef.current?.network?.body?.data?.nodes?.getIds?.() ?? []
    const edges = vizRef.current?.network?.body?.data?.edges?.getIds?.() ?? []
    setStats({ nodes: nodes.length, relationships: edges.length })
  }, [])

  const applyLayoutModeToNetwork = useCallback((mode: LayoutMode, spread = layoutSpread) => {
    const network = vizRef.current?.network
    if (!network?.setOptions) return
    network.setOptions({
      physics: getPhysicsByLayoutMode(mode, spread),
    })
    if (network.stabilize) {
      network.stabilize()
      return
    }
    network.fit?.()
  }, [layoutSpread])

  const bootstrapNeoVis = useCallback(
    async (initialQuery: string, initialParams?: Record<string, unknown>) => {
      const NeoVis = await ensureNeoVisCtor()
      const config: Record<string, unknown> = {
        containerId: NEO_VIS_CONTAINER_ID,
        neo4j: {
          serverUrl: boltConfig.serverUrl,
          serverUser: boltConfig.serverUser,
          serverPassword: boltConfig.serverPassword,
        },
        serverDatabase: boltConfig.serverDatabase,
        labels: buildNeovisLabelConfig(showNodeLabels),
        relationships: {
          '*': {
            caption: showEdgeLabels ? true : false,
            thickness: 1,
          },
        },
        visConfig: buildVisConfig(showNodeLabels, showEdgeLabels, layoutMode, layoutSpread),
        // 避免首次 render 时因参数缺失触发 Neo4j 参数错误
        initialCypher: SAFE_INITIAL_CYPHER,
      }

      const viz = new NeoVis(config)
      vizRef.current = viz

      viz.registerOnEvent('completed', () => {
        applyLayoutModeToNetwork(layoutMode, layoutSpread)
        readStatsFromNetwork()
      })
      viz.registerOnEvent('error', (event: unknown) => {
        const detail =
          (event as { error?: { message?: string } })?.error?.message ||
          JSON.stringify(event)
        const tip = `NeoVis 渲染失败：${detail || 'Bolt 连接不可用或认证失败'}`
        messageApi.error(tip)
        setGraphError(tip)
      })
      viz.registerOnEvent('clickNode', (event: unknown) => {
        const nodePayload = (event as { node?: { raw?: { labels?: string[]; properties?: Record<string, unknown> } } })?.node?.raw
        if (!nodePayload) return
        const labels = nodePayload.labels ?? []
        const props = nodePayload.properties ?? {}
        const bk = String(props.business_key ?? '')
        const node: SubgraphNode = {
          business_key: bk || null,
          labels,
          properties: props,
        }
        setEntity(node, labels[0] ?? 'Unknown', bk || undefined)
      })

      viz.render()
      viz.renderWithCypher(initialQuery, initialParams ?? {})
    },
    [boltConfig, showEdgeLabels, showNodeLabels, layoutMode, layoutSpread, readStatsFromNetwork, messageApi, setEntity, applyLayoutModeToNetwork]
  )

  const runCypher = useCallback(
    async (query: string, params?: Record<string, unknown>) => {
      setLoading(true)
      setGraphError(null)
      try {
        if (!vizRef.current) {
          await bootstrapNeoVis(query, params)
        } else {
          vizRef.current.renderWithCypher(query, params)
          readStatsFromNetwork()
        }
      } catch (error) {
        console.error(error)
        const detail = error instanceof Error ? error.message : String(error)
        const tip = `图谱加载失败：${detail || '请检查 Neo4j Bolt 连接配置与账号密码'}`
        messageApi.error(tip)
        setGraphError(tip)
      } finally {
        setLoading(false)
      }
    },
    [bootstrapNeoVis, readStatsFromNetwork, messageApi]
  )

  const loadGlobal = useCallback(async () => {
    const { query, params } = buildGlobalCypher()
    setCenterTag('GlobalGraph/ALL')
    clearEntity()
    await runCypher(query, params)
  }, [buildGlobalCypher, clearEntity, runCypher])

  const loadCenter = useCallback(
    async (labelValue: string, businessKey: string) => {
      const bk = businessKey.trim()
      if (!bk) return
      const { query, params } = buildCenterCypher(labelValue, bk)
      setCenterTag(`${labelValue}/${bk}`)
      clearEntity()
      await runCypher(query, params)
    },
    [buildCenterCypher, runCypher, clearEntity]
  )

  useEffect(() => {
    const boot = async () => {
      const centerData = await graphApi.listCenters(30)
      setCenters(centerData.items ?? [])

      const nodeOptions = new Set<string>()
      ;(centerData.items ?? []).forEach((c) => nodeOptions.add(c.label))
      Object.keys(LABEL_CHINESE).forEach((k) => nodeOptions.add(k))
      setNodeTypeOptions(Array.from(nodeOptions).map((v) => ({ value: v, label: LABEL_CHINESE[v] ?? v })))
      setRelTypeOptions(
        Object.keys(REL_CN).map((v) => ({
          value: v,
          label: REL_CN[v] ?? v,
        }))
      )

      if (routeParams.label && routeParams.businessKey) {
        await loadCenter(routeParams.label, decodeURIComponent(routeParams.businessKey))
      } else {
        await loadGlobal()
      }
    }
    void boot()
  }, [routeParams.label, routeParams.businessKey, loadCenter, loadGlobal])

  useEffect(() => {
    applyLayoutModeToNetwork(layoutMode, layoutSpread)
  }, [layoutMode, layoutSpread, applyLayoutModeToNetwork])

  const handleSearch = async () => {
    if (!keyword.trim()) {
      await loadGlobal()
      return
    }
    await loadCenter(searchLabel, keyword)
  }

  const handleReset = async () => {
    setKeyword('')
    setFilterKeyword('')
    setNodeTypeFilters([])
    setRelTypeFilters([])
    setGlobalRelLimit(300)
    setGlobalExcludeChunks(true)
    setShowNodeLabels(false)
    setShowEdgeLabels(false)
    setLayoutMode('neo4j')
    setLayoutSpread(1.45)
    await loadGlobal()
  }

  const handleCorePreset = async () => {
    setRelTypeFilters(CORE_REL_TYPES)
    setFilterKeyword('')
    setNodeTypeFilters([])
    setGlobalExcludeChunks(true)
    await loadGlobal()
  }

  const zoom = (factor: number) => {
    const network = vizRef.current?.network
    if (!network) return
    const current = network.getScale?.() ?? 1
    network.moveTo({ scale: current * factor })
  }

  const fitView = () => {
    vizRef.current?.network?.fit?.()
  }

  const relayout = () => {
    applyLayoutModeToNetwork(layoutMode, layoutSpread)
    messageApi.success('正在重新计算布局…')
  }

  const entityType = entity?.labels?.[0] ?? label ?? ''
  const entityColor = LABEL_COLORS[entityType] ?? '#64748b'
  const entityEntries = Object.entries(entity?.properties ?? {}).slice(0, 10)

  return (
    <div className={styles.page}>
      {contextHolder}

      <header className={styles.header}>
        <div>
          <Title level={3} className={styles.headerTitle}>
            知识图谱
          </Title>
          <p className={styles.headerSub}>NeoVis.js（vis-network + Bolt）实时渲染</p>
        </div>
      </header>

      <div className={styles.workspace}>
        <Card className={styles.graphCard} variant="borderless">
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
                <Button size="small" type="primary" icon={<SearchOutlined />} onClick={() => void handleSearch()}>
                  查询
                </Button>
              </div>
              <div className={styles.controlGroup}>
                <Select
                  size="small"
                  value={layoutMode}
                  onChange={(v) => setLayoutMode(v as LayoutMode)}
                  options={[
                    { value: 'neo4j', label: 'Neo4j风格(分散)' },
                    { value: 'stable', label: '稳定分散' },
                    { value: 'performance', label: '高性能' },
                  ]}
                  style={{ width: 132 }}
                />
                <Select
                  size="small"
                  value={layoutSpread}
                  onChange={(v) => setLayoutSpread(v)}
                  options={[
                    { value: 1.0, label: '疏密 1.0x' },
                    { value: 1.35, label: '疏密 1.35x' },
                    { value: 1.7, label: '疏密 1.7x' },
                    { value: 2.1, label: '疏密 2.1x' },
                  ]}
                  className={styles.limitSelect}
                />
                <Tooltip title="显示节点标签">
                  <Switch size="small" checked={showNodeLabels} onChange={setShowNodeLabels} checkedChildren="节点名" unCheckedChildren="节点名" />
                </Tooltip>
                <Tooltip title="显示关系标签">
                  <Switch size="small" checked={showEdgeLabels} onChange={setShowEdgeLabels} checkedChildren="关系" unCheckedChildren="关系" />
                </Tooltip>
                <Tooltip title="适应画布">
                  <Button size="small" icon={<ExpandOutlined />} onClick={fitView} />
                </Tooltip>
                <Tooltip title="重新计算力导向布局（不重新查询）">
                  <Button size="small" onClick={relayout}>
                    重布局
                  </Button>
                </Tooltip>
                <Tooltip title="重载">
                  <Button size="small" icon={<ReloadOutlined />} onClick={() => void loadGlobal()} />
                </Tooltip>
                <Tooltip title="清空筛选并重载">
                  <Button size="small" icon={<ClearOutlined />} onClick={() => void handleReset()} />
                </Tooltip>
              </div>
            </div>

            <div className={styles.filterRow}>
              <Select
                size="small"
                mode="multiple"
                allowClear
                maxTagCount="responsive"
                placeholder="节点类型筛选"
                value={nodeTypeFilters}
                onChange={(v) => setNodeTypeFilters(v)}
                options={nodeTypeOptions}
                className={styles.filterSelect}
              />
              <Select
                size="small"
                mode="multiple"
                allowClear
                maxTagCount="responsive"
                placeholder="关系类型筛选"
                value={relTypeFilters}
                onChange={(v) => setRelTypeFilters(v)}
                options={relTypeOptions}
                className={styles.filterSelect}
              />
              <Input
                size="small"
                allowClear
                value={filterKeyword}
                onChange={(e) => setFilterKeyword(e.target.value)}
                placeholder="图内关键词筛选（business_key/title）"
                className={styles.filterKeywordInput}
              />
              <div className={styles.globalFilterGroup}>
                <Select
                  size="small"
                  value={globalRelLimit}
                  onChange={(v) => setGlobalRelLimit(v)}
                  options={[
                    { value: 200, label: '关系200' },
                    { value: 300, label: '关系300' },
                    { value: 600, label: '关系600' },
                    { value: 1000, label: '关系1000' },
                  ]}
                  className={styles.limitSelect}
                />
                <Tooltip title="过滤 Chunk 与提及边">
                  <Switch size="small" checked={globalExcludeChunks} onChange={setGlobalExcludeChunks} checkedChildren="去Chunk" unCheckedChildren="含Chunk" />
                </Tooltip>
                <Button size="small" onClick={() => void loadGlobal()}>
                  重载全图
                </Button>
                <Button size="small" onClick={() => void handleCorePreset()}>
                  仅主干关系
                </Button>
              </div>
            </div>
          </div>

          <div className={styles.canvasWrap}>
            {loading && (
              <div className={styles.loadingMask}>
                <div style={{ color: '#fff' }}>加载图谱中...</div>
              </div>
            )}
            {graphError && !loading && (
              <div className={styles.loadingMask}>
                <div style={{ color: '#fff', maxWidth: 560, textAlign: 'center' }}>{graphError}</div>
              </div>
            )}
            <div id={NEO_VIS_CONTAINER_ID} className={styles.neovisCanvas} />
            <div className={styles.floatingControls}>
              <Tooltip title="放大" placement="left">
                <Button className={styles.floatingBtn} icon={<ZoomInOutlined />} onClick={() => zoom(1.2)} />
              </Tooltip>
              <Tooltip title="缩小" placement="left">
                <Button className={styles.floatingBtn} icon={<ZoomOutOutlined />} onClick={() => zoom(0.85)} />
              </Tooltip>
              <Tooltip title="适应视图" placement="left">
                <Button className={styles.floatingBtn} icon={<ApartmentOutlined />} onClick={fitView} />
              </Tooltip>
            </div>
          </div>

          <div className={styles.statsBar}>
            <span className={styles.statPill}>节点 <strong>{stats.nodes}</strong></span>
            <span className={styles.statPill}>关系 <strong>{stats.relationships}</strong></span>
            <span className={styles.statPill}>中心 <code>{centerTag}</code></span>
            <span className={styles.statPill}>
              Bolt <code>{boltConfig.serverUser}@{boltConfig.serverUrl}</code>
            </span>
          </div>
        </Card>

        <Card className={styles.detailCard} variant="borderless" title={<span><NodeIndexOutlined style={{ marginRight: 8, color: '#14b8a6' }} />节点详情</span>}>
          {entity ? (
            <>
              <div className={styles.entityHeader}>
                <span className={styles.entityBadge} style={{ background: entityColor }} />
                <div>
                  <Tag color={entityColor} style={{ marginBottom: 6 }}>
                    {LABEL_CHINESE[entityType] ?? entityType}
                  </Tag>
                  <p className={styles.entityTitle}>{String(entity.properties?.title ?? entity.business_key ?? '')}</p>
                  <div className={styles.entityKey}>{entity.business_key}</div>
                </div>
              </div>
              <div className={styles.propList}>
                {entityEntries.map(([k, v]) => (
                  <div key={k} className={styles.propItem}>
                    <div className={styles.propKey}>{k}</div>
                    <div className={styles.propVal}>{String(v)}</div>
                  </div>
                ))}
              </div>
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
                  className={styles.reportItem}
                  onClick={() => void loadCenter(c.label, c.business_key)}
                >
                  <div className={styles.reportItemTitle}>{c.title || c.business_key}</div>
                  <div className={styles.reportItemMeta}>{c.business_key} · {c.degree} 条关联</div>
                </button>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}

export default GraphPageNeoVis
