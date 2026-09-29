// ============================================================
// 文件：layouts/UserLayout.tsx
// 用途：用户端布局
//
// 【结构】
//   AppHeader（品牌栏 + 导航栏，112px）
//   Content（内容区，calc(100vh - 112px)）
//
// 【为什么内容区不滚动，让页面自己滚动】
//   练习页是三栏固定布局，左右两栏自己不滚动，只有中栏滚动。
//   如果外层容器也滚动，会出现双滚动条。
// ============================================================

import { Layout } from 'antd'
import { Outlet } from 'react-router-dom'
import AppHeader from '../components/AppHeader'
import { tokens } from '../styles/theme'

const { Content } = Layout

export default function UserLayout() {
  return (
    <Layout style={{ minHeight: '100vh', background: tokens.bgPage }}>
      {/* 顶部头部 */}
      <AppHeader />

      {/* 内容区 */}
      <Content
        style={{
          height: `calc(100vh - ${tokens.headerTotalHeight}px)`,
          overflow: 'hidden',   // 让页面内容自己管理滚动
        }}
      >
        <Outlet />
      </Content>
    </Layout>
  )
}