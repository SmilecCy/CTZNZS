// ============================================================
// 文件：components/QuestionCard.tsx
// 用途：题目卡片组件（练习页和错题集共用）
//
// 【新增功能】
//   1. initialAnswer：从父组件传入的已作答状态，用于恢复
//   2. onRedo：单题重做的回调
// ============================================================

import { useEffect, useState } from 'react'
import {
  Card,
  Radio,
  Input,
  Button,
  Alert,
  Tag,
  Space,
  Checkbox,
  Divider,
} from 'antd'
import { RedoOutlined } from '@ant-design/icons'
import type { AnswerResponse, Question } from '../types'

const { TextArea } = Input

// ============================================================
// Props 定义
// ============================================================
interface QuestionCardProps {
  question: Question
  index?: number
  onSubmit: (userAnswer: string) => Promise<AnswerResponse>
  /** 恢复状态：已作答的答案和判分结果 */
  initialAnswer?: {
    user_answer: string
    result: AnswerResponse | null
  }
  /** 单题重做的回调 */
  onRedo?: () => void
  showSubmit?: boolean
}

// ============================================================
// 组件
// ============================================================
export default function QuestionCard({
  question,
  index,
  onSubmit,
  initialAnswer,
  onRedo,
  showSubmit = true,
}: QuestionCardProps) {
  const [userAnswer, setUserAnswer] = useState<string>('')
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<AnswerResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const isChoice = question.question_type === '选择'
  const options = question.options || []
  const points = question.scoring_points || []

  const [hits, setHits] = useState<boolean[]>([])

  // ---------- 从 initialAnswer 恢复状态 ----------
  useEffect(() => {
    if (initialAnswer) {
      setUserAnswer(initialAnswer.user_answer || '')
      setResult(initialAnswer.result || null)
      if (initialAnswer.result?.point_results) {
        setHits(initialAnswer.result.point_results.map((p) => p.hit))
      }
    } else {
      // 没有初始答案 → 重置
      setUserAnswer('')
      setResult(null)
      setHits([])
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialAnswer])

  // ---------- 提交 ----------
  const handleSubmit = async () => {
    if (!userAnswer.trim() && !isChoice) {
      setError('请先写点什么再提交')
      return
    }

    setSubmitting(true)
    setError(null)

    try {
      const res = await onSubmit(userAnswer)
      setResult(res)

      if (!isChoice && res.point_results.length > 0) {
        setHits(res.point_results.map((p) => p.hit))
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '提交失败')
    } finally {
      setSubmitting(false)
    }
  }

  // ---------- 单题重做 ----------
  const handleRedo = () => {
    setUserAnswer('')
    setResult(null)
    setError(null)
    setHits([])
    if (onRedo) onRedo()
  }

  // ---------- 渲染 ----------
  return (
    <Card
      style={{ marginBottom: 16 }}
      title={
        <Space>
          {index !== undefined && <span>第 {index + 1} 题</span>}
          <Tag color="blue">{question.question_type}</Tag>
          <Tag>{question.difficulty}</Tag>
          {question.from && (
            <Tag color={question.from === 'bank' ? 'green' : 'orange'}>
              {question.from === 'bank' ? '题库' : '新生成'}
            </Tag>
          )}
        </Space>
      }
      extra={
        result && onRedo ? (
          <Button
            size="small"
            icon={<RedoOutlined />}
            onClick={handleRedo}
          >
            重做这题
          </Button>
        ) : null
      }
    >
      {/* 题干 */}
      <div style={{ fontSize: 16, lineHeight: 1.8, marginBottom: 16 }}>
        {question.question}
      </div>

      {/* 作答区 */}
      {showSubmit && !result && (
        <div>
          {isChoice ? (
            <Radio.Group
              onChange={(e) => setUserAnswer(String(e.target.value))}
              value={userAnswer}
              style={{ display: 'flex', flexDirection: 'column', gap: 8 }}
            >
              {options.map((opt, i) => (
                <Radio key={i} value={String(i)}>
                  {String.fromCharCode(65 + i)}. {opt}
                </Radio>
              ))}
            </Radio.Group>
          ) : (
            <TextArea
              rows={5}
              value={userAnswer}
              onChange={(e) => setUserAnswer(e.target.value)}
              placeholder="请写下你的作答（提交后会自动判分）"
            />
          )}

          {error && (
            <Alert type="error" message={error} style={{ marginTop: 12 }} showIcon />
          )}

          <Button
            type="primary"
            onClick={handleSubmit}
            loading={submitting}
            style={{ marginTop: 12 }}
            disabled={isChoice && !userAnswer}
          >
            提交作答
          </Button>
        </div>
      )}

      {/* 判分结果 */}
      {result && (
        <div>
          <Divider />

          {result.error ? (
            <Alert
              type="warning"
              showIcon
              message="自动判分不可用"
              description={result.error}
              style={{ marginBottom: 12 }}
            />
          ) : result.is_correct === true ? (
            <Alert
              type="success"
              showIcon
              message={`回答正确${result.score !== null ? `（得分 ${(result.score * 100).toFixed(0)}%）` : ''}`}
              style={{ marginBottom: 12 }}
            />
          ) : result.is_correct === false ? (
            <Alert
              type="error"
              showIcon
              message={`回答错误${result.score !== null ? `（得分 ${(result.score * 100).toFixed(0)}%）` : ''}`}
              description={result.wrong_recorded ? '已自动收录到错题集' : undefined}
              style={{ marginBottom: 12 }}
            />
          ) : (
            <Alert type="info" showIcon message="未判定" style={{ marginBottom: 12 }} />
          )}

          {result.comment && (
            <Alert
              type="info"
              message="批改意见"
              description={result.comment}
              style={{ marginBottom: 12 }}
            />
          )}

          {!isChoice && result.reference_answer && (
            <div style={{ marginBottom: 12 }}>
              <strong>参考答案：</strong>
              <div style={{ marginTop: 4, padding: 12, background: '#fafafa', borderRadius: 4 }}>
                {result.reference_answer}
              </div>
            </div>
          )}

          {isChoice && question.correct_index !== undefined && (
            <div style={{ marginBottom: 12 }}>
              <strong>正确答案：</strong>
              {String.fromCharCode(65 + question.correct_index)}.{' '}
              {options[question.correct_index]}
            </div>
          )}

          {!isChoice && points.length > 0 && result.point_results.length > 0 && (
            <div>
              <strong>逐要点核对（可手动调整）：</strong>
              <div style={{ marginTop: 8 }}>
                {result.point_results.map((p, i) => (
                  <div key={i} style={{ marginBottom: 8 }}>
                    <Checkbox
                      checked={hits[i] ?? p.hit}
                      onChange={(e) => {
                        const next = [...hits]
                        next[i] = e.target.checked
                        setHits(next)
                      }}
                    >
                      {p.point}
                    </Checkbox>
                    {p.reason && (
                      <div style={{ fontSize: 12, color: '#888', marginLeft: 24 }}>
                        {p.reason}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {question.explanation && (
            <div style={{ marginTop: 12, fontSize: 13, color: '#666' }}>
              <strong>解析：</strong>
              {question.explanation}
            </div>
          )}
        </div>
      )}
    </Card>
  )
}