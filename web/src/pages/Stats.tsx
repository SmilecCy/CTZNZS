// ============================================================
// 文件：pages/Stats.tsx
// 用途：学习统计页
//
// 【展示内容】
//   1. 统计总览（总答题数、正确率、错题数、掌握率）
//   2. 正确率趋势（柱状图）
//   3. 知识点掌握度
// ============================================================

import { useEffect, useState } from 'react'
import { Row, Col, Spin, Empty, message } from 'antd'
import StatCard from '../components/StatCard'
import TrendChart from '../components/TrendChart'
import * as statsApi from '../api/stats'
import { extractErrorMessage } from '../api/client'
import { usePracticeSessionStore } from '../stores/practiceSession'
import type {
  StatsKnowledgePointItem,
  StatsOverview,
  StatsTrendItem,
} from '../types'

export default function Stats() {
  const courseId = usePracticeSessionStore((s) => s.courseId)

  const [loading, setLoading] = useState(true)
  const [overview, setOverview] = useState<StatsOverview | null>(null)
  const [trend, setTrend] = useState<StatsTrendItem[]>([])
  const [knowledgePoints, setKnowledgePoints] = useState<StatsKnowledgePointItem[]>([])

  useEffect(() => {
    if (!courseId) return

    const fetchAll = async () => {
      setLoading(true)
      try {
        const [ov, tr, kp] = await Promise.all([
          statsApi.getStatsOverview(courseId).catch(() => null),
          statsApi.getStatsTrend(courseId, 30).catch(() => []),
          statsApi.getStatsKnowledgePoints(courseId).catch(() => []),
        ])
        setOverview(ov)
        setTrend(tr)
        setKnowledgePoints(kp)
      } catch {
        message.error('加载统计失败')
      } finally {
        setLoading(false)
      }
    }
    fetchAll()
  }, [courseId])

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin size="large" tip="加载统计数据..." />
      </div>
    )
  }

  if (!overview) {
    return (
      <div style={{ padding: 24 }}>
        <Empty description="暂无统计数据，请先开始练习" />
      </div>
    )
  }

  return (
    <div style={{ padding: 24 }}>
      <h2 style={{ marginBottom: 24 }}>学习统计</h2>

      {/* 统计总览 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={12} sm={6}>
          <StatCard
            title="总答题数"
            value={overview.total_answers}
          />
        </Col>
        <Col xs={12} sm={6}>
          <StatCard
            title="正确率"
            value={`${(overview.correct_rate * 100).toFixed(1)}%`}
            color={
              overview.correct_rate >= 0.8
                ? '#52c41a'
                : overview.correct_rate >= 0.6
                  ? '#1677ff'
                  : '#ff4d4f'
            }
          />
        </Col>
        <Col xs={12} sm={6}>
          <StatCard
            title="错题数"
            value={overview.total_wrong}
            color="#ff4d4f"
          />
        </Col>
        <Col xs={12} sm={6}>
          <StatCard
            title="掌握率"
            value={`${(overview.mastery_rate * 100).toFixed(1)}%`}
            color="#52c41a"
          />
        </Col>
      </Row>

      {/* 正确率趋势 */}
      <div style={{ marginBottom: 24 }}>
        <TrendChart data={trend} title="近30日正确率趋势" />
      </div>

      {/* 知识点掌握度 */}
      {knowledgePoints.length > 0 && (
        <div>
          <h3 style={{ marginBottom: 16 }}>知识点掌握度</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {knowledgePoints.map((kp) => (
              <div
                key={kp.knowledge_point}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                }}
              >
                <span style={{ width: 120, textAlign: 'right', fontSize: 13, color: '#666' }}>
                  {kp.knowledge_point}
                </span>
                <div
                  style={{
                    flex: 1,
                    height: 24,
                    background: '#f5f5f5',
                    borderRadius: 12,
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      height: '100%',
                      width: `${kp.rate * 100}%`,
                      background:
                        kp.rate >= 0.8
                          ? 'linear-gradient(90deg, #52c41a, #73d13d)'
                          : kp.rate >= 0.6
                            ? 'linear-gradient(90deg, #1677ff, #4096ff)'
                            : 'linear-gradient(90deg, #ff4d4f, #ff7875)',
                      borderRadius: 12,
                      transition: 'width 0.5s ease',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'flex-end',
                      paddingRight: 8,
                    }}
                  >
                    {kp.rate > 0.15 && (
                      <span style={{ fontSize: 11, color: '#fff', fontWeight: 500 }}>
                        {(kp.rate * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>
                </div>
                <span style={{ fontSize: 12, color: '#999', width: 60 }}>
                  {kp.correct}/{kp.total}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}