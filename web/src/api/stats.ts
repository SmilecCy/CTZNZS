// ============================================================
// 文件：api/stats.ts
// 用途：学习统计 API 调用
// ============================================================

import client from './client'
import type {
  StatsKnowledgePointItem,
  StatsOverview,
  StatsTrendItem,
} from '../types'

export async function getStatsOverview(courseId: number): Promise<StatsOverview> {
  const response = await client.get<StatsOverview>('/api/user/stats/overview', {
    params: { course_id: courseId },
  })
  return response.data
}

export async function getStatsTrend(courseId: number, days?: number): Promise<StatsTrendItem[]> {
  const response = await client.get<StatsTrendItem[]>('/api/user/stats/trend', {
    params: { course_id: courseId, ...(days ? { days } : {}) },
  })
  return response.data
}

export async function getStatsKnowledgePoints(courseId: number): Promise<StatsKnowledgePointItem[]> {
  const response = await client.get<StatsKnowledgePointItem[]>(
    '/api/user/stats/knowledge-points',
    { params: { course_id: courseId } },
  )
  return response.data
}