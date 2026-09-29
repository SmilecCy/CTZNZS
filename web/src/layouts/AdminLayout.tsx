// ============================================================
// 文件：layouts/AdminLayout.tsx
// ============================================================

import { Layout, Menu, Dropdown, Avatar, Space, message } from 'antd'
import {
  UserOutlined,
  LogoutOutlined,
  DashboardOutlined,
  BookOutlined,
  DatabaseOutlined,
  TagsOutlined,
  ApartmentOutlined,
  PartitionOutlined,
  FileTextOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useAdminAuthStore } from '../stores/adminAuth'

const { Header, Content, Sider } = Layout

export default function AdminLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const user = useAdminAuthStore((state) => state.user)
  const logout = useAdminAuthStore((state) => state.logout)

  const handleLogout = async () => {
    await logout()
    message.success('已登出')
    navigate('/admin/login')
  }

  const menuItems = [
    {
      key: '/admin/dashboard',
      icon: <DashboardOutlined />,
      label: '首页',
    },
    {
      key: '/admin/courses',
      icon: <BookOutlined />,
      label: '课程管理',
    },
    {
      key: '/admin/chapters',
      icon: <ApartmentOutlined />,
      label: '章节管理',
    },
    {
      key: '/admin/materials',
      icon: <DatabaseOutlined />,
      label: '资料上传',
    },
    {
      key: '/admin/classify',
      icon: <TagsOutlined />,
      label: '资料分类',
    },
    {
      key: '/admin/chunk-classify',
      icon: <PartitionOutlined />,
      label: 'Chunk 分类',
    },
    {
      key: '/admin/question-bank',
      icon: <FileTextOutlined />,
      label: '题库浏览',
    },
    {
      key: '/admin/selftest',
      icon: <CheckCircleOutlined />,
      label: '系统自检',
    },
  ]

  const selectedKey =
    menuItems.find((item) => location.pathname.startsWith(item.key))?.key ||
    '/admin/dashboard'

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        theme="dark"
        width={220}
        style={{ position: 'fixed', left: 0, top: 0, bottom: 0, overflow: 'auto' }}
      >
        <div
          style={{
            height: 64,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
            fontSize: 16,
            fontWeight: 600,
            borderBottom: '1px solid rgba(255,255,255,0.1)',
          }}
        >
          🔧 后台管理
        </div>

        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>

      <Layout style={{ marginLeft: 220 }}>
        <Header
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            background: '#fff',
            padding: '0 24px',
            boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
          }}
        >
          <Dropdown
            menu={{
              items: [
                {
                  key: 'logout',
                  icon: <LogoutOutlined />,
                  label: '登出',
                  onClick: handleLogout,
                },
              ],
            }}
          >
            <Space style={{ cursor: 'pointer' }}>
              <Avatar size="small" icon={<UserOutlined />} />
              <span>{user?.display_name || user?.username || '管理员'}</span>
            </Space>
          </Dropdown>
        </Header>

        <Content
          style={{
            padding: 24,
            background: '#f5f5f5',
            minHeight: 'calc(100vh - 64px)',
          }}
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}