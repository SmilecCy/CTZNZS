// ============================================================
// 文件：api/admin.ts
// 用途：后台 API 调用
// ============================================================

import axios, { AxiosError, AxiosInstance, AxiosResponse } from 'axios'
import type { Course, SuccessResponse } from '../types'

const TOKEN_KEY = 'admin_access_token'

const adminClient: AxiosInstance = axios.create({
  baseURL: '',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

adminClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error),
)

adminClient.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem('admin_user')
      if (window.location.pathname !== '/admin/login') {
        window.location.href = '/admin/login'
      }
    }
    return Promise.reject(error)
  },
)

// ============================================================
// 类型
// ============================================================
export interface ParseTask {
  id: number
  source_file: string
  status: 'pending' | 'running' | 'done' | 'failed'
  progress: number
  stage: string | null
  page_count: number
  chunk_count: number
  ocr_used: boolean
  warnings: string[]
  error: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string | null
}

export interface Material {
  id: number
  source_file: string
  course_id: number | null
  kind: string
  upload_type: 'textbook' | 'supplement' | string
  chapter_classified: boolean
  chunk_count: number
  page_count: number
  ocr_used: boolean
  detected_course_name: string | null
  detected_knowledge_points: Array<{ name: string; confidence?: number }>
  detection_confidence: number | null
  detection_reasoning: string | null
  detection_status: 'pending' | 'suggested' | 'confirmed' | 'rejected'
  uploaded_at: string | null
  parsed_at: string | null
}

// ============================================================
// 首页
// ============================================================
export async function getDashboard() {
  const response = await adminClient.get('/api/admin/dashboard')
  return response.data as {
    course_count: number
    material_count: number
    pending_classification_count: number
    question_count: number
    llm_calls_today: number
  }
}

// ============================================================
// 课程
// ============================================================
export async function listAllCourses(): Promise<Course[]> {
  const response = await adminClient.get<Course[]>('/api/admin/courses')
  return response.data
}

export async function createCourse(data: {
  name: string
  display_name?: string
  description?: string
  question_focus?: string
}): Promise<Course> {
  const response = await adminClient.post<Course>('/api/admin/courses', data)
  return response.data
}

export async function updateCourse(
  courseId: number,
  data: { display_name?: string; description?: string; question_focus?: string },
): Promise<SuccessResponse> {
  const response = await adminClient.patch<SuccessResponse>(
    `/api/admin/courses/${courseId}`,
    data,
  )
  return response.data
}

export async function deleteCourse(courseId: number): Promise<SuccessResponse> {
  const response = await adminClient.delete<SuccessResponse>(`/api/admin/courses/${courseId}`)
  return response.data
}

export async function mergeCourses(data: {
  from_course_id: number
  to_course_id: number
  merged_by?: string
}): Promise<SuccessResponse> {
  const response = await adminClient.post<SuccessResponse>('/api/admin/courses/merge', data)
  return response.data
}

