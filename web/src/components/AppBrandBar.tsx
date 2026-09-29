// ============================================================
// 文件：components/AppBrandBar.tsx
// 用途：顶部品牌栏（第一级）
//
// 【布局】
//   左：Logo + 系统名 + 副标题
//   右：版本号 + 帮助按钮
//
// 【背景】
//   薄荷绿渐变
// ============================================================

import { Button, Tooltip } from 'antd'
import { QuestionCircleOutlined } from '@ant-design/icons'
import { tokens } from '../styles/theme'

export default function AppBrandBar() {
  return (
    <div
      style={{
        height: tokens.brandBarHeight,
        padding: '0 24px',
        // 薄荷绿渐变
        background: 'linear-gradient(135deg, #A8E6DD 0%, #7EDDD0 50%, #5DD6C7 100%)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        // 底部细分割线
        borderBottom: '1px solid rgba(15, 118, 110, 0.1)',
      }}
    >
      {/* 左侧：Logo + 系统名 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ fontSize: 26, lineHeight: 1 }}>🌿</span>
        <div style={{ lineHeight: 1.2 }}>
          <div
            style={{
              fontSize: 16,
              fontWeight: 600,
              color: '#0F766E',
              letterSpacing: 0.5,
            }}
          >
            双课程学习系统
          </div>
          <div
            style={{
              fontSize: 11,
              color: 'rgba(15, 118, 110, 0.7)',
              marginTop: 2,
            }}
          >
            AI 辅助学习
          </div>
        </div>
      </div>

      {/* 右侧：版本号 + 帮助 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span
          style={{
            fontSize: 12,
            color: 'rgba(15, 118, 110, 0.7)',
            fontFamily: 'monospace',
          }}
        >
          v1.0
        </span>
        <Tooltip title="帮助">
          <Button
            type="text"
            size="small"
            icon={<QuestionCircleOutlined style={{ color: '#0F766E' }} />}
          />
        </Tooltip>
      </div>
    </div>
  )
}