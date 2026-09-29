# -*- coding: utf-8 -*-
"""一次性创建 web/ 下的所有文件。

用法：
    python scripts/create_web_files.py

【为什么要有这个脚本】
    PyCharm 创建文件时容易留空（不会提示"未保存"）。
    用脚本写文件，保证内容完整、编码统一。
"""

from pathlib import Path

# web 目录的绝对路径
WEB = Path(__file__).resolve().parent.parent / "web"


def write(rel_path: str, content: str) -> None:
    """写入一个文件。

    Args:
        rel_path: 相对 web/ 的路径，例如 "vite.config.ts"
        content: 文件内容
    """
    full = WEB / rel_path
    # 确保父目录存在
    full.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n" 保证换行符统一（Windows 默认是 \r\n，某些工具处理不好）
    full.write_text(content, encoding="utf-8", newline="\n")
    size = len(content.encode("utf-8"))
    print(f"  [OK] {rel_path:35s} {size:>6} 字节")


def main() -> int:
    print("=" * 60)
    print("创建 web/ 下的所有文件")
    print("=" * 60)
    print(f"目标目录：{WEB}")
    print()

    # 后续在这里写各文件的 write(...) 调用
    # ...
    # =========================================================
    # 第 1 批：根目录配置文件
    # =========================================================

    write("package.json", '''{
      "name": "study-system-web",
      "private": true,
      "version": "1.0.0",
      "type": "module",
      "scripts": {
        "dev": "vite",
        "build": "tsc -b && vite build",
        "preview": "vite preview",
        "lint": "tsc --noEmit"
      },
      "dependencies": {
        "react": "^18.3.1",
        "react-dom": "^18.3.1",
        "react-router-dom": "^6.26.0",
        "antd": "^5.21.0",
        "@ant-design/icons": "^5.5.0",
        "axios": "^1.7.7",
        "zustand": "^5.0.0",
        "dayjs": "^1.11.13"
      },
      "devDependencies": {
        "@types/react": "^18.3.10",
        "@types/react-dom": "^18.3.0",
        "@vitejs/plugin-react": "^4.3.2",
        "typescript": "^5.6.2",
        "vite": "^5.4.8"
      }
    }
    ''')

    write("vite.config.ts", '''import { defineConfig } from 'vite'
    import react from '@vitejs/plugin-react'

    export default defineConfig({
      plugins: [react()],
      server: {
        port: 5173,
        proxy: {
          '/api': {
            target: 'http://localhost:8000',
            changeOrigin: true,
          },
        },
      },
      build: {
        outDir: 'dist',
        sourcemap: false,
      },
    })
    ''')

    write("tsconfig.json", '''{
      "compilerOptions": {
        "target": "ES2022",
        "useDefineForClassFields": true,
        "lib": ["ES2022", "DOM", "DOM.Iterable"],
        "module": "ESNext",
        "skipLibCheck": true,
        "moduleResolution": "bundler",
        "allowImportingTsExtensions": true,
        "resolveJsonModule": true,
        "isolatedModules": true,
        "noEmit": true,
        "jsx": "react-jsx",
        "strict": true,
        "noUnusedLocals": false,
        "noUnusedParameters": false,
        "noFallthroughCasesInSwitch": true,
        "baseUrl": ".",
        "paths": {
          "@/*": ["./src/*"]
        }
      },
      "include": ["src"]
    }
    ''')

    write("index.html", '''<!doctype html>
    <html lang="zh-CN">
      <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>思政+法学 双课程 AI 辅助学习系统</title>
      </head>
      <body>
        <div id="root"></div>
        <script type="module" src="/src/main.tsx"></script>
      </body>
    </html>
    ''')

    write(".gitignore", '''node_modules/
    dist/
    dist-ssr/
    .env.local
    .env.*.local
    .vscode/*
    !.vscode/extensions.json
    .idea/
    *.swp
    .DS_Store
    Thumbs.db
    *.log
    npm-debug.log*
    yarn-debug.log*
    yarn-error.log*
    pnpm-debug.log*
    ''')

    # =========================================================
    # 第 2 批：src 核心文件
    # =========================================================

    write("src/main.tsx", '''// ============================================================
    // 文件：main.tsx
    // 用途：React 应用入口
    //
    // 【这个文件干什么】
    //   整个 React 应用从这里开始。它做三件事：
    //     1. 找到 HTML 里的 <div id="root">
    //     2. 把 <App /> 组件渲染进去
    //     3. 配置全局样式（Ant Design）
    // ============================================================

    import React from 'react'
    import ReactDOM from 'react-dom/client'
    import { ConfigProvider } from 'antd'
    import zhCN from 'antd/locale/zh_CN'
    import App from './App'
    import './index.css'

    // 把 <App /> 渲染到 HTML 里
    ReactDOM.createRoot(document.getElementById('root')!).render(
      // React.StrictMode 是开发辅助工具：
      //   - 会故意把某些函数调用两次，帮你发现副作用 bug
      //   - 只在开发模式生效，生产构建会自动去掉
      <React.StrictMode>
        {/* ConfigProvider 是 Ant Design 的全局配置 */}
        <ConfigProvider
          locale={zhCN}
          theme={{
            token: {
              colorPrimary: '#1677ff',
            },
          }}
        >
          <App />
        </ConfigProvider>
      </React.StrictMode>,
    )
    ''')

    write("src/index.css", '''/* ============================================================
     * 文件：index.css
     * 用途：全局样式
     * ============================================================ */

    /* 重置边距 */
    html,
    body,
    #root {
      margin: 0;
      padding: 0;
      height: 100%;
    }

    /* 字体设置 */
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC',
        'Hiragino Sans GB', 'Microsoft YaHei', 'Helvetica Neue', Helvetica, Arial,
        sans-serif;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }

    /* 去掉链接的默认下划线 */
    a {
      text-decoration: none;
    }
    ''')

    write("src/types/index.ts", '''// ============================================================
    // 文件：types/index.ts
    // 用途：TypeScript 类型定义
    // ============================================================

    // ---------- 用户与认证 ----------
    export interface User {
      id: number
      username: string
      role: 'user' | 'admin'
      display_name: string
    }

    export interface LoginRequest {
      username: string
      password: string
      role?: 'user' | 'admin'
    }

    export interface RegisterRequest {
      username: string
      password: string
      display_name?: string
      email?: string
    }

    export interface TokenResponse {
      access_token: string
      token_type: string
      expires_in: number
      user: User
    }

    // ---------- 课程与知识点 ----------
    export interface Course {
      id: number
      name: string
      display_name: string
      description?: string
      question_focus?: string
    }

    export interface KnowledgePoint {
      id: number
      course_id: number
      name: string
      description?: string
      sort_order: number
    }

    // ---------- 出题 ----------
    export type QuestionType = '简答' | '选择'
    export type Difficulty = '易' | '中' | '难'

    export interface QuestionRequest {
      course_id: number
      knowledge_point: string
      question_type: QuestionType
      difficulty: Difficulty
      count: number
      knowledge_point_id?: number
    }

    export interface Question {
      id: number
      question: string
      question_type: QuestionType
      difficulty: Difficulty
      knowledge_tags?: string[]
      source_ref?: string
      from?: 'bank' | 'llm' | 'search'
      reference_answer?: string
      scoring_points?: string[]
      options?: string[]
      correct_index?: number
      explanation?: string
    }

    export interface QuestionResponse {
      questions: Question[]
      source_summary: {
        from_bank: number
        from_llm: number
        from_search?: number
      }
      warnings: string[]
    }

    // ---------- 作答 ----------
    export interface AnswerRequest {
      question_id: number
      user_answer: string
    }

    export interface AnswerResponse {
      is_correct: boolean | null
      score: number | null
      reference_answer: string
      comment: string
      error?: string | null
    }

    // ---------- 错题集 ----------
    export interface WrongQuestion {
      id: number
      question_bank_id: number | null
      knowledge_point: string | null
      question_type: string | null
      mastery_status: 'unmastered' | 'mastered'
      wrong_count: number
      review_count: number
      payload: Question
    }

    // ---------- 通用响应 ----------
    export interface SuccessResponse {
      success: boolean
      message: string
      data?: Record<string, unknown>
    }
    ''')

    write("src/api/client.ts", '''// ============================================================
    // 文件：api/client.ts
    // 用途：axios 封装 —— 所有 HTTP 请求都从这里走
    // ============================================================

    import axios, { AxiosError, AxiosInstance, AxiosResponse } from 'axios'

    const client: AxiosInstance = axios.create({
      baseURL: '',
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    })

    // ============================================================
    // 请求拦截器：自动加 Authorization 头
    // ============================================================
    client.interceptors.request.use(
      (config) => {
        const token = localStorage.getItem('access_token')

        if (token) {
          config.headers.Authorization = `Bearer ${token}`
        }

        return config
      },
      (error) => {
        return Promise.reject(error)
      },
    )

    // ============================================================
    // 响应拦截器：统一错误处理
    // ============================================================
    client.interceptors.response.use(
      (response: AxiosResponse) => {
        return response
      },

      (error: AxiosError) => {
        if (error.response) {
          const status = error.response.status

          if (status === 401) {
            localStorage.removeItem('access_token')
            localStorage.removeItem('user')

            if (window.location.pathname !== '/login') {
              window.location.href = '/login'
            }
          }
        }

        return Promise.reject(error)
      },
    )

    // ============================================================
    // 错误信息提取
    // ============================================================
    export function extractErrorMessage(error: unknown): string {
      if (axios.isAxiosError(error)) {
        const data = error.response?.data

        if (data) {
          if (typeof data === 'string') return data

          if (data.detail) {
            if (typeof data.detail === 'string') return data.detail
            if (typeof data.detail === 'object' && data.detail.message) {
              return data.detail.message
            }
          }

          if (data.error) {
            if (typeof data.error === 'string') return data.error
            if (typeof data.error === 'object' && data.error.message) {
              return data.error.message
            }
          }

          if (data.message) return data.message
        }

        if (error.response?.status === 500) {
          return '服务器内部错误，请稍后重试'
        }
        if (error.response?.status === 404) {
          return '请求的资源不存在'
        }
        if (error.code === 'ECONNABORTED') {
          return '请求超时，请检查网络'
        }
        if (error.message) {
          return error.message
        }
      }

      if (error instanceof Error) {
        return error.message
      }

      return '发生未知错误'
    }

    export default client
    ''')

    write("src/api/auth.ts", '''// ============================================================
    // 文件：api/auth.ts
    // 用途：认证相关的 API 调用
    // ============================================================

    import client from './client'
    import type {
      LoginRequest,
      RegisterRequest,
      TokenResponse,
      User,
    } from '../types'

    // 登录
    export async function login(data: LoginRequest): Promise<TokenResponse> {
      const response = await client.post<TokenResponse>('/api/auth/login', data)
      return response.data
    }

    // 注册
    export async function register(data: RegisterRequest): Promise<TokenResponse> {
      const response = await client.post<TokenResponse>('/api/auth/register', data)
      return response.data
    }

    // 登出
    export async function logout(): Promise<void> {
      try {
        await client.post('/api/auth/logout')
      } catch {
        // 忽略错误
      }
    }

    // 获取当前用户
    export async function getCurrentUser(): Promise<User> {
      const response = await client.get<User>('/api/auth/me')
      return response.data
    }
    ''')

    # =========================================================
    # 第 3 批：状态管理、布局、页面
    # =========================================================

    write("src/stores/auth.ts", '''// ============================================================
    // 文件：stores/auth.ts
    // 用途：登录状态管理（Zustand）
    // ============================================================

    import { create } from 'zustand'
    import type { User } from '../types'
    import * as authApi from '../api/auth'

    interface AuthState {
      user: User | null
      isAuthenticated: boolean

      login: (username: string, password: string, role?: 'user' | 'admin') => Promise<User>
      register: (username: string, password: string, displayName?: string) => Promise<User>
      logout: () => Promise<void>
      loadFromStorage: () => void
    }

    export const useAuthStore = create<AuthState>((set, get) => ({
      user: null,
      isAuthenticated: false,

      login: async (username, password, role = 'user') => {
        const result = await authApi.login({ username, password, role })

        localStorage.setItem('access_token', result.access_token)
        localStorage.setItem('user', JSON.stringify(result.user))

        set({
          user: result.user,
          isAuthenticated: true,
        })

        return result.user
      },

      register: async (username, password, displayName = '') => {
        const result = await authApi.register({
          username,
          password,
          display_name: displayName,
        })

        localStorage.setItem('access_token', result.access_token)
        localStorage.setItem('user', JSON.stringify(result.user))

        set({
          user: result.user,
          isAuthenticated: true,
        })

        return result.user
      },

      logout: async () => {
        await authApi.logout()

        localStorage.removeItem('access_token')
        localStorage.removeItem('user')

        set({
          user: null,
          isAuthenticated: false,
        })
      },

      loadFromStorage: () => {
        const token = localStorage.getItem('access_token')
        const userJson = localStorage.getItem('user')

        if (!token || !userJson) {
          return
        }

        try {
          const user = JSON.parse(userJson) as User
          set({
            user,
            isAuthenticated: true,
          })
        } catch {
          localStorage.removeItem('access_token')
          localStorage.removeItem('user')
        }
      },
    }))
    ''')

    write("src/layouts/UserLayout.tsx", '''// ============================================================
    // 文件：layouts/UserLayout.tsx
    // 用途：用户端布局（顶部导航 + 内容区）
    // ============================================================

    import { Layout, Menu, Dropdown, Avatar, Space, message } from 'antd'
    import { UserOutlined, LogoutOutlined, BookOutlined, FileTextOutlined } from '@ant-design/icons'
    import { Outlet, useNavigate, useLocation } from 'react-router-dom'
    import { useAuthStore } from '../stores/auth'

    const { Header, Content } = Layout

    export default function UserLayout() {
      const navigate = useNavigate()
      const location = useLocation()
      const user = useAuthStore((state) => state.user)
      const logout = useAuthStore((state) => state.logout)

      const handleLogout = async () => {
        await logout()
        message.success('已登出')
        navigate('/login')
      }

      const menuItems = [
        {
          key: '/practice',
          icon: <BookOutlined />,
          label: '练习',
        },
        {
          key: '/wrong-book',
          icon: <FileTextOutlined />,
          label: '错题集',
        },
      ]

      const selectedKey =
        menuItems.find((item) => location.pathname.startsWith(item.key))?.key ||
        '/practice'

      return (
        <Layout style={{ minHeight: '100vh' }}>
          <Header
            style={{
              display: 'flex',
              alignItems: 'center',
              background: '#fff',
              padding: '0 24px',
              boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
            }}
          >
            <div
              style={{
                fontSize: 18,
                fontWeight: 600,
                marginRight: 40,
                color: '#1677ff',
              }}
            >
              📚 双课程学习系统
            </div>

            <Menu
              mode="horizontal"
              selectedKeys={[selectedKey]}
              items={menuItems}
              onClick={({ key }) => navigate(key)}
              style={{ flex: 1, borderBottom: 'none' }}
            />

            <Dropdown
              menu={{
                items: [
                  {
                    key: 'logout',
                    icon: <LogoutOutlined />,
                    label: '登出',
                    onClick: handleLogout,
                  },
                ],
              }}
            >
              <Space style={{ cursor: 'pointer' }}>
                <Avatar size="small" icon={<UserOutlined />} />
                <span>{user?.display_name || user?.username || '用户'}</span>
              </Space>
            </Dropdown>
          </Header>

          <Content
            style={{
              padding: 24,
              background: '#f5f5f5',
            }}
          >
            <Outlet />
          </Content>
        </Layout>
      )
    }
    ''')

    write("src/pages/Login.tsx", '''// ============================================================
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
              <Link to="/login">管理员入口</Link>
            </div>
          </Card>
        </div>
      )
    }
    ''')

    write("src/pages/Practice.tsx", '''// ============================================================
    // 文件：pages/Practice.tsx
    // 用途：练习页（阶段 5.1 占位版本）
    // ============================================================

    import { useEffect, useState } from 'react'
    import { Card, Button, Alert, Space, Tag, Empty } from 'antd'
    import client, { extractErrorMessage } from '../api/client'
    import type { Course } from '../types'

    export default function Practice() {
      const [courses, setCourses] = useState<Course[]>([])
      const [selectedCourseId, setSelectedCourseId] = useState<number | null>(null)
      const [loading, setLoading] = useState(false)
      const [error, setError] = useState<string | null>(null)

      useEffect(() => {
        const fetchCourses = async () => {
          setLoading(true)
          setError(null)
          try {
            const response = await client.get<Course[]>('/api/user/courses')
            setCourses(response.data)
          } catch (err) {
            setError(extractErrorMessage(err))
          } finally {
            setLoading(false)
          }
        }

        fetchCourses()
      }, [])

      return (
        <div style={{ maxWidth: 900, margin: '0 auto' }}>
          <Card title="练习模式（阶段 5.1 占位）">
            <Alert
              type="info"
              showIcon
              message="阶段 5.1 只验证前后端联通"
              description="练习功能（出题、作答、判分）会在阶段 5.2 交付。本页现在只展示课程列表，用来确认你能正常拿到后端数据。"
              style={{ marginBottom: 24 }}
            />

            {error && (
              <Alert
                type="error"
                showIcon
                message="加载课程失败"
                description={error}
                style={{ marginBottom: 24 }}
              />
            )}

            <Space direction="vertical" style={{ width: '100%' }} size="large">
              <div>
                <div style={{ marginBottom: 8, color: '#666' }}>
                  课程列表（来自后端 /api/user/courses）
                </div>
                {loading ? (
                  <div>加载中…</div>
                ) : courses.length === 0 ? (
                  <Empty
                    description={
                      <span>
                        还没有课程。
                        <br />
                        到后台管理页新建课程后，这里会显示。
                      </span>
                    }
                  />
                ) : (
                  <Space wrap>
                    {courses.map((c) => (
                      <Tag
                        key={c.id}
                        color={selectedCourseId === c.id ? 'blue' : 'default'}
                        style={{ cursor: 'pointer', padding: '6px 12px', fontSize: 14 }}
                        onClick={() => setSelectedCourseId(c.id)}
                      >
                        {c.display_name || c.name}
                      </Tag>
                    ))}
                  </Space>
                )}
              </div>

              <div>
                <div style={{ marginBottom: 8, color: '#666' }}>选中的课程 id</div>
                <div>{selectedCourseId ?? '（未选）'}</div>
              </div>

              <Button type="primary" disabled>
                开始练习（阶段 5.2 交付）
              </Button>
            </Space>
          </Card>
        </div>
      )
    }
    ''')

    write("src/pages/WrongBook.tsx", '''// ============================================================
    // 文件：pages/WrongBook.tsx
    // 用途：错题集页（阶段 5.1 占位版本）
    // ============================================================

    import { useEffect, useState } from 'react'
    import { Card, Alert, Empty, List, Tag } from 'antd'
    import client, { extractErrorMessage } from '../api/client'
    import type { WrongQuestion } from '../types'

    export default function WrongBook() {
      const [entries, setEntries] = useState<WrongQuestion[]>([])
      const [loading, setLoading] = useState(false)
      const [error, setError] = useState<string | null>(null)

      useEffect(() => {
        const fetchEntries = async () => {
          setLoading(true)
          setError(null)
          try {
            const response = await client.get<WrongQuestion[]>('/api/user/wrong-questions')
            setEntries(response.data)
          } catch (err) {
            setError(extractErrorMessage(err))
          } finally {
            setLoading(false)
          }
        }

        fetchEntries()
      }, [])

      return (
        <div style={{ maxWidth: 900, margin: '0 auto' }}>
          <Card title="错题集（阶段 5.1 占位）">
            <Alert
              type="info"
              showIcon
              message="阶段 5.1 只验证前后端联通"
              description="错题集功能（筛选、标记掌握、重做）会在阶段 5.2 交付。"
              style={{ marginBottom: 24 }}
            />

            {error && (
              <Alert
                type="error"
                showIcon
                message="加载错题失败"
                description={error}
                style={{ marginBottom: 24 }}
              />
            )}

            {loading ? (
              <div>加载中…</div>
            ) : entries.length === 0 ? (
              <Empty description="还没有错题。答错题目后会自动收进来。" />
            ) : (
              <List
                dataSource={entries}
                renderItem={(item) => (
                  <List.Item>
                    <List.Item.Meta
                      title={item.payload?.question || `错题 #${item.id}`}
                      description={
                        <>
                          <Tag>{item.knowledge_point || '未分类'}</Tag>
                          <Tag color="red">错过 {item.wrong_count} 次</Tag>
                          <Tag color={item.mastery_status === 'mastered' ? 'green' : 'orange'}>
                            {item.mastery_status === 'mastered' ? '已掌握' : '待复习'}
                          </Tag>
                        </>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>
        </div>
      )
    }
    ''')
    print()
    print("=" * 60)
    print("完成")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())