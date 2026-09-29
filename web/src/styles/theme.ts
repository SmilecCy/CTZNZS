// ============================================================
// 文件：styles/theme.ts
// 用途：Ant Design 主题配置
//
// 【设计系统】
//   主色：薄荷绿
//   圆角：大圆角（12~16px）
//   阴影：柔和
// ============================================================

import type { ThemeConfig } from 'antd'

// ============================================================
// 设计令牌
// ============================================================
export const tokens = {
  // 主色（薄荷绿）
  primary50: '#F0FDFA',
  primary100: '#CCFBF1',
  primary200: '#A8E6DD',    // 意向图主色
  primary400: '#5DD6C7',    // 按钮
  primary600: '#14B8A6',    // hover
  primary800: '#0F766E',    // 文字强调

  // 中性色
  bgPage: '#F5F6FA',        // 页面背景
  bgCard: '#FFFFFF',        // 卡片
  border: '#E5E7EB',
  borderLight: '#F0F0F0',
  textPrimary: '#1F2937',
  textSecondary: '#6B7280',
  textHint: '#9CA3AF',

  // 语义色
  success: '#10B981',
  warning: '#F59E0B',
  error: '#EF4444',
  info: '#3B82F6',

  // 圆角
  radiusSm: 6,
  radiusMd: 8,
  radiusLg: 12,
  radiusXl: 16,

  // 阴影
  shadowSm: '0 1px 2px rgba(0,0,0,0.04)',
  shadowMd: '0 2px 8px rgba(0,0,0,0.06)',
  shadowLg: '0 4px 16px rgba(0,0,0,0.08)',
  shadowXl: '0 8px 32px rgba(0,0,0,0.12)',

  // 布局
  brandBarHeight: 56,
  navBarHeight: 56,
  headerTotalHeight: 112,
}

// ============================================================
// Ant Design 主题
// ============================================================
export const themeConfig: ThemeConfig = {
  token: {
    colorPrimary: tokens.primary400,
    colorSuccess: tokens.success,
    colorWarning: tokens.warning,
    colorError: tokens.error,
    colorInfo: tokens.info,

    colorBgLayout: tokens.bgPage,
    colorBgContainer: tokens.bgCard,
    colorBorder: tokens.border,
    colorBorderSecondary: tokens.borderLight,

    colorText: tokens.textPrimary,
    colorTextSecondary: tokens.textSecondary,
    colorTextTertiary: tokens.textHint,

    borderRadius: tokens.radiusMd,
    borderRadiusLG: tokens.radiusLg,
    borderRadiusSM: tokens.radiusSm,

    fontSize: 14,
    controlHeight: 40,

    boxShadow: tokens.shadowMd,
    boxShadowSecondary: tokens.shadowSm,
  },
  components: {
    Button: {
      borderRadius: tokens.radiusMd,
      controlHeight: 40,
      primaryShadow: 'none',
    },
    Card: {
      borderRadiusLG: tokens.radiusXl,
      boxShadowTertiary: tokens.shadowMd,
    },
    Input: {
      borderRadius: tokens.radiusMd,
      controlHeight: 40,
    },
    Select: {
      borderRadius: tokens.radiusMd,
      controlHeight: 40,
    },
    Menu: {
      itemBorderRadius: tokens.radiusMd,
      itemSelectedBg: tokens.primary100,
      itemSelectedColor: tokens.primary800,
      itemHoverBg: tokens.primary50,
    },
    Modal: {
      borderRadiusLG: tokens.radiusXl,
    },
    Table: {
      borderRadius: tokens.radiusLg,
      headerBg: tokens.primary50,
    },
    Tag: {
      borderRadiusSM: tokens.radiusSm,
    },
  },
}