// ============================================================
// 文件：components/AppNavBar.tsx
// 用途：顶部导航栏（第二级）
//
// 【布局】
//   左：课程切换
//   中：导航菜单（练习 / 错题集 / 统计）
//   右：用户菜单
//
// 【背景】
//   白色 + 底部阴影
// ============================================================

import { Select, Dropdown, Avatar, Space, message } from 'antd'
import {
  UserOutlined,
  LogoutOutlined,
  BookOutlined,
  FileTextOutlined,
  BarChartOutlined,
} from '@ant-design/icons'
import { useNavigate, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useAuthStore } from '../stores/auth'
import { usePracticeSessionStore } from '../stores/practiceSession'
import * as userApi from '../api/user'
import { tokens } from '../styles/theme'
import type { Course } from '../types'

// ============================================================
// 导航项
// ============================================================
const NAV_ITEMS = [
  { key: '/practice', label: '练习', icon: <BookOutlined /> },
  { key: '/wrong-book', label: '错题集', icon: <FileTextOutlined /> },
  { key: '/stats', label: '统计', icon: <BarChartOutlined /> },
]

export default function AppNavBar() {
  const navigate = useNavigate()
  const location = useLocation()
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const { courseId, setCourseId } = usePracticeSessionStore()

  const [courses, setCourses] = useState<Course[]>([])

  // 加载课程列表
  useEffect(() => {
    const fetch = async () => {
      try {
        const list = await userApi.listCourses()
        console.log('[AppNavBar] 课程列表加载成功:', list)
        setCourses(list)
        if (list.length > 0 && !courseId) {
          console.log('[AppNavBar] 自动选中第一门课程:', list[0].id)
          setCourseId(list[0].id)
        }
      } catch (err) {
        console.error('[AppNavBar] 加载课程列表失败:', err)
      }
    }
    fetch()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleLogout = async () => {
    await logout()
    message.success('已登出')
    navigate('/login')
  }

  // 当前选中的导航项
  const activeKey =
    NAV_ITEMS.find((item) => location.pathname.startsWith(item.key))?.key || ''

  return (
    <div
      style={{
        height: tokens.navBarHeight,
        padding: '0 24px',
        background: '#FFFFFF',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        boxShadow: tokens.shadowSm,
        borderBottom: `1px solid ${tokens.borderLight}`,
      }}
    >
      {/* ===== 左侧：课程切换 ===== */}
      <Select
        value={courseId}
        onChange={(val) => {
          console.log('[AppNavBar] 切换课程:', val)
          setCourseId(val)
        }}
        style={{ width: 160, fontSize: 15 }}
        options={courses.map((c) => ({
          label: c.display_name || c.name,
          value: c.id,
        }))}
        placeholder="选择课程"
        getPopupContainer={() => document.body}
        notFoundContent={courses.length === 0 ? '暂无课程，请先到后台创建' : undefined}
      />

      {/* ===== 中间：导航菜单 ===== */}
      <nav style={{ display: 'flex', gap: 4, flex: 1, marginLeft: 24 }}>
        {NAV_ITEMS.map((item) => {
          const isActive = activeKey === item.key
          return (
            <div
              key={item.key}
              onClick={() => navigate(item.key)}
              style={{
                padding: '8px 16px',
                borderRadius: tokens.radiusMd,
                cursor: 'pointer',
                fontSize: 14,
                fontWeight: isActive ? 500 : 400,
                color: isActive ? tokens.primary800 : tokens.textSecondary,
                background: isActive ? tokens.primary100 : 'transparent',
                transition: 'all 0.2s',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}
              onMouseEnter={(e) => {
                if (!isActive) {
                  e.currentTarget.style.background = tokens.primary50
                  e.currentTarget.style.color = tokens.primary600
                }
              }}
              onMouseLeave={(e) => {
                if (!isActive) {
                  e.currentTarget.style.background = 'transparent'
                  e.currentTarget.style.color = tokens.textSecondary
                }
              }}
            >
              {item.icon}
              <span>{item.label}</span>
            </div>
          )
        })}
      </nav>

      {/* ===== 右侧：用户菜单 ===== */}
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
        placement="bottomRight"
      >
        <Space style={{ cursor: 'pointer', padding: '4px 8px', borderRadius: tokens.radiusMd }}>
          <Avatar
            size={32}
            style={{ background: tokens.primary400 }}
            icon={<UserOutlined />}
          />
          <span style={{ fontSize: 14, color: tokens.textPrimary }}>
            {user?.display_name || user?.username || '用户'}
          </span>
        </Space>
      </Dropdown>
    </div>
  )
}