// ============================================================
// 资料上传
// ============================================================
export async function uploadTextbook(file: File, courseKey?: string): Promise<ParseTask> {
  const formData = new FormData()
  formData.append('file', file)

  const params = new URLSearchParams()
  if (courseKey) params.append('course_key', courseKey)

  const url = `/api/admin/textbooks/upload${params.toString() ? `?${params}` : ''}`

  const response = await adminClient.post<ParseTask>(url, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
  return response.data
}

export async function uploadSupplement(file: File, courseKey?: string): Promise<ParseTask> {
  const formData = new FormData()
  formData.append('file', file)

  const params = new URLSearchParams()
  if (courseKey) params.append('course_key', courseKey)

  const url = `/api/admin/supplements/upload${params.toString() ? `?${params}` : ''}`

  const response = await adminClient.post<ParseTask>(url, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
  return response.data
}

export async function uploadMaterial(file: File, courseKey?: string): Promise<ParseTask> {
  const formData = new FormData()
  formData.append('file', file)

  const params = new URLSearchParams()
  if (courseKey) params.append('course_key', courseKey)

  const url = `/api/admin/materials/upload${params.toString() ? `?${params}` : ''}`

  const response = await adminClient.post<ParseTask>(url, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
  return response.data
}

export async function listParseTasks(statusFilter?: string): Promise<{
  tasks: ParseTask[]
  total: number
}> {
  const params: Record<string, unknown> = {}
  if (statusFilter) params.status = statusFilter

  const response = await adminClient.get<{ tasks: ParseTask[]; total: number }>(
    '/api/admin/materials/tasks',
    { params },
  )
  return response.data
}

export async function getParseTask(taskId: number): Promise<ParseTask> {
  const response = await adminClient.get<ParseTask>(`/api/admin/materials/tasks/${taskId}`)
  return response.data
}

export async function retryParseTask(taskId: number): Promise<ParseTask> {
  const response = await adminClient.post<ParseTask>(`/api/admin/materials/tasks/${taskId}/retry`)
  return response.data
}

// ============================================================
// 资料分类
// ============================================================
export async function listMaterials(params: {
  courseId?: number
  detectionStatus?: string
  uploadType?: string
} = {}): Promise<Material[]> {
  const query: Record<string, unknown> = {}
  if (params.courseId) query.course_id = params.courseId
  if (params.detectionStatus) query.detection_status = params.detectionStatus
  if (params.uploadType) query.upload_type = params.uploadType

  const response = await adminClient.get<Material[]>('/api/admin/materials', { params: query })
  return response.data
}

export async function listPendingMaterials(): Promise<Material[]> {
  const response = await adminClient.get<Material[]>('/api/admin/materials/pending')
  return response.data
}

export async function classifyMaterial(
  materialId: number,
  data: { doc_title?: string; sample_text?: string } = {},
): Promise<Material> {
  const response = await adminClient.post<Material>(
    `/api/admin/materials/${materialId}/classify`,
    data,
    { timeout: 120000 },   // LLM 调用可能慢
  )
  return response.data
}

export async function confirmMaterial(
  materialId: number,
  data: { course_id: number; create_knowledge_points?: boolean; confirmed_by?: string },
): Promise<SuccessResponse> {
  const response = await adminClient.post<SuccessResponse>(
    `/api/admin/materials/${materialId}/confirm`,
    data,
  )
  return response.data
}

// ============================================================
// Chunk 分类到章节
// ============================================================
export interface ChunkClassificationItem {
  chunk_id: string
  chapter_id: number | null
  chapter_name: string | null
  confidence: number | null
  reasoning: string | null
  is_confirmed: boolean
  text: string | null
}

/** 查看某资料的 chunk 分类结果 */
export async function getChunkClassification(
  materialId: number,
): Promise<ChunkClassificationItem[]> {
  const response = await adminClient.get<ChunkClassificationItem[]>(
    `/api/admin/materials/${materialId}/chunk-classification`,
  )
  return response.data
}

/** 触发 LLM 将资料 chunk 分类到章节 */
export async function classifyChunksToChapters(
  materialId: number,
): Promise<ChunkClassificationItem[]> {
  const response = await adminClient.post<ChunkClassificationItem[]>(
    `/api/admin/materials/${materialId}/classify-to-chapters`,
    undefined,
    { timeout: 300000 },   // LLM 逐条分类每个 chunk，可能很慢
  )
  return response.data
}

/** 手动修改某个 chunk 的章节归属 */
export async function updateChunkChapter(
  chunkId: string,
  chapterId: number,
): Promise<SuccessResponse> {
  const response = await adminClient.patch<SuccessResponse>(
    `/api/admin/chunks/${chunkId}/chapter`,
    { chapter_id: chapterId },
  )
  return response.data
}

/** 确认某个 chunk 的分类 */
export async function confirmChunk(chunkId: string): Promise<SuccessResponse> {
  const response = await adminClient.post<SuccessResponse>(
    `/api/admin/chunks/${chunkId}/confirm`,
  )
  return response.data
}

// ============================================================
// 按课程查知识点
// ============================================================
export interface KnowledgePoint {
  id: number
  course_id: number
  name: string
  description: string | null
  sort_order: number
}

export async function listCourseKnowledgePoints(
  courseId: number,
): Promise<KnowledgePoint[]> {
  const response = await adminClient.get<KnowledgePoint[]>(
    `/api/admin/courses/${courseId}/knowledge-points`,
  )
  return response.data
}

// ============================================================
// 题库浏览
// ============================================================
export interface QuestionBankItem {
  id: number
  course_id: number
  knowledge_point: string
  question_type: string
  difficulty: string
  source: string
  status: string
  quality_score: number
  usage_count: number
  prompt_version: string | null
  payload: {
    question?: string
    options?: string[]
    correct_index?: number
    reference_answer?: string
    scoring_points?: string[]
    explanation?: string
  }
}

export async function listQuestions(params: {
  courseId: number
  knowledgePoint?: string
  questionType?: string
  difficulty?: string
  status?: string
  limit?: number
}): Promise<QuestionBankItem[]> {
  const query: Record<string, unknown> = { course_id: params.courseId }
  if (params.knowledgePoint) query.knowledge_point = params.knowledgePoint
  if (params.questionType) query.question_type = params.questionType
  if (params.difficulty) query.difficulty = params.difficulty
  if (params.status) query.status = params.status
  if (params.limit) query.limit = params.limit

  const response = await adminClient.get<QuestionBankItem[]>(
    '/api/admin/question-bank',
    { params: query },
  )
  return response.data
}

export interface QuestionBankStats {
  total: number
  deprecated: number
  avg_quality: number
  by_type: Record<string, number>
  by_difficulty: Record<string, number>
  by_source: Record<string, number>
  by_knowledge_point: Record<string, number>
}

export async function getQuestionBankStats(
  courseId: number,
): Promise<QuestionBankStats> {
  const response = await adminClient.get<QuestionBankStats>(
    '/api/admin/question-bank/stats',
    { params: { course_id: courseId } },
  )
  return response.data
}

export async function deprecateQuestion(questionId: number): Promise<SuccessResponse> {
  const response = await adminClient.delete<SuccessResponse>(
    `/api/admin/question-bank/${questionId}`,
  )
  return response.data
}

export async function restoreQuestion(questionId: number): Promise<SuccessResponse> {
  const response = await adminClient.post<SuccessResponse>(
    `/api/admin/question-bank/${questionId}/restore`,
  )
  return response.data
}

// ============================================================
// 系统自检
// ============================================================
export async function getSelfTest(): Promise<{
  mysql: { ok: boolean; version?: string; error?: string }
  redis: { ok: boolean; version?: string; error?: string }
  question_bank: { by_course: Record<string, number> }
  llm_last_7_days: { calls: number; total_tokens: number }
}> {
  const response = await adminClient.get('/api/admin/selftest')
  return response.data
}
// ============================================================
// 删除资料
// ============================================================
export interface DeletePreview {
  material_id: number
  source_file: string
  chunk_count: number
  question_count: number
  running_tasks: number
  can_delete: boolean
  block_reason: string | null
}

export async function getDeletePreview(materialId: number): Promise<DeletePreview> {
  const response = await adminClient.get<DeletePreview>(
    `/api/admin/materials/${materialId}/delete-preview`,
  )
  return response.data
}

export async function deleteMaterial(materialId: number): Promise<SuccessResponse> {
  const response = await adminClient.delete<SuccessResponse>(
    `/api/admin/materials/${materialId}`,
  )
  return response.data
}
// ============================================================
// 课程：启用 / 彻底删除
// ============================================================
export async function restoreCourse(courseId: number): Promise<SuccessResponse> {
  const response = await adminClient.post<SuccessResponse>(
    `/api/admin/courses/${courseId}/restore`,
  )
  return response.data
}

export interface CourseDeletePreview {
  course_id: number
  name: string
  display_name: string
  is_active: boolean
  knowledge_point_count: number
  question_count: number
  wrong_question_count: number
  paper_count: number
  material_count: number
  can_delete: boolean
}

export async function getCourseDeletePreview(
  courseId: number,
): Promise<CourseDeletePreview> {
  const response = await adminClient.get<CourseDeletePreview>(
    `/api/admin/courses/${courseId}/delete-preview`,
  )
  return response.data
}

export async function hardDeleteCourse(courseId: number): Promise<SuccessResponse> {
  const response = await adminClient.delete<SuccessResponse>(
    `/api/admin/courses/${courseId}/hard`,
  )
  return response.data
}
// ============================================================
// 章节管理
// ============================================================
export interface ChapterTreeItem {
  id: number
  course_id: number
  parent_id: number | null
  name: string
  summary: string | null
  sort_order: number
  children: ChapterTreeItem[]
}

export async function listCourseChapters(courseId: number): Promise<ChapterTreeItem[]> {
  const response = await adminClient.get<ChapterTreeItem[]>(
    `/api/admin/courses/${courseId}/chapters`,
  )
  return response.data
}

export async function createChapter(data: {
  course_id: number
  name: string
  parent_id?: number | null
  summary?: string
  sort_order?: number
}): Promise<ChapterTreeItem> {
  const response = await adminClient.post<ChapterTreeItem>('/api/admin/chapters', data)
  return response.data
}

export async function updateChapter(
  chapterId: number,
  data: { name?: string; summary?: string; sort_order?: number },
): Promise<ChapterTreeItem> {
  const response = await adminClient.patch<ChapterTreeItem>(
    `/api/admin/chapters/${chapterId}`,
    data,
  )
  return response.data
}

export async function deleteChapter(chapterId: number): Promise<SuccessResponse> {
  const response = await adminClient.delete<SuccessResponse>(
    `/api/admin/chapters/${chapterId}`,
  )
  return response.data
}
export default adminClient