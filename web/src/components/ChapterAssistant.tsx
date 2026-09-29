// ============================================================
// 文件：components/ChapterAssistant.tsx
// 用途：出题助手 —— 练习页左栏，对话式交互
//
// 【定位】
//   按教材/附属资料在对应章节出题，用户可选择选择题/简答题。
//
// 【交互流程】
//   学生输入章节名称 + 题型 → POST /api/user/chat → 匹配章节 + 出题 → 展示结果
//
// 【布局】
//   上：聊天记录（可滚动）
//   下：输入区（题型快捷选择 + 输入框 + 发送按钮）
// ============================================================

import { useState, useRef, useEffect } from 'react'
import { Input, Button, Spin, Typography } from 'antd'
import { SendOutlined, RobotOutlined, UserOutlined } from '@ant-design/icons'
import * as userApi from '../api/user'
import { usePracticeSessionStore, type ChatMessage } from '../stores/practiceSession'
import { tokens } from '../styles/theme'

const { Text } = Typography

// 题型选项
const QUESTION_TYPES = [
  { key: '选择', label: '选择题' },
  { key: '简答', label: '简答题' },
] as const

// ============================================================
// 组件
// ============================================================
export default function ChapterAssistant() {
  const {
    courseId,
    messages,
    chatLoading,
    setChapter,
    setQuestions,
    setQuota,
    setSourceStats,
    setChatLoading,
    addMessage,
  } = usePracticeSessionStore()

  const [userInput, setUserInput] = useState('')
  const [selectedType, setSelectedType] = useState<string | null>(null)

  const chatEndRef = useRef<HTMLDivElement>(null)

  // 自动滚动到底部
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // 生成消息 ID
  const msgId = () => `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`

  // 添加助手消息
  const addAssistantMsg = (content: string, extra?: Partial<ChatMessage>) => {
    addMessage({
      id: msgId(),
      role: 'assistant',
      content,
      timestamp: Date.now(),
      ...extra,
    })
  }

  const handleSend = async () => {
    const input = userInput.trim()
    if (!input || chatLoading) return
    if (!courseId) {
      addAssistantMsg('请先在顶部导航栏选择一门课程')
      setUserInput('')
      return
    }

    // 拼接完整的出题请求：显式带上题型（优先用户选中的，其次文本中的）
    let message = input
    if (selectedType && !input.includes('选择') && !input.includes('简答')) {
      message = `${input}，${selectedType === '选择' ? '选择题' : '简答题'}`
    }

    // 添加用户消息（展示原来的输入）
    addMessage({
      id: msgId(),
      role: 'user',
      content: input,
      timestamp: Date.now(),
    })
    setUserInput('')
    setChatLoading(true)

    try {
      const result = await userApi.chatRequest({
        course_id: courseId,
        message,
      })

      // 构建助手回复 — 包含配额信息
      let replyContent = result.reply
      if (result.quota) {
        const { choice_used, choice_limit, short_answer_used, short_answer_limit } = result.quota
        replyContent += `\n本章选择题 ${choice_used}/${choice_limit} · 简答题 ${short_answer_used}/${short_answer_limit}`
      }

      // 同步到 store
      if (result.questions && result.questions.length > 0) {
        setQuestions(result.questions)
      }
      if (result.chapter_id) {
        setChapter(result.chapter_id, result.chapter_name, result.chapter_summary)
      }
      if (result.quota) {
        setQuota({
          choiceUsed: result.quota.choice_used,
          choiceLimit: result.quota.choice_limit,
          shortAnswerUsed: result.quota.short_answer_used,
          shortAnswerLimit: result.quota.short_answer_limit,
        })
      }
      if (result.source_stats) {
        setSourceStats({
          fromBank: result.source_stats.from_bank,
          fromLlvm: result.source_stats.from_llm,
        })
      }

      addAssistantMsg(replyContent, {
        chapterMatched: Boolean(result.chapter_id),
        chapterSummary: result.chapter_summary || undefined,
      })
    } catch (err) {
      const errMsg =
        err instanceof Error ? err.message : '网络异常，请检查连接后重试'
      addAssistantMsg(errMsg, { chapterMatched: false })
    } finally {
      setChatLoading(false)
    }
  }

  // ============================================================
  // 渲染
  // ============================================================
  return (
    <div
      style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        background: tokens.bgPage,
      }}
    >
      {/* ===== 标题栏 ===== */}
      <div
        style={{
          padding: '12px 16px',
          borderBottom: `1px solid ${tokens.borderLight}`,
          background: '#FFFFFF',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}
      >
        <span style={{ fontSize: 16 }}>🤖</span>
        <div>
          <div style={{ fontWeight: 600, fontSize: 14, color: tokens.textPrimary }}>
            教学助手
          </div>
          <Text type="secondary" style={{ fontSize: 11 }}>
            按章节·教材·资料智能出题
          </Text>
        </div>
      </div>

      {/* ===== 聊天记录区 ===== */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '16px 12px',
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        }}
      >
        {messages.length === 0 && (
          <div
            style={{
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: tokens.textHint,
              fontSize: 13,
              textAlign: 'center',
              padding: 24,
            }}
          >
            <div>
              <span
                style={{
                  fontSize: 36,
                  color: tokens.primary200,
                  marginBottom: 12,
                  display: 'block',
                }}
              >
                🤖
              </span>
              输入章节名称开始出题
              <div style={{ fontSize: 12, marginTop: 8, color: tokens.textHint }}>
                例如"第一章 商法概述"、"公司法"
              </div>
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            style={{
              display: 'flex',
              flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
              alignItems: 'flex-start',
              gap: 8,
            }}
          >
            {/* 头像 */}
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: '50%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
                background:
                  msg.role === 'user' ? tokens.primary400 : tokens.primary100,
                color: msg.role === 'user' ? '#FFFFFF' : tokens.primary600,
                fontSize: 14,
              }}
            >
              {msg.role === 'user' ? <UserOutlined /> : <RobotOutlined />}
            </div>

            {/* 气泡 */}
            <div
              style={{
                maxWidth: '75%',
                padding: '10px 14px',
                borderRadius:
                  msg.role === 'user'
                    ? '12px 12px 4px 12px'
                    : '12px 12px 12px 4px',
                background:
                  msg.role === 'user' ? tokens.primary400 : '#FFFFFF',
                color:
                  msg.role === 'user' ? '#FFFFFF' : tokens.textPrimary,
                fontSize: 14,
                lineHeight: 1.6,
                wordBreak: 'break-word',
                whiteSpace: 'pre-wrap',
                boxShadow:
                  msg.role === 'assistant' ? tokens.shadowSm : 'none',
              }}
            >
              {msg.content}

              {/* 章节摘要 */}
              {msg.chapterSummary && (
                <div
                  style={{
                    marginTop: 8,
                    padding: '8px 10px',
                    background: tokens.primary50,
                    borderRadius: tokens.radiusSm,
                    fontSize: 12,
                    color: tokens.textSecondary,
                    lineHeight: 1.6,
                  }}
                >
                  <Text
                    type="secondary"
                    style={{
                      fontSize: 11,
                      display: 'block',
                      marginBottom: 4,
                    }}
                  >
                    章节摘要
                  </Text>
                  {msg.chapterSummary}
                </div>
              )}
            </div>
          </div>
        ))}

        {/* 加载指示器 */}
        {chatLoading && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              paddingLeft: 40,
            }}
          >
            <Spin size="small" />
            <Text type="secondary" style={{ fontSize: 13 }}>
              正在出题...
            </Text>
          </div>
        )}

        <div ref={chatEndRef} />
      </div>

      {/* ===== 题型快捷选择 ===== */}
      <div
        style={{
          padding: '6px 16px 0',
          display: 'flex',
          gap: 8,
        }}
      >
        {QUESTION_TYPES.map((qt) => (
          <Button
            key={qt.key}
            size="small"
            type={selectedType === qt.key ? 'primary' : 'default'}
            ghost={selectedType !== qt.key}
            onClick={() =>
              setSelectedType(selectedType === qt.key ? null : qt.key)
            }
            style={{
              borderRadius: 12,
              fontSize: 12,
              padding: '0 12px',
            }}
          >
            {qt.label}
          </Button>
        ))}
        {selectedType && (
          <Text
            type="secondary"
            style={{ fontSize: 11, lineHeight: '24px' }}
          >
            已选：{selectedType === '选择' ? '选择题' : '简答题'}
          </Text>
        )}
      </div>

      {/* ===== 输入区 ===== */}
      <div
        style={{
          padding: '8px 16px 12px',
          borderTop: `1px solid ${tokens.borderLight}`,
          background: '#FFFFFF',
          display: 'flex',
          gap: 8,
          alignItems: 'flex-end',
        }}
      >
        <Input.TextArea
          rows={2}
          value={userInput}
          onChange={(e) => setUserInput(e.target.value)}
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault()
              handleSend()
            }
          }}
          placeholder='输入章节名称，如"第一章 商法概述"...'
          disabled={chatLoading}
          style={{
            flex: 1,
            borderRadius: tokens.radiusMd,
            resize: 'none',
          }}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          disabled={!userInput.trim() || chatLoading}
          onClick={handleSend}
          loading={chatLoading}
          style={{
            borderRadius: tokens.radiusMd,
            minWidth: 44,
            height: 44,
          }}
        />
      </div>
    </div>
  )
}