// ============================================================
// 文件：pages/admin/AdminLogin.tsx
// 用途：后台登录页（只让管理员登录）
// ============================================================

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Form, Input, Button, Card, Typography, message } from 'antd'
import { UserOutlined, LockOutlined, SafetyOutlined } from '@ant-design/icons'
import { useAdminAuthStore } from '../../stores/adminAuth'
import { extractErrorMessage } from '../../api/client'

const { Title } = Typography

export default function AdminLogin() {
  const [loading, setLoading] = useState(false)
  const login = useAdminAuthStore((state) => state.login)
  const navigate = useNavigate()

  const handleLogin = async (values: { username: string; password: string }) => {
    setLoading(true)

    try {
      await login(values.username, values.password)
      message.success('登录成功')
      navigate('/admin/dashboard')
    } catch (err) {
      message.error(extractErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'linear-gradient(135deg, #1e3c72 0%, #2a5298 100%)',
      }}
    >
      <Card
        style={{
          width: 400,
          boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
        }}
      >
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <SafetyOutlined style={{ fontSize: 48, color: '#1677ff' }} />
          <Title level={3} style={{ marginTop: 16, marginBottom: 0 }}>
            后台管理登录
          </Title>
          <p style={{ color: '#888', marginTop: 8 }}>仅限管理员访问</p>
        </div>

        <Form
          name="admin-login"
          onFinish={handleLogin}
          size="large"
          autoComplete="off"
        >
          <Form.Item
            name="username"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input prefix={<UserOutlined />} placeholder="管理员用户名" />
          </Form.Item>

          <Form.Item
            name="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>

          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block>
              登录
            </Button>
          </Form.Item>
        </Form>

        <div style={{ textAlign: 'center', marginTop: 16, fontSize: 12, color: '#999' }}>
          初始账号：admin / admin123
          <br />
          <a href="/login" style={{ color: '#1677ff' }}>返回学生端</a>
        </div>
      </Card>
    </div>
  )
}