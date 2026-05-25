/** 仪表盘页（占位） */

import React from 'react'
import { Card, Typography, Space } from 'antd'
import { DashboardOutlined } from '@ant-design/icons'
import styles from './DashboardPage.module.css'

const { Title, Text } = Typography

export const DashboardPage: React.FC = () => {
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <Title level={3} className={styles.title}>
            仪表盘
          </Title>
          <p className={styles.subtitle}>平台概览与关键指标（建设中）</p>
        </div>
      </header>
      <Card variant="outlined" className={styles.card}>
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