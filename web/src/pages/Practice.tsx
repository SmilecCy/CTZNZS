// ============================================================
// 文件：pages/Practice.tsx
// 用途：练习页 —— 三栏布局
//
// 【布局】
//   左栏（25%）：ChapterAssistant —— 章节匹配 + 出题
//   中栏（50%）：AnswerSheet —— 答题卡
//   右栏（25%）：QuestionNav —— 题目目录
//
// 【数据流】
//   ChapterAssistant 匹配章节 → 点选出题类型 ↓
//   → 调后端出题接口 → 存入 practiceSession store ↓
//   → AnswerSheet 读取题目 → 渲染 → 作答 → 判分
//   → QuestionNav 读取题目列表 → 显示进度 → 点击跳转
// ============================================================

import { useEffect, useRef } from 'react'
import ChapterAssistant from '../components/ChapterAssistant'
import AnswerSheet from '../components/AnswerSheet'
import QuestionNav from '../components/QuestionNav'
import { usePracticeSessionStore } from '../stores/practiceSession'

export default function Practice() {
  const {
    courseId,
    resetQuestions,
    setChapter,
  } = usePracticeSessionStore()

  const prevCourseRef = useRef<number | null>(courseId)

  useEffect(() => {
    const prev = prevCourseRef.current
    prevCourseRef.current = courseId
    // 仅在用户主动切换到不同课程时才重置（跳过组件挂载时的首次执行）
    if (prev !== null && prev !== courseId) {
      resetQuestions()
      setChapter(null, null, null)
    }
  }, [courseId]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div style={{ height: 'calc(100vh - 120px)' }}>
      {/* 三栏布局 */}
      <div style={{ display: 'flex', height: '100%' }}>
        {/* 左栏：教学助手 - 25% */}
        <div
          style={{
            width: '25%',
            minWidth: 280,
            borderRight: '1px solid #f0f0f0',
            overflow: 'hidden',
          }}
        >
          <ChapterAssistant />
        </div>

        {/* 中栏：出题框 - 50% */}
        <div style={{ flex: 1, overflow: 'auto', padding: 24 }}>
          <AnswerSheet />
        </div>

        {/* 右栏：题目显示框 - 25% */}
        <div
          style={{
            width: '25%',
            minWidth: 280,
            borderLeft: '1px solid #f0f0f0',
            overflow: 'hidden',
          }}
        >
          <QuestionNav />
        </div>
      </div>
    </div>
  )
}