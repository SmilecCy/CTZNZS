// ============================================================
// 文件：components/QuestionNav.tsx
// 用途：题目显示框 —— 练习页右栏
//
// 【功能】
//   章节信息 · 题量配额 · 进度 · 题目目录（可跳转、可删除）
// ============================================================

import { Modal, Typography, message } from 'antd'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  MinusCircleOutlined,
  DeleteOutlined,
} from '@ant-design/icons'
import { usePracticeSessionStore } from '../stores/practiceSession'
import { deleteQuestion } from '../api/user'
import { tokens } from '../styles/theme'

const { Text } = Typography

export default function QuestionNav() {
  const {
    questions,
    currentIndex,
    answerStatuses,
    chapterName,
    chapterSummary,
    quota,
    setCurrentIndex,
    removeQuestion,
    setQuota,
  } = usePracticeSessionStore()

  const correctCount = Object.values(answerStatuses).filter(
    (s) => s === 'correct',
  ).length
  const wrongCount = Object.values(answerStatuses).filter(
    (s) => s === 'wrong',
  ).length
  const totalAnswered = correctCount + wrongCount

  const handleDelete = (questionId: number) => {
    Modal.confirm({
      title: '确认删除',
      content:
        '删除后，该题的错题记录、作答历史、收藏、笔记将一并删除，且不可恢复。是否确认？',
      okText: '确认删除',
      cancelText: '取消',
      okButtonProps: { danger: true, type: 'primary' },
      onOk: async () => {
        try {
          const res = await deleteQuestion(questionId)
          if (res.success) {
            removeQuestion(questionId)
            // 释放配额
            setQuota({
              ...quota,
              choiceUsed: Math.max(0, quota.choiceUsed - 1),
              shortAnswerUsed: Math.max(0, quota.shortAnswerUsed - 1),
            })
            message.success('题目已删除，配额已释放')
          }
        } catch {
          message.error('删除失败，请重试')
        }
      },
    })
  }

  return (
    <div
      style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        background: '#FFFFFF',
      }}
    >
      {/* ===== 标题 ===== */}
      <div
        style={{
          padding: '12px 16px',
          fontWeight: 600,
          fontSize: 14,
          color: tokens.textPrimary,
          borderBottom: `1px solid ${tokens.borderLight}`,
        }}
      >
        题目显示框
      </div>

      {/* ===== 章节信息 ===== */}
      {chapterName && (
        <div
          style={{
            padding: '12px 16px',
            borderBottom: `1px solid ${tokens.borderLight}`,
          }}
        >
          <Text
            strong
            style={{ fontSize: 14, color: tokens.textPrimary }}
          >
            {chapterName}
          </Text>
          {chapterSummary && (
            <div
              style={{
                fontSize: 12,
                color: tokens.textHint,
                marginTop: 4,
                lineHeight: 1.5,
              }}
            >
              {chapterSummary.length > 80
                ? chapterSummary.slice(0, 80) + '...'
                : chapterSummary}
            </div>
          )}
        </div>
      )}

      {/* ===== 题量配额 ===== */}
      <div
        style={{
          padding: '12px 16px',
          borderBottom: `1px solid ${tokens.borderLight}`,
          display: 'flex',
          flexDirection: 'column',
          gap: 4,
        }}
      >
        <Text style={{ fontSize: 13, color: tokens.textSecondary }}>
          选择题：
          <Text
            style={{
              color:
                quota.choiceUsed >= quota.choiceLimit
                  ? tokens.error
                  : tokens.textSecondary,
            }}
          >
            {quota.choiceUsed}/{quota.choiceLimit}
          </Text>
        </Text>
        <Text style={{ fontSize: 13, color: tokens.textSecondary }}>
          简答题：
          <Text
            style={{
              color:
                quota.shortAnswerUsed >= quota.shortAnswerLimit
                  ? tokens.error
                  : tokens.textSecondary,
            }}
          >
            {quota.shortAnswerUsed}/{quota.shortAnswerLimit}
          </Text>
        </Text>
      </div>

      {/* ===== 进度信息 ===== */}
      <div
        style={{
          padding: '12px 16px',
          borderBottom: `1px solid ${tokens.borderLight}`,
          display: 'flex',
          flexDirection: 'column',
          gap: 4,
        }}
      >
        <Text style={{ fontSize: 13, color: tokens.textSecondary }}>
          当前进度：{totalAnswered}/{questions.length}
        </Text>
        <Text
          style={{ fontSize: 13, color: tokens.success }}
        >
          ✅ 已答对：{correctCount}
        </Text>
        <Text style={{ fontSize: 13, color: tokens.error }}>
          ❌ 已答错：{wrongCount}
        </Text>
      </div>

      {/* ===== 题目目录 ===== */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '12px 8px',
        }}
      >
        {questions.length === 0 ? (
          <div
            style={{
              textAlign: 'center',
              color: tokens.textHint,
              fontSize: 13,
              padding: 24,
            }}
          >
            暂无题目
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {questions.map((q, i) => {
              const status = answerStatuses[q.id]
              const isActive = i === currentIndex

              let icon = (
                <MinusCircleOutlined style={{ color: '#d9d9d9', fontSize: 14 }} />
              )
              if (status === 'correct') {
                icon = (
                  <CheckCircleOutlined
                    style={{ color: tokens.success, fontSize: 14 }}
                  />
                )
              } else if (status === 'wrong') {
                icon = (
                  <CloseCircleOutlined
                    style={{ color: tokens.error, fontSize: 14 }}
                  />
                )
              }

              return (
                <div
                  key={q.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    cursor: 'pointer',
                    padding: '6px 8px',
                    borderRadius: tokens.radiusSm,
                    background: isActive ? tokens.primary100 : '#FAFAFA',
                    border: isActive
                      ? `1px solid ${tokens.primary400}`
                      : `1px solid ${tokens.borderLight}`,
                    transition: 'all 0.15s',
                  }}
                >
                  {/* 点击跳题区域 */}
                  <div
                    onClick={() => setCurrentIndex(i)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      flex: 1,
                      minWidth: 0,
                    }}
                  >
                    {icon}
                    <span
                      style={{
                        fontSize: 12,
                        color: tokens.textPrimary,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {i + 1}.{' '}
                      {q.question.length > 15
                        ? q.question.slice(0, 15) + '...'
                        : q.question}
                    </span>
                  </div>

                  {/* 删除按钮 */}
                  <DeleteOutlined
                    style={{
                      color: tokens.textHint,
                      fontSize: 13,
                      cursor: 'pointer',
                      padding: 2,
                    }}
                    onClick={(e) => {
                      e.stopPropagation()
                      handleDelete(q.id)
                    }}
                  />
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}