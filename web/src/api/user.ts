// ============================================================
// 文件：api/user.ts
// 用途：用户端 API 调用（出题、作答、错题集）
// ============================================================

import client from './client'
import type {
  AnswerRequest,
  AnswerResponse,
  ChatRequest,
  ChatResponse,
  Course,
  KnowledgePoint,
  QuotaResponse,
  QuestionRequest,
  QuestionResponse,
  ResolveRequest,
  SuccessResponse,
  WrongBookStats,
  WrongQuestion,
} from '../types'

// ============================================================
// 课程与知识点
// ============================================================
export async function listCourses(): Promise<Course[]> {
  const response = await client.get<Course[]>('/api/user/courses')
  return response.data
}

export async function listKnowledgePoints(courseId: number): Promise<KnowledgePoint[]> {
  const response = await client.get<KnowledgePoint[]>(
    `/api/user/courses/${courseId}/knowledge-points`,
  )
  return response.data
}

// ============================================================
// 出题
// ============================================================
export async function requestQuestions(data: QuestionRequest): Promise<QuestionResponse> {
  const response = await client.post<QuestionResponse>('/api/user/questions', data)
  return response.data
}

export async function chatRequest(data: ChatRequest): Promise<ChatResponse> {
  const response = await client.post<ChatResponse>('/api/user/chat', data)
  return response.data
}

export async function getQuota(courseId: number, chapterId: number): Promise<QuotaResponse> {
  const response = await client.get<QuotaResponse>('/api/user/questions/quota', {
    params: { course_id: courseId, chapter_id: chapterId },
  })
  return response.data
}

export async function deleteQuestion(questionId: number): Promise<SuccessResponse> {
  const response = await client.delete<SuccessResponse>(`/api/user/questions/${questionId}`)
  return response.data
}

// ============================================================
// 作答与判分
// ============================================================
export async function submitAnswer(data: AnswerRequest): Promise<AnswerResponse> {
  const response = await client.post<AnswerResponse>('/api/user/answers', data)
  return response.data
}

export async function resolveAnswer(data: ResolveRequest): Promise<AnswerResponse> {
  const response = await client.post<AnswerResponse>('/api/user/answers/resolve', data)
  return response.data
}

// ============================================================
// 错题集
// ============================================================
export async function listWrongQuestions(
  courseId: number,
  options: {
    knowledgePoint?: string
    questionType?: string
    masteryStatus?: string
    orderBy?: string
    limit?: number
  } = {},
): Promise<WrongQuestion[]> {
  const params: Record<string, unknown> = { course_id: courseId }
  if (options.knowledgePoint) params.knowledge_point = options.knowledgePoint
  if (options.questionType) params.question_type = options.questionType
  if (options.masteryStatus) params.mastery_status = options.masteryStatus
  if (options.orderBy) params.order_by = options.orderBy
  if (options.limit) params.limit = options.limit

  const response = await client.get<WrongQuestion[]>('/api/user/wrong-questions', { params })
  return response.data
}

export async function getWrongBookStats(courseId: number): Promise<WrongBookStats> {
  const response = await client.get<WrongBookStats>('/api/user/wrong-questions/stats', {
    params: { course_id: courseId },
  })
  return response.data
}

export async function updateMastery(entryId: number, mastered: boolean): Promise<SuccessResponse> {
  const response = await client.patch<SuccessResponse>(
    `/api/user/wrong-questions/${entryId}`,
    { mastered },
  )
  return response.data
}

export async function recordReview(entryId: number, correct: boolean | null): Promise<SuccessResponse> {
  const response = await client.post<SuccessResponse>(
    `/api/user/wrong-questions/${entryId}/review`,
    { correct },
  )
  return response.data
}

export async function deleteWrongQuestion(entryId: number): Promise<SuccessResponse> {
  const response = await client.delete<SuccessResponse>(`/api/user/wrong-questions/${entryId}`)
  return response.data
}