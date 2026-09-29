// ============================================================
// 文件：components/StatCard.tsx
// 用途：统计卡片组件 —— Stats 页面用
// ============================================================

import { Card, Typography } from 'antd'

const { Title, Text } = Typography

interface StatCardProps {
  title: string
  value: string | number
  suffix?: string
  color?: string
}

export default function StatCard({ title, value, suffix, color }: StatCardProps) {
  return (
    <Card style={{ textAlign: 'center' }}>
      <Text type="secondary">{title}</Text>
      <div style={{ marginTop: 8 }}>
        <Title level={3} style={{ margin: 0, color: color || '#1677ff' }}>
          {value}
        </Title>
        {suffix && (
          <Text type="secondary" style={{ fontSize: 14 }}>
            {suffix}
          </Text>
        )}
      </div>
    </Card>
  )
}