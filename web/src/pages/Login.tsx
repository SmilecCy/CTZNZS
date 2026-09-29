// ============================================================
    // 文件：pages/Login.tsx
    // 用途：登录页
    // ============================================================

    import { useState } from 'react'
    import { useNavigate, Link } from 'react-router-dom'
    import { Form, Input, Button, Card, Typography, message, Tabs } from 'antd'
    import { UserOutlined, LockOutlined } from '@ant-design/icons'
    import { useAuthStore } from '../stores/auth'
    import { extractErrorMessage } from '../api/client'

    const { Title } = Typography

    export default function Login() {
      const [loading, setLoading] = useState(false)
      const [activeTab, setActiveTab] = useState('login')

      const login = useAuthStore((state) => state.login)
      const register = useAuthStore((state) => state.register)

      const navigate = useNavigate()

      const handleLogin = async (values: { username: string; password: string }) => {
        setLoading(true)

        try {
          await login(values.username, values.password)
          message.success('登录成功')
          navigate('/practice')
        } catch (err) {
          message.error(extractErrorMessage(err))
        } finally {
          setLoading(false)
        }
      }

      const handleRegister = async (values: {
        username: string
        password: string
        display_name?: string
      }) => {
        setLoading(true)

        try {
          await register(values.username, values.password, values.display_name)
          message.success('注册成功，已自动登录')
          navigate('/practice')
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
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
          }}
        >
          <Card
            style={{
              width: 420,
              boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
            }}
          >
            <div style={{ textAlign: 'center', marginBottom: 24 }}>
              <Title level={3} style={{ margin: 0 }}>
                思政+法学 双课程学习系统
              </Title>
              <p style={{ color: '#888', marginTop: 8 }}>
                题库优先 · AI 辅助 · 来源可追溯
              </p>
            </div>

            <Tabs
              activeKey={activeTab}
              onChange={setActiveTab}
              centered
              items={[
                {
                  key: 'login',
                  label: '登录',
                  children: (
                    <Form
                      name="login"
                      onFinish={handleLogin}
                      size="large"
                      autoComplete="off"
                    >
                      <Form.Item
                        name="username"
                        rules={[{ required: true, message: '请输入用户名' }]}
                      >
                        <Input
                          prefix={<UserOutlined />}
                          placeholder="用户名"
                        />
                      </Form.Item>

                      <Form.Item
                        name="password"
                        rules={[{ required: true, message: '请输入密码' }]}
                      >
                        <Input.Password
                          prefix={<LockOutlined />}
                          placeholder="密码"
                        />
                      </Form.Item>

                      <Form.Item>
                        <Button
                          type="primary"
                          htmlType="submit"
                          loading={loading}
                          block
                        >
                          登录
                        </Button>
                      </Form.Item>
                    </Form>
                  ),
                },
                {
                  key: 'register',
                  label: '注册',
                  children: (
                    <Form
                      name="register"
                      onFinish={handleRegister}
                      size="large"
                      autoComplete="off"
                    >
                      <Form.Item
                        name="username"
                        rules={[
                          { required: true, message: '请输入用户名' },
                          { min: 3, message: '用户名至少 3 个字符' },
                        ]}
                      >
                        <Input
                          prefix={<UserOutlined />}
                          placeholder="用户名（至少 3 个字符）"
                        />
                      </Form.Item>

                      <Form.Item name="display_name">
                        <Input placeholder="显示名（可选）" />
                      </Form.Item>

                      <Form.Item
                        name="password"
                        rules={[
                          { required: true, message: '请输入密码' },
                          { min: 6, message: '密码至少 6 个字符' },
                        ]}
                      >
                        <Input.Password
                          prefix={<LockOutlined />}
                          placeholder="密码（至少 6 个字符）"
                        />
                      </Form.Item>

                      <Form.Item>
                        <Button
                          type="primary"
                          htmlType="submit"
                          loading={loading}
                          block
                        >
                          注册并登录
                        </Button>
                      </Form.Item>
                    </Form>
                  ),
                },
              ]}
            />

            <div style={{ textAlign: 'center', marginTop: 16, fontSize: 12, color: '#999' }}>
              <Link to="/admin/login">管理员入口</Link>
            </div>
          </Card>
        </div>
      )
    }