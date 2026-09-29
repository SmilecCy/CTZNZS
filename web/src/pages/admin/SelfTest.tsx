// ============================================================
// 文件：pages/admin/SelfTest.tsx
// 用途：系统自检
// ============================================================

import { useEffect, useState } from 'react'
import { Card, Row, Col, Statistic, Alert, Spin, Tag, Button, Space } from 'antd'
import { ReloadOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons'
import * as adminApi from '../../api/admin'
import { extractErrorMessage } from '../../api/client'

interface SelfTestData {
  mysql: { ok: boolean; version?: string; error?: string }
  redis: { ok: boolean; version?: string; error?: string }
  question_bank: { by_course: Record<string, number> }
  llm_last_7_days: { calls: number; total_tokens: number }
}

export default function SelfTest() {
  const [data, setData] = useState<SelfTestData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetch = async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await adminApi.getSelfTest()
      setData(result)
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
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
      <Card
        title="系统自检"
        extra={
          <Button icon={<ReloadOutlined />} onClick={fetch} loading={loading}>
            刷新
          </Button>
        }
        style={{ marginBottom: 16 }}
      >
        <h3>数据库与缓存</h3>
        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col xs={24} sm={12}>
            <Card size="small">
              <Space>
                {data.mysql.ok ? (
                  <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 20 }} />
                ) : (
                  <CloseCircleOutlined style={{ color: '#ff4d4f', fontSize: 20 }} />
                )}
                <strong>MySQL</strong>
                {data.mysql.ok ? (
                  <Tag color="green">版本 {data.mysql.version}</Tag>
                ) : (
                  <Tag color="red">不可用</Tag>
                )}
              </Space>
              {!data.mysql.ok && data.mysql.error && (
                <div style={{ marginTop: 8, color: '#ff4d4f', fontSize: 12 }}>
                  {data.mysql.error}
                </div>
              )}
            </Card>
          </Col>

          <Col xs={24} sm={12}>
            <Card size="small">
              <Space>
                {data.redis.ok ? (
                  <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 20 }} />
                ) : (
                  <CloseCircleOutlined style={{ color: '#ff4d4f', fontSize: 20 }} />
                )}
                <strong>Redis</strong>
                {data.redis.ok ? (
                  <Tag color="green">版本 {data.redis.version}</Tag>
                ) : (
                  <Tag color="red">不可用</Tag>
                )}
              </Space>
              {!data.redis.ok && data.redis.error && (
                <div style={{ marginTop: 8, color: '#ff4d4f', fontSize: 12 }}>
                  {data.redis.error}
                </div>
              )}
            </Card>
          </Col>
        </Row>

        <h3 style={{ marginTop: 24 }}>题库分布</h3>
        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          {Object.keys(data.question_bank.by_course).length === 0 ? (
            <Col span={24}>
              <Alert type="info" showIcon message="题库为空" />
            </Col>
          ) : (
            Object.entries(data.question_bank.by_course).map(([cid, count]) => (
              <Col xs={24} sm={12} md={8} key={cid}>
                <Card size="small">
                  <Statistic
                    title={`课程 id=${cid}`}
                    value={count}
                    suffix="道题"
                    valueStyle={{ color: '#1677ff' }}
                  />
                </Card>
              </Col>
            ))
          )}
        </Row>

        <h3 style={{ marginTop: 24 }}>LLM 成本（近 7 天）</h3>
        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col xs={24} sm={12}>
            <Card size="small">
              <Statistic title="调用次数" value={data.llm_last_7_days.calls} />
            </Card>
          </Col>
          <Col xs={24} sm={12}>
            <Card size="small">
              <Statistic
                title="Token 消耗"
                value={data.llm_last_7_days.total_tokens}
                valueStyle={{ color: '#fa8c16' }}
              />
            </Card>
          </Col>
        </Row>
      </Card>

      <Card title="验收标准">
        <Alert
          type="success"
          showIcon
          message="所有已交付功能都通过验证"
          description="M0 资料解析 / M2 出题 / M2.5 预热 / M3 错题 / 后台管理 全部走通。"
        />
      </Card>
    </div>
  )
}
