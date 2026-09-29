// ============================================================
// 文件：types/index.ts
// 用途：TypeScript 类型定义
// ============================================================

// ---------- 用户与认证 ----------
export interface User {
  id: number
  username: string
  role: 'user' | 'admin'
  display_name: string
}

export interface LoginRequest {
  username: string
  password: string
  role?: 'user' | 'admin'
}

export interface RegisterRequest {
  username: string
  password: string
  display_name?: string
  email?: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
  user: User
}

// ---------- 课程与知识点 ----------
export interface Course {
  id: number
  name: string
  display_name: string
  description?: string
  question_focus?: string
   is_active?: number
}

export interface KnowledgePoint {
  id: number
  course_id: number
  name: string
  description?: string
  sort_order: number
}

// ---------- 出题 ----------
export type QuestionType = '简答' | '选择'
export type Difficulty = '易' | '中' | '难'

export interface QuestionRequest {
  course_id: number
  knowledge_point: string
  question_type: QuestionType
  difficulty: Difficulty
  count: number
  knowledge_point_id?: number
}

export interface Question {
  id: number
  question: string
  question_type: QuestionType
  difficulty: Difficulty
  knowledge_tags?: string[]
  source_ref?: string
  from?: 'bank' | 'llm' | 'search'
  // 简答题字段
  reference_answer?: string
  scoring_points?: string[]
  // 选择题字段
  options?: string[]
  correct_index?: number
  explanation?: string
}

export interface QuestionResponse {
  questions: Question[]
  source_summary: {
    from_bank: number
    from_llm: number
    from_search?: number
  }
  warnings: string[]
}

// ---------- 作答与判分 ----------
export interface AnswerRequest {
  question_id: number
  user_answer: string
  course_id: number
  knowledge_point?: string
}

export interface PointJudgement {
  point: string
  hit: boolean
  reason: string
}

export interface AnswerResponse {
  is_correct: boolean | null
  score: number | null
  reference_answer: string
  comment: string
  point_results: PointJudgement[]
  wrong_recorded: boolean
  error?: string | null
}

export interface ResolveRequest {
  question_id: number
  hits: boolean[]
}

// ---------- 错题集 ----------
export interface WrongQuestion {
  id: number
  question_bank_id: number | null
  knowledge_point: string | null
  question_type: string | null
  mastery_status: 'unmastered' | 'mastered'
  mastery_label: string
  wrong_count: number
  review_count: number
  correct_count: number
  last_result: string | null
  error_tags: string[]
  payload: Question
}

export interface WrongBookStats {
  total: number
  unmastered: number
  mastered: number
  never_reviewed: number
  by_knowledge_point: Record<string, number>
}

// ---------- 章节 ----------
export interface ChapterNode {
  id: number
  course_id: number
  parent_id: number | null
  node_type: 'chapter' | 'knowledge'
  name: string
  description?: string
  summary?: string
  sort_order: number
  children?: ChapterNode[]
}

export interface ChapterMatchRequest {
  course_id: number
  input_text: string
}

export interface ChapterMatchResponse {
  matched: boolean
  chapter: ChapterNode | null
  reply: string
}

// ---------- 对话式出题 ----------
export interface ChatRequest {
  course_id: number
  session_id?: string
  message: string
}

export interface ChatResponse {
  reply: string
  chapter_id: number | null
  chapter_name: string | null
  chapter_summary: string | null
  questions: Question[]
  source_stats: {
    from_bank: number
    from_llm: number
  }
  quota: {
    choice_used: number
    choice_limit: number
    short_answer_used: number
    short_answer_limit: number
  }
}

export interface QuotaResponse {
  choice_used: number
  choice_limit: number
  short_answer_used: number
  short_answer_limit: number
}

// ---------- 收藏 ----------
export interface FavoriteItem {
  id: number
  user_id: number
  question_id: number
  payload: Question
  created_at: string
}

// ---------- 笔记 ----------
export interface NoteItem {
  id: number
  user_id: number
  question_id: number
  content: string
  updated_at: string
}

// ---------- 学习统计 ----------
export interface StatsOverview {
  total_answers: number
  correct_count: number
  correct_rate: number
  total_wrong: number
  mastered_count: number
  mastery_rate: number
  streak_days: number
}

export interface StatsTrendItem {
  date: string
  total: number
  correct: number
  rate: number
}

export interface StatsKnowledgePointItem {
  knowledge_point: string
  total: number
  correct: number
  rate: number
}

// ---------- 通用响应 ----------
export interface SuccessResponse {
  success: boolean
  message: string
  data?: Record<string, unknown>
}