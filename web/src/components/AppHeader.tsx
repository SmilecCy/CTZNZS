// ============================================================
// 文件：components/AppHeader.tsx
// 用途：顶部头部（品牌栏 + 导航栏的组合）
//
// 【为什么要组合】
//   品牌栏 + 导航栏是两个独立组件，但总高度是固定的 112px。
//   组合在一起，调用方只需要 <AppHeader />。
// ============================================================

import AppBrandBar from './AppBrandBar'
import AppNavBar from './AppNavBar'

export default function AppHeader() {
  return (
    <>
      <AppBrandBar />
      <AppNavBar />
    </>
  )
}