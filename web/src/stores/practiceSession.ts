// ============================================================
// 文件：stores/practiceSession.ts
// 用途：练习会话状态管理
//
// 【功能】
//   1. 当前选中的课程 ID
//   2. 当前匹配的章节
//   3. 当前题目列表
//   4. 每题作答状态追踪（unanswered / correct / wrong）
//   5. 配额信息
//   6. 教学助手聊天消息
// ============================================================

import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Question } from '../types'

// ============================================================
// 聊天消息类型
// ============================================================
export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: number
  chapterSummary?: string
  chapterMatched?: boolean
}

export type AnswerStatus = 'unanswered' | 'correct' | 'wrong'

export interface QuotaInfo {
  choiceUsed: number
  choiceLimit: number
  shortAnswerUsed: number
  shortAnswerLimit: number
}

interface PracticeSessionState {
  courseId: number | null
  chapterId: number | null
  chapterName: string | null
  chapterSummary: string | null
  questions: Question[]
  currentIndex: number
  answers: Record<number, string>

  // 作答状态：每题的状态
  answerStatuses: Record<number, AnswerStatus>

  // 聊天加载态
  chatLoading: boolean

  // 配额
  quota: QuotaInfo

  // 出题来源统计
  sourceStats: { fromBank: number; fromLlvm: number }

  // 教学助手聊天消息
  messages: ChatMessage[]

  setCourseId: (courseId: number) => void
  setChapter: (chapterId: number | null, chapterName: string | null, chapterSummary?: string | null) => void
  setQuestions: (questions: Question[]) => void
  setCurrentIndex: (index: number) => void
  setChatLoading: (loading: boolean) => void
  setQuota: (quota: QuotaInfo) => void
  setSourceStats: (stats: { fromBank: number; fromLlvm: number }) => void
  recordAnswer: (questionId: number, answer: string, status: AnswerStatus) => void
  removeQuestion: (questionId: number) => void
  addMessage: (msg: ChatMessage) => void
  resetQuestions: () => void
}

const initialQuota: QuotaInfo = {
  choiceUsed: 0,
  choiceLimit: 50,
  shortAnswerUsed: 0,
  shortAnswerLimit: 10,
}

const initialState = {
  courseId: null as number | null,
  chapterId: null as number | null,
  chapterName: null as string | null,
  chapterSummary: null as string | null,
  questions: [] as Question[],
  currentIndex: 0,
  answers: {} as Record<number, string>,
  answerStatuses: {} as Record<number, AnswerStatus>,
  chatLoading: false,
  quota: { ...initialQuota },
  sourceStats: { fromBank: 0, fromLlvm: 0 },
  messages: [] as ChatMessage[],
}

export const usePracticeSessionStore = create<PracticeSessionState>()(
  persist(
    (set) => ({
      ...initialState,

      setCourseId: (courseId) => set({ courseId }),
      setChapter: (chapterId, chapterName, chapterSummary = null) =>
        set({ chapterId, chapterName, chapterSummary }),
      setQuestions: (questions) =>
        set({
          questions,
          currentIndex: 0,
          answers: {},
          answerStatuses: {},
        }),
      setCurrentIndex: (currentIndex) => set({ currentIndex }),
      setChatLoading: (chatLoading) => set({ chatLoading }),
      setQuota: (quota) => set({ quota }),
      setSourceStats: (stats) => set({ sourceStats: stats }),
      recordAnswer: (questionId, answer, status) =>
        set((state) => ({
          answers: { ...state.answers, [questionId]: answer },
          answerStatuses: { ...state.answerStatuses, [questionId]: status },
        })),
      removeQuestion: (questionId) =>
        set((state) => {
          const filtered = state.questions.filter((q) => q.id !== questionId)
          const newAnswers = { ...state.answers }
          delete newAnswers[questionId]
          const newStatuses = { ...state.answerStatuses }
          delete newStatuses[questionId]
          return {
            questions: filtered,
            answers: newAnswers,
            answerStatuses: newStatuses,
            currentIndex: state.currentIndex >= filtered.length
              ? Math.max(0, filtered.length - 1)
              : state.currentIndex,
          }
        }),
      addMessage: (msg) =>
        set((state) => ({
          messages: [...state.messages, msg],
        })),
      resetQuestions: () =>
        set({
          questions: [],
          currentIndex: 0,
          answers: {},
          answerStatuses: {},
          sourceStats: { fromBank: 0, fromLlvm: 0 },
        }),
    }),
    {
      name: 'practice-session',
      partialize: (state) => ({
        messages: state.messages,
        chatLoading: state.chatLoading,
        quota: state.quota,
        sourceStats: state.sourceStats,
        chapterId: state.chapterId,
        chapterName: state.chapterName,
        chapterSummary: state.chapterSummary,
        questions: state.questions,
        currentIndex: state.currentIndex,
        answers: state.answers,
        answerStatuses: state.answerStatuses,
        courseId: state.courseId,
      }),
    }
  )
)