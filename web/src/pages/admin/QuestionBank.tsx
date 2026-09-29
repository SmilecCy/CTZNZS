// ============================================================
// 文件：pages/admin/QuestionBank.tsx
// 用途：题库浏览
// ============================================================

import { useEffect, useState } from 'react'
import {
  Card,
  Table,
  Select,
  Space,
  Tag,
  message,
  Popconfirm,
  Button,
  Row,
  Col,
  Statistic,
  Alert,
  Modal,
  Descriptions,
} from 'antd'
import { ReloadOutlined, DeleteOutlined, UndoOutlined } from '@ant-design/icons'
import * as adminApi from '../../api/admin'
import type { QuestionBankItem, QuestionBankStats } from '../../api/admin'
import { extractErrorMessage } from '../../api/client'
import type { Course } from '../../types'

export default function QuestionBank() {
  const [courses, setCourses] = useState<Course[]>([])
  const [selectedCourse, setSelectedCourse] = useState<number | null>(null)

  const [questions, setQuestions] = useState<QuestionBankItem[]>([])
  const [stats, setStats] = useState<QuestionBankStats | null>(null)
  const [loading, setLoading] = useState(false)

  // 筛选
  const [filterType, setFilterType] = useState<string>('')
  const [filterDifficulty, setFilterDifficulty] = useState<string>('')
  const [filterStatus, setFilterStatus] = useState<string>('active')

  // 详情弹窗
  const [detailOpen, setDetailOpen] = useState(false)
  const [currentQuestion, setCurrentQuestion] = useState<QuestionBankItem | null>(null)

  // ---------- 加载课程 ----------
  useEffect(() => {
    const fetch = async () => {
      try {
        const list = await adminApi.listAllCourses()
        const active = list.filter((c) => (c as any).is_active !== 0)
        setCourses(active)
        if (active.length > 0 && !selectedCourse) {
          setSelectedCourse(active[0].id)
        }
      } catch (err) {
        message.error(extractErrorMessage(err))
      }
    }
    fetch()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ---------- 加载题目和统计 ----------
  useEffect(() => {
    if (!selectedCourse) return

    const fetch = async () => {
      setLoading(true)
      try {
        const [list, s] = await Promise.all([
          adminApi.listQuestions({
            courseId: selectedCourse,
            questionType: filterType || undefined,
            difficulty: filterDifficulty || undefined,
            status: filterStatus || undefined,
            limit: 200,
          }),
          adminApi.getQuestionBankStats(selectedCourse),
        ])
        setQuestions(list)
        setStats(s)
      } catch (err) {
        message.error(extractErrorMessage(err))
      } finally {
        setLoading(false)
      }
    }
    fetch()
  }, [selectedCourse, filterType, filterDifficulty, filterStatus])

  const refresh = async () => {
    if (!selectedCourse) return
    setLoading(true)
    try {
      const [list, s] = await Promise.all([
        adminApi.listQuestions({
          courseId: selectedCourse,
          questionType: filterType || undefined,
          difficulty: filterDifficulty || undefined,
          status: filterStatus || undefined,
          limit: 200,
        }),
        adminApi.getQuestionBankStats(selectedCourse),
      ])
      setQuestions(list)
      setStats(s)
    } catch (err) {
      message.error(extractErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  // ---------- 废弃/恢复 ----------
  const handleDeprecate = async (qid: number) => {
    try {
      await adminApi.deprecateQuestion(qid)
      message.success('已废弃')
      await refresh()
    } catch (err) {
      message.error(extractErrorMessage(err))
    }
  }

  const handleRestore = async (qid: number) => {
    try {
      await adminApi.restoreQuestion(qid)
      message.success('已恢复')
      await refresh()
    } catch (err) {
      message.error(extractErrorMessage(err))
    }
  }

  // ---------- 表格列 ----------
  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      width: 60,
    },
    {
      title: '题干',
      dataIndex: ['payload', 'question'],
      key: 'question',
      ellipsis: true,
      render: (text: string, row: QuestionBankItem) => (
        <a
          onClick={() => {
            setCurrentQuestion(row)
            setDetailOpen(true)
          }}
          title={text}
        >
          {text?.slice(0, 60) || '（无题干）'}
        </a>
      ),
    },
    {
      title: '知识点',
      dataIndex: 'knowledge_point',
      width: 140,
      render: (v: string) => <Tag>{v}</Tag>,
    },
    {
      title: '题型',
      dataIndex: 'question_type',
      width: 80,
      render: (v: string) => <Tag color="blue">{v}</Tag>,
    },
    {
      title: '难度',
      dataIndex: 'difficulty',
      width: 70,
    },
    {
      title: '质量分',
      dataIndex: 'quality_score',
      width: 90,
      render: (v: number) => {
        const color = v > 0 ? 'green' : v < 0 ? 'red' : 'default'
        return <Tag color={color}>{v > 0 ? '+' : ''}{v}</Tag>
      },
    },
    {
      title: '用过',
      dataIndex: 'usage_count',
      width: 70,
    },
    {
      title: '来源',
      dataIndex: 'source',
      width: 100,
      render: (v: string) => {
        const map: Record<string, { color: string; label: string }> = {
          generated: { color: 'orange', label: 'LLM 生成' },
          web_search: { color: 'purple', label: '搜索' },
          user_imported: { color: 'cyan', label: '资料抽取' },
        }
        const info = map[v] || { color: 'default', label: v }
        return <Tag color={info.color}>{info.label}</Tag>
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 80,
      render: (v: string) =>
        v === 'active' ? <Tag color="green">在用</Tag> : <Tag>已废弃</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_: unknown, row: QuestionBankItem) => (
        <>
          {row.status === 'active' ? (
            <Popconfirm
              title="确定废弃这道题吗？"
              onConfirm={() => handleDeprecate(row.id)}
            >
              <Button size="small" danger icon={<DeleteOutlined />}>
                废弃
              </Button>
            </Popconfirm>
          ) : (
            <Button
              size="small"
              icon={<UndoOutlined />}
              onClick={() => handleRestore(row.id)}
            >
              恢复
            </Button>
          )}
        </>
      ),
    },
  ]

  return (
    <div>
      <Card title="题库浏览" style={{ marginBottom: 16 }}>
        <Space wrap style={{ marginBottom: 16 }}>
          <Select
            style={{ width: 180 }}
            value={selectedCourse}
            onChange={setSelectedCourse}
            placeholder="选择课程"
            options={courses.map((c) => ({
              label: c.display_name || c.name,
              value: c.id,
            }))}
          />
          <Select
            style={{ width: 120 }}
            value={filterType}
            onChange={setFilterType}
            placeholder="题型"
            allowClear
            options={[
              { label: '全部题型', value: '' },
              { label: '简答', value: '简答' },
              { label: '选择', value: '选择' },
            ]}
          />
          <Select
            style={{ width: 120 }}
            value={filterDifficulty}
            onChange={setFilterDifficulty}
            placeholder="难度"
            allowClear
            options={[
              { label: '全部难度', value: '' },
              { label: '易', value: '易' },
              { label: '中', value: '中' },
              { label: '难', value: '难' },
            ]}
          />
          <Select
            style={{ width: 120 }}
            value={filterStatus}
            onChange={setFilterStatus}
            options={[
              { label: '在用', value: 'active' },
              { label: '已废弃', value: 'deprecated' },
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={refresh} loading={loading}>
            刷新
          </Button>
        </Space>

        {stats && (
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={6}>
              <Statistic title="题库总量" value={stats.total} />
            </Col>
            <Col span={6}>
              <Statistic title="平均质量分" value={stats.avg_quality} precision={2} />
            </Col>
            <Col span={6}>
              <Statistic title="已废弃" value={stats.deprecated} />
            </Col>
            <Col span={6}>
              <Statistic
                title="题型分布"
                value={
                  Object.entries(stats.by_type)
                    .map(([k, v]) => `${k}:${v}`)
                    .join(' ') || '—'
                }
                valueStyle={{ fontSize: 16 }}
              />
            </Col>
          </Row>
        )}

        {questions.length === 0 && !loading ? (
          <Alert
            type="info"
            showIcon
            message="没有符合条件的题目"
            description="调整筛选条件，或到「预热向导」生成一批题目。"
          />
        ) : (
          <Table
            rowKey="id"
            dataSource={questions}
            columns={columns}
            loading={loading}
            pagination={{ pageSize: 20 }}
            size="middle"
          />
        )}
      </Card>

      {/* 详情弹窗 */}
      <Modal
        title="题目详情"
        open={detailOpen}
        onCancel={() => setDetailOpen(false)}
        footer={null}
        width={720}
      >
        {currentQuestion && (
          <>
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label="ID">{currentQuestion.id}</Descriptions.Item>
              <Descriptions.Item label="知识点">
                {currentQuestion.knowledge_point}
              </Descriptions.Item>
              <Descriptions.Item label="题型">
                {currentQuestion.question_type}
              </Descriptions.Item>
              <Descriptions.Item label="难度">
                {currentQuestion.difficulty}
              </Descriptions.Item>
              <Descriptions.Item label="质量分">
                {currentQuestion.quality_score}
              </Descriptions.Item>
              <Descriptions.Item label="用过">
                {currentQuestion.usage_count}
              </Descriptions.Item>
              <Descriptions.Item label="提示词版本" span={2}>
                {currentQuestion.prompt_version || '—'}
              </Descriptions.Item>
            </Descriptions>

            <div style={{ marginTop: 16 }}>
              <h4>题干</h4>
              <p>{currentQuestion.payload.question || '（缺失）'}</p>
            </div>

            {currentQuestion.payload.options && (
              <div style={{ marginTop: 16 }}>
                <h4>选项</h4>
                {currentQuestion.payload.options.map((opt, i) => (
                  <p
                    key={i}
                    style={{
                      fontWeight:
                        i === currentQuestion.payload.correct_index ? 'bold' : 'normal',
                      color:
                        i === currentQuestion.payload.correct_index ? 'green' : undefined,
                    }}
                  >
                    {String.fromCharCode(65 + i)}. {opt}
                  </p>
                ))}
              </div>
            )}

            {currentQuestion.payload.reference_answer && (
              <div style={{ marginTop: 16 }}>
                <h4>参考答案</h4>
                <p>{currentQuestion.payload.reference_answer}</p>
              </div>
            )}

            {currentQuestion.payload.scoring_points &&
              currentQuestion.payload.scoring_points.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <h4>评分要点</h4>
                  <ul>
                    {currentQuestion.payload.scoring_points.map((p, i) => (
                      <li key={i}>{p}</li>
                    ))}
                  </ul>
                </div>
              )}

            {currentQuestion.payload.explanation && (
              <div style={{ marginTop: 16 }}>
                <h4>解析</h4>
                <p>{currentQuestion.payload.explanation}</p>
              </div>
            )}
          </>
        )}
      </Modal>
    </div>
  )
}