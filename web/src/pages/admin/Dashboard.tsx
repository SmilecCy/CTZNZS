// ============================================================
// 文件：pages/admin/Dashboard.tsx
// 用途：后台首页数据总览
// ============================================================

import { useEffect, useState } from 'react'
import { Card, Row, Col, Statistic, Alert, Spin, message } from 'antd'
import {
  BookOutlined,
  DatabaseOutlined,
  ExclamationCircleOutlined,
  FileTextOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import * as adminApi from '../../api/admin'
import { extractErrorMessage } from '../../api/client'

interface DashboardData {
  course_count: number
  material_count: number
  pending_classification_count: number
  question_count: number
  llm_calls_today: number
}

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetch = async () => {
      setLoading(true)
      setError(null)
      try {
        const result = await adminApi.getDashboard()
        setData(result)
      } catch (err) {
        setError(extractErrorMessage(err))
      } finally {
        setLoading(false)
      }
    }
    fetch()
  }, [])

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin size="large" />
      </div>
    )
  }

  if (error) {
    return <Alert type="error" showIcon message="加载失败" description={error} />
  }

  if (!data) return null

  return (
    <div>
      <h2>数据总览</h2>

      <Row gutter={[16, 16]} style={{ marginTop: 24 }}>
        <Col xs={24} sm={12} md={8}>
          <Card>
            <Statistic
              title="课程总数"
              value={data.course_count}
              prefix={<BookOutlined />}
              valueStyle={{ color: '#1677ff' }}
            />
          </Card>
        </Col>

        <Col xs={24} sm={12} md={8}>
          <Card>
            <Statistic
              title="资料总数"
              value={data.material_count}
              prefix={<DatabaseOutlined />}
            />
          </Card>
        </Col>

        <Col xs={24} sm={12} md={8}>
          <Card>
            <Statistic
              title="待分类资料"
              value={data.pending_classification_count}
              prefix={<ExclamationCircleOutlined />}
              valueStyle={{
                color: data.pending_classification_count > 0 ? '#fa8c16' : undefined,
              }}
            />
          </Card>
        </Col>

        <Col xs={24} sm={12} md={8}>
          <Card>
            <Statistic
              title="题库题量"
              value={data.question_count}
              prefix={<FileTextOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>

        <Col xs={24} sm={12} md={8}>
          <Card>
            <Statistic
              title="今日 LLM 调用"
              value={data.llm_calls_today}
              prefix={<ThunderboltOutlined />}
            />
          </Card>
        </Col>
      </Row>

      {data.course_count === 0 && (
        <Alert
          type="info"
          showIcon
          message="还没有课程"
          description="到「课程管理」新建课程，然后到「资料管理」上传资料。"
          style={{ marginTop: 24 }}
        />
      )}

      {data.pending_classification_count > 0 && (
        <Alert
          type="warning"
          showIcon
          message={`有 ${data.pending_classification_count} 份资料等待分类确认`}
          description="到「资料管理」确认这些资料的归属课程。"
          style={{ marginTop: 16 }}
        />
      )}
    </div>
  )
}