// ============================================================
// 文件：api/chapter.ts
// 用途：章节 API 调用
// ============================================================

import client from './client'
import type {
  ChapterMatchRequest,
  ChapterMatchResponse,
  ChapterNode,
} from '../types'

export async function getChapterTree(courseId: number): Promise<ChapterNode[]> {
  const response = await client.get<ChapterNode[]>(
    `/api/user/courses/${courseId}/chapters`,
  )
  return response.data
}

export async function matchChapter(data: ChapterMatchRequest): Promise<ChapterMatchResponse> {
  const response = await client.post<ChapterMatchResponse>(
    '/api/user/chapter/match',
    data,
  )
  return response.data
}