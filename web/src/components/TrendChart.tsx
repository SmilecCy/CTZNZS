// ============================================================
// 文件：components/TrendChart.tsx
// 用途：趋势图组件 —— Stats 页面用
// ============================================================

import { Card, Empty } from 'antd'
import type { StatsTrendItem } from '../types'

interface TrendChartProps {
  data: StatsTrendItem[]
  title?: string
}

export default function TrendChart({ data, title = '正确率趋势' }: TrendChartProps) {
  if (!data || data.length === 0) {
    return (
      <Card title={title}>
        <Empty description="暂无数据" />
      </Card>
    )
  }

  const maxRate = Math.max(...data.map((d) => d.rate), 1)

  return (
    <Card title={title}>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12, height: 200, paddingTop: 16 }}>
        {data.map((item, i) => {
          const heightPercent = (item.rate / maxRate) * 100

          return (
            <div
              key={i}
              style={{
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 4,
              }}
            >
              <span style={{ fontSize: 11, color: '#1677ff', fontWeight: 500 }}>
                {(item.rate * 100).toFixed(0)}%
              </span>
              <div
                style={{
                  width: '100%',
                  maxWidth: 40,
                  height: `${Math.max(heightPercent, 4)}%`,
                  background: item.rate >= 0.8
                    ? '#52c41a'
                    : item.rate >= 0.6
                      ? '#1677ff'
                      : '#ff4d4f',
                  borderRadius: '4px 4px 0 0',
                  transition: 'height 0.3s',
                  minHeight: 4,
                }}
              />
              <span style={{ fontSize: 10, color: '#999', marginTop: 4 }}>
                {item.date.slice(5)}
              </span>
              <span style={{ fontSize: 10, color: '#999' }}>
                {item.total}题
              </span>
            </div>
          )
        })}
      </div>
    </Card>
  )
}