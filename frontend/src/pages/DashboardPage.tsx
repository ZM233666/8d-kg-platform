/** 仪表盘页（占位） */

import React from 'react'
import { Card, Typography, Space } from 'antd'
import { DashboardOutlined } from '@ant-design/icons'

const { Title, Text } = Typography

export const DashboardPage: React.FC = () => {
  return (
    <div>
      <Card variant="outlined" style={{ borderRadius: 8 }}>
        <Space direction="vertical" style={{ width: '100%' }} align="center">
          <DashboardOutlined style={{ fontSize: 64, color: '#d9d9d9' }} />
          <Title level={4}>仪表盘</Title>
          <Text type="secondary">v0.2 建设中...</Text>
        </Space>
      </Card>
    </div>
  )
}

export default DashboardPage