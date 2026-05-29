/** 图谱渲染器选择：neovis（默认）| g6（回滚） */

export type GraphRenderer = 'neovis' | 'g6'

const VALID: GraphRenderer[] = ['neovis', 'g6']

function parseRenderer(raw: string | undefined): GraphRenderer {
  const value = (raw ?? 'neovis').trim().toLowerCase()
  if (VALID.includes(value as GraphRenderer)) {
    return value as GraphRenderer
  }
  console.warn(`[graph] unknown VITE_GRAPH_RENDERER="${raw}", fallback to neovis`)
  return 'neovis'
}

/** 当前生效的渲染器（构建时由 VITE_GRAPH_RENDERER 决定） */
export const graphRenderer: GraphRenderer = parseRenderer(import.meta.env.VITE_GRAPH_RENDERER)

/** 回滚到 G6：在 .env 中设置 VITE_GRAPH_RENDERER=g6 后重启前端 */
export const isG6Renderer = graphRenderer === 'g6'

export const graphRendererLabel: Record<GraphRenderer, string> = {
  neovis: 'NeoVis.js（Bolt 直连）',
  g6: 'AntV G6（REST API）',
}
