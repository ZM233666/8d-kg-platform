/** MainLayout 主布局组件 */

import React, { useState } from 'react'
import {
  Layout,
  Menu,
  Avatar,
  Dropdown,
  Space,
  Typography,
  Badge,
  Drawer,
  Grid,
  Button,
} from 'antd'
import {
  DashboardOutlined,
  UploadOutlined,
  FileTextOutlined,
  ShareAltOutlined,
  SearchOutlined,
  AuditOutlined,
  SettingOutlined,
  LogoutOutlined,
  UserOutlined,
  BellOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from '@ant-design/icons'
import type { MenuProps } from 'antd'

import { useUserStore, useThemeStore, useTaskStore } from '../../store'
import type { User } from '../store'

const { Header, Sider, Content } = Layout
const { Text } = Typography

// =============================================================================
// 菜单配置
// =============================================================================

const menuItems: MenuProps['items'] = [
  {
    key: '/dashboard',
    icon: <DashboardOutlined />,
    label: '仪表盘',
  },
  {
    key: '/upload',
    icon: <UploadOutlined />,
    label: '文档上传',
  },
  {
    key: '/documents',
    icon: <FileTextOutlined />,
    label: '文档列表',
  },
  {
    key: '/extraction',
    icon: <ShareAltOutlined />,
    label: '抽取任务',
  },
  {
    key: '/graph',
    icon: <ShareAltOutlined />,
    label: '知识图谱',
  },
  {
    key: '/query',
    icon: <SearchOutlined />,
    label: '语义检索',
  },
  {
    key: '/audit',
    icon: <AuditOutlined />,
    label: '审核管理',
    roles: ['admin', 'engineer'],
  },
  {
    key: '/settings',
    icon: <SettingOutlined />,
    label: '系统设置',
    roles: ['admin'],
  },
]

const filteredMenuItems = (user: User | null): MenuProps['items'] => {
  if (!user) return menuItems.filter((m) => !('roles' in (m as Record<string, unknown>)))
  return menuItems.filter((m) => {
    if (!('roles' in (m as Record<string, unknown>))) return true
    const item = m as { roles?: string[] }
    return !item.roles || item.roles.includes(user.role)
  })
}

// =============================================================================
// User Menu
// =============================================================================

const userMenuItems: MenuProps['items'] = [
  { key: 'profile', icon: <UserOutlined />, label: '个人信息' },
  { key: 'settings', icon: <SettingOutlined />, label: '系统设置' },
  { type: 'divider' },
  { key: 'logout', icon: <LogoutOutlined />, label: '退出登录' },
]

// =============================================================================
// MainLayout Props
// =============================================================================

export interface MainLayoutProps {
  children: React.ReactNode
  collapsed?: boolean
  onCollapse?: (collapsed: boolean) => void
  activePath?: string
  onMenuSelect?: (path: string) => void
}

// =============================================================================
// MainLayout Component
// =============================================================================

export const MainLayout: React.FC<MainLayoutProps> = ({
  children,
  collapsed: externalCollapsed,
  onCollapse,
  activePath = '/dashboard',
  onMenuSelect,
}) => {
  const [internalCollapsed, setInternalCollapsed] = useState(false)
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false)
  const collapsed = externalCollapsed !== undefined ? externalCollapsed : internalCollapsed

  const { user, logout } = useUserStore()
  const { mode } = useThemeStore()
  const { taskCount } = useTaskStore()
  const screens = Grid.useBreakpoint()

  const isDark = mode === 'dark'
  const isMobile = !screens.lg

  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    if (isMobile) {
      setMobileDrawerOpen(false)
    }
    onMenuSelect?.(key)
  }

  const handleUserMenuClick: MenuProps['onClick'] = ({ key }) => {
    if (key === 'logout') {
      logout()
    }
  }

  const totalPending = taskCount.pending + taskCount.running

  return (
    <Layout style={{ minHeight: '100dvh', width: '100%' }}>
      {/* 侧边栏 */}
      {!isMobile && (
        <Sider
          collapsible
          collapsed={collapsed}
          trigger={null}
          width={220}
          style={{
            background: isDark ? '#141414' : '#001529',
            position: 'fixed',
            height: '100dvh',
            left: 0,
            top: 0,
            bottom: 0,
            zIndex: 100,
            overflow: 'auto',
          }}
        >
        {/* Logo 区域 */}
        <div
          style={{
            height: 64,
            display: 'flex',
            alignItems: 'center',
            justifyContent: collapsed ? 'center' : 'flex-start',
            padding: collapsed ? '0' : '0 16px',
            borderBottom: `1px solid ${isDark ? '#303030' : '#ffffff18'}`,
          }}
        >
          {collapsed ? (
            <span style={{ color: '#fff', fontSize: 20, fontWeight: 'bold' }}>8D</span>
          ) : (
            <Space direction="horizontal" align="center">
              <span style={{ color: '#1677ff', fontSize: 22, fontWeight: 'bold' }}>8D</span>
              <span style={{ color: '#fff', fontSize: 13 }}>KG Platform</span>
            </Space>
          )}
        </div>

        {/* 导航菜单 */}
        <Menu
          theme={isDark ? 'dark' : 'dark'}
          mode="inline"
          selectedKeys={[activePath]}
          items={filteredMenuItems(user)}
          onClick={handleMenuClick}
          style={{ borderRight: 0, marginTop: 8 }}
        />

        {/* 折叠按钮 */}
        <div
          onClick={() => {
            const next = !collapsed
            setInternalCollapsed(next)
            onCollapse?.(next)
          }}
          style={{
            position: 'absolute',
            bottom: 48,
            left: 0,
            right: 0,
            height: 40,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            color: '#fff8',
            borderTop: `1px solid ${isDark ? '#303030' : '#ffffff18'}`,
          }}
        >
          {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
        </div>
        </Sider>
      )}

      {isMobile && (
        <Drawer
          title={null}
          placement="left"
          width={220}
          open={mobileDrawerOpen}
          onClose={() => setMobileDrawerOpen(false)}
          styles={{
            body: { padding: 0, background: isDark ? '#141414' : '#001529' },
            header: { display: 'none' },
          }}
        >
          <div
            style={{
              height: 64,
              display: 'flex',
              alignItems: 'center',
              padding: '0 16px',
              borderBottom: `1px solid ${isDark ? '#303030' : '#ffffff18'}`,
            }}
          >
            <Space direction="horizontal" align="center">
              <span style={{ color: '#1677ff', fontSize: 22, fontWeight: 'bold' }}>8D</span>
              <span style={{ color: '#fff', fontSize: 13 }}>KG Platform</span>
            </Space>
          </div>
          <Menu
            theme="dark"
            mode="inline"
            selectedKeys={[activePath]}
            items={filteredMenuItems(user)}
            onClick={handleMenuClick}
            style={{ borderRight: 0, marginTop: 8 }}
          />
        </Drawer>
      )}

      {/* 右侧主区域 */}
      <Layout
        style={{
          marginLeft: isMobile ? 0 : collapsed ? 80 : 220,
          transition: 'margin-left 0.2s',
          minWidth: 0,
        }}
      >
        {/* 顶部导航栏 */}
        <Header
          style={{
            background: isDark ? '#1f1f1f' : '#fff',
            padding: '0 24px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            boxShadow: `0 1px 4px ${isDark ? '#00000060' : '#00152910'}`,
            position: 'sticky',
            top: 0,
            zIndex: 99,
            borderBottom: `1px solid ${isDark ? '#303030' : '#f0f0f0'}`,
          }}
        >
          {/* 左侧：面包屑 / 页面标题 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {isMobile && (
              <Button
                type="text"
                icon={<MenuUnfoldOutlined />}
                onClick={() => setMobileDrawerOpen(true)}
              />
            )}
            <Text strong style={{ fontSize: 16 }}>
              {menuItems.find((m) => 'key' in m && m.key === activePath)?.label as string || '8D 知识图谱'}
            </Text>
          </div>

          {/* 右侧：通知 + 用户 */}
          <Space size={16}>
            {/* 任务通知徽标 */}
            <Badge count={totalPending} size="small" offset={[-2, 2]}>
              <BellOutlined style={{ fontSize: 18, cursor: 'pointer' }} />
            </Badge>

            {/* 用户下拉菜单 */}
            <Dropdown menu={{ items: userMenuItems, onClick: handleUserMenuClick }} placement="bottomRight">
              <Space style={{ cursor: 'pointer' }}>
                <Avatar size={32} style={{ backgroundColor: '#1677ff' }} icon={<UserOutlined />} />
                <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.2 }}>
                  <Text strong style={{ fontSize: 13 }}>
                    {user?.username || '访客'}
                  </Text>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {user?.role === 'admin' ? '管理员' : user?.role === 'engineer' ? '工程师' : '访客'}
                  </Text>
                </div>
              </Space>
            </Dropdown>
          </Space>
        </Header>

        {/* 内容区 */}
        <Content style={{ padding: isMobile ? 12 : 16, minHeight: 'calc(100dvh - 64px)' }}>
          {children}
        </Content>
      </Layout>
    </Layout>
  )
}

export default MainLayout