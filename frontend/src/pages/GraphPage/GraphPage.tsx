/**
 * 图谱页入口：按 VITE_GRAPH_RENDERER 选择 NeoVis 或 G6 实现。
 *
 * 默认 neovis；回滚到 G6 时在仓库根 .env 设置：
 *   VITE_GRAPH_RENDERER=g6
 * 然后重启 `make frontend`。
 */

import React from 'react'
import { Tag } from 'antd'

import { graphRenderer, graphRendererLabel, isG6Renderer } from '../../config/graphRenderer'
import { GraphPageG6 } from './GraphPageG6'
import { GraphPageNeoVis } from './GraphPageNeoVis'
import styles from './GraphPage.module.css'

const Impl = isG6Renderer ? GraphPageG6 : GraphPageNeoVis

export const GraphPage: React.FC = () => (
  <>
    {import.meta.env.DEV && (
      <div className={styles.rendererBanner}>
        <Tag color={isG6Renderer ? 'orange' : 'cyan'}>{graphRendererLabel[graphRenderer]}</Tag>
        <span className={styles.rendererHint}>
          切换渲染器：修改 <code>VITE_GRAPH_RENDERER</code>（neovis | g6）后重启前端
        </span>
      </div>
    )}
    <Impl />
  </>
)

export default GraphPage
