// ============================================================
// 文件：pages/WrongBook.tsx
// 用途：错题集页（完整版）
// ============================================================

import { useEffect, useState } from 'react'
import {
  Card,
  Table,
  Select,
  Button,
  Space,
  Tag,
  message,
  Popconfirm,
  Statistic,
  Row,
  Col,
  Empty,
  Alert,
} from 'antd'
import * as userApi from '../api/user'
import { extractErrorMessage } from '../api/client'
import type { Course, WrongBookStats, WrongQuestion } from '../types'

export default function WrongBook() {
  const [courses, setCourses] = useState<Course[]>([])
  const [selectedCourseId, setSelectedCourseId] = useState<number | null>(null)

  const [stats, setStats] = useState<WrongBookStats | null>(null)
  const [entries, setEntries] = useState<WrongQuestion[]>([])
  const [loading, setLoading] = useState(false)

  const [filterMastery, setFilterMastery] = useState<string>('unmastered')
  const [orderBy, setOrderBy] = useState<string>('最近答错')

  // ---------- 加载课程 ----------
  useEffect(() => {
    const fetch = async () => {
      try {
        const list = await userApi.listCourses()
        setCourses(list)
        if (list.length > 0 && !selectedCourseId) {
          setSelectedCourseId(list[0].id)
        }
      } catch (err) {
        message.error(extractErrorMessage(err))
      }
    }
    fetch()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ---------- 加载错题和统计 ----------
  useEffect(() => {
    if (!selectedCourseId) return

    const fetch = async () => {
      setLoading(true)
      try {
        const [list, s] = await Promise.all([
          userApi.listWrongQuestions(selectedCourseId, {
            masteryStatus: filterMastery || undefined,
            orderBy,
          }),
          userApi.getWrongBookStats(selectedCourseId),
        ])
        setEntries(list)
        setStats(s)
      } catch (err) {
        message.error(extractErrorMessage(err))
      } finally {
        setLoading(false)
      }
    }
    fetch()
  }, [selectedCourseId, filterMastery, orderBy])

  // ---------- 重新加载 ----------
  const refresh = async () => {
    if (!selectedCourseId) return
    setLoading(true)
    try {
      const [list, s] = await Promise.all([
        userApi.listWrongQuestions(selectedCourseId, {
          masteryStatus: filterMastery || undefined,
          orderBy,
        }),
        userApi.getWrongBookStats(selectedCourseId),
      ])
      setEntries(list)
      setStats(s)
    } catch (err) {
      message.error(extractErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  // ---------- 标记掌握 ----------
  const handleMastery = async (entryId: number, mastered: boolean) => {
    try {
      await userApi.updateMastery(entryId, mastered)
      message.success(mastered ? '已标记为已掌握' : '已打回待复习')
      await refresh()
    } catch (err) {
      message.error(extractErrorMessage(err))
    }
  }

  // ---------- 删除 ----------
  const handleDelete = async (entryId: number) => {
    try {
      await userApi.deleteWrongQuestion(entryId)
      message.success('已删除')
      await refresh()
    } catch (err) {
      message.error(extractErrorMessage(err))
    }
  }

  // ---------- 表格列 ----------
  const columns = [
    {
      title: '题干',
      dataIndex: ['payload', 'question'],
      key: 'question',
      ellipsis: true,
      render: (text: string) => (
        <span title={text}>{text?.slice(0, 60) || '（无题干）'}</span>
      ),
    },
    {
      title: '知识点',
      dataIndex: 'knowledge_point',
      key: 'kp',
      width: 140,
      render: (v: string) => <Tag>{v || '未分类'}</Tag>,
    },
    {
      title: '错次',
      dataIndex: 'wrong_count',
      key: 'wrong',
      width: 70,
      render: (v: number) => <Tag color="red">{v}</Tag>,
    },
    {
      title: '复习',
      dataIndex: 'review_count',
      key: 'review',
      width: 70,
    },
    {
      title: '状态',
      dataIndex: 'mastery_status',
      key: 'status',
      width: 90,
      render: (v: string, row: WrongQuestion) => (
        <Tag color={v === 'mastered' ? 'green' : 'orange'}>{row.mastery_label}</Tag>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 220,
      render: (_: unknown, row: WrongQuestion) => (
        <Space>
          {row.mastery_status === 'mastered' ? (
            <Button size="small" onClick={() => handleMastery(row.id, false)}>
              打回
            </Button>
          ) : (
            <Button
              size="small"
              type="primary"
              onClick={() => handleMastery(row.id, true)}
            >
              已掌握
            </Button>
          )}
          <Popconfirm
            title="确定删除这道错题吗？"
            onConfirm={() => handleDelete(row.id)}
          >
            <Button size="small" danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // ---------- 渲染 ----------
  return (
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>
      <Card title="错题集" style={{ marginBottom: 16 }}>
        <Space wrap style={{ marginBottom: 16 }}>
          <div>
            <div style={{ fontSize: 12, color: '#666', marginBottom: 4 }}>课程</div>
            <Select
              style={{ width: 160 }}
              value={selectedCourseId}
              onChange={setSelectedCourseId}
              placeholder="选择课程"
              options={courses.map((c) => ({
                label: c.display_name || c.name,
                value: c.id,
              }))}
            />
          </div>

          <div>
            <div style={{ fontSize: 12, color: '#666', marginBottom: 4 }}>状态</div>
            <Select
              style={{ width: 120 }}
              value={filterMastery}
              onChange={setFilterMastery}
              options={[
                { label: '全部', value: '' },
                { label: '待复习', value: 'unmastered' },
                { label: '已掌握', value: 'mastered' },
              ]}
            />
          </div>

          <div>
            <div style={{ fontSize: 12, color: '#666', marginBottom: 4 }}>排序</div>
            <Select
              style={{ width: 140 }}
              value={orderBy}
              onChange={setOrderBy}
              options={[
                { label: '最近答错', value: '最近答错' },
                { label: '错得最多', value: '错得最多' },
                { label: '最近复习', value: '最近复习' },
                { label: '按知识点', value: '按知识点' },
              ]}
            />
          </div>

          <div style={{ alignSelf: 'flex-end' }}>
            <Button onClick={refresh}>刷新</Button>
          </div>
        </Space>

        {stats && (
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={6}>
              <Statistic title="错题总数" value={stats.total} />
            </Col>
            <Col span={6}>
              <Statistic title="待复习" value={stats.unmastered} valueStyle={{ color: '#fa8c16' }} />
            </Col>
            <Col span={6}>
              <Statistic title="已掌握" value={stats.mastered} valueStyle={{ color: '#52c41a' }} />
            </Col>
            <Col span={6}>
              <Statistic title="从未复习" value={stats.never_reviewed} />
            </Col>
          </Row>
        )}

        {courses.length === 0 && (
          <Alert
            type="info"
            showIcon
            message="还没有课程"
            description="请到后台管理页新建课程并导入资料。"
            style={{ marginBottom: 16 }}
          />
        )}

        {entries.length === 0 && !loading ? (
          <Empty description="还没有错题。练习时答错会自动收进来。" />
        ) : (
          <Table
            rowKey="id"
            dataSource={entries}
            columns={columns}
            loading={loading}
            pagination={{ pageSize: 20 }}
          />
        )}
      </Card>
    </div>
  )
}