// ============================================================
// 文件：components/AnswerSheet.tsx
// 用途：答题卡 —— 练习页中栏
//
// 【功能】
//   展示当前题目，收集作答，调用判分
// ============================================================

import { useState, useEffect } from 'react'
import { Button, Space, Typography } from 'antd'
import {
  LeftOutlined,
  RightOutlined,
  CheckOutlined,
  FileTextOutlined,
} from '@ant-design/icons'
import QuestionCard from './QuestionCard'
import { usePracticeSessionStore } from '../stores/practiceSession'
import * as userApi from '../api/user'
import { tokens } from '../styles/theme'
import type { AnswerResponse } from '../types'

const { Title, Text } = Typography

export default function AnswerSheet() {
  const {
    questions,
    currentIndex,
    courseId,
    chapterName,
    answers,
    answerStatuses,
    setCurrentIndex,
    recordAnswer,
    resetQuestions,
  } = usePracticeSessionStore()

  const currentQuestion = questions[currentIndex]
  const [completed, setCompleted] = useState(false)

  // 当题目列表变化时（重新出题），重置完成状态
  useEffect(() => {
    setCompleted(false)
  }, [questions])

  if (!currentQuestion) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          flexDirection: 'column',
          gap: 12,
          color: tokens.textHint,
        }}
      >
        <FileTextOutlined
          style={{ fontSize: 48, color: tokens.primary200 }}
        />
        <span style={{ fontSize: 14 }}>
          请先在左侧章节助手中选择章节并出题
        </span>
      </div>
    )
  }

  const handleSubmit = async (userAnswer: string): Promise<AnswerResponse> => {
    if (!courseId) throw new Error('未选择课程')

    const result = await userApi.submitAnswer({
      question_id: currentQuestion.id,
      user_answer: userAnswer,
      course_id: courseId,
      knowledge_point: chapterName || undefined,
    })

    recordAnswer(
      currentQuestion.id,
      userAnswer,
      result.is_correct ? 'correct' : 'wrong',
    )

    return result
  }

  const goPrev = () => {
    if (currentIndex > 0) setCurrentIndex(currentIndex - 1)
  }

  const goNext = () => {
    if (currentIndex < questions.length - 1) {
      setCurrentIndex(currentIndex + 1)
    } else {
      setCompleted(true)
    }
  }

  const correctCount = Object.values(answerStatuses).filter(
    (s) => s === 'correct',
  ).length
  const wrongCount = Object.values(answerStatuses).filter(
    (s) => s === 'wrong',
  ).length

  if (completed) {
    return (
      <div style={{ padding: 32, textAlign: 'center' }}>
        <Title level={3} style={{ marginBottom: 16 }}>
          练习完成！
        </Title>
        <div
          style={{
            display: 'flex',
            justifyContent: 'center',
            gap: 32,
            marginBottom: 24,
          }}
        >
          <div>
            <div style={{ fontSize: 28, fontWeight: 700, color: tokens.success }}>
              {correctCount}
            </div>
            <Text type="secondary">已答对</Text>
          </div>
          <div>
            <div style={{ fontSize: 28, fontWeight: 700, color: tokens.error }}>
              {wrongCount}
            </div>
            <Text type="secondary">已答错</Text>
          </div>
          <div>
            <div style={{ fontSize: 28, fontWeight: 700 }}>
              {questions.length - correctCount - wrongCount}
            </div>
            <Text type="secondary">未作答</Text>
          </div>
        </div>
        <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
          正确率：
          {questions.length > 0
            ? ((correctCount / questions.length) * 100).toFixed(0)
            : 0}
          %
        </Text>
        <Space>
          <Button onClick={resetQuestions}>重新开始</Button>
        </Space>
      </div>
    )
  }

  // 构建之前作答的状态（用于回看已答题目）
  const prevAnswer = answers[currentQuestion.id]
  const prevResult =
    prevAnswer !== undefined && answerStatuses[currentQuestion.id]
      ? ({
          is_correct: answerStatuses[currentQuestion.id] === 'correct',
          score: answerStatuses[currentQuestion.id] === 'correct' ? 1 : 0,
          reference_answer: '',
          comment: '',
          point_results: [],
          wrong_recorded: false,
        } as AnswerResponse)
      : null

  return (
    <div>
      {/* 章节标题 */}
      {chapterName && (
        <div
          style={{
            marginBottom: 16,
            padding: '8px 12px',
            background: tokens.primary50,
            borderRadius: tokens.radiusSm,
          }}
        >
          <Text
            strong
            style={{ color: tokens.primary600, fontSize: 14 }}
          >
            {chapterName}
          </Text>
        </div>
      )}

      <QuestionCard
        question={currentQuestion}
        index={currentIndex}
        onSubmit={handleSubmit}
        initialAnswer={
          prevAnswer !== undefined && prevResult
            ? {
                user_answer: prevAnswer,
                result: prevResult,
              }
            : undefined
        }
      />

      <Space
        style={{
          marginTop: 16,
          width: '100%',
          justifyContent: 'center',
        }}
      >
        <Button
          icon={<LeftOutlined />}
          onClick={goPrev}
          disabled={currentIndex === 0}
        >
          上一题
        </Button>
        <span style={{ minWidth: 60, textAlign: 'center' }}>
          {currentIndex + 1} / {questions.length}
        </span>
        <Button
          icon={
            currentIndex < questions.length - 1 ? (
              <RightOutlined />
            ) : (
              <CheckOutlined />
            )
          }
          onClick={goNext}
          type={
            currentIndex === questions.length - 1 ? 'primary' : 'default'
          }
        >
          {currentIndex < questions.length - 1 ? '下一题' : '完成'}
        </Button>
      </Space>
    </div>
  )
}