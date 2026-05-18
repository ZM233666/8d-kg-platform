/** 页面级加载：Spin tip 需嵌套子节点（antd v5 约定） */

import React from 'react'
import { Spin } from 'antd'

interface PageSpinProps {
  tip?: string
  size?: 'small' | 'default' | 'large'
  minHeight?: number
  fullPage?: boolean
}

export const PageSpin: React.FC<PageSpinProps> = ({
  tip = '加载中...',
  size = 'large',
  minHeight = 120,
  fullPage = true,
}) => (
  <div
    style={
      fullPage
        ? { display: 'flex', justifyContent: 'center', alignItems: 'center', height: '60vh' }
        : { textAlign: 'center', padding: '24px 0' }
    }
  >
    <Spin tip={tip} size={size}>
      <div style={{ minHeight, minWidth: 120 }} />
    </Spin>
  </div>
)
