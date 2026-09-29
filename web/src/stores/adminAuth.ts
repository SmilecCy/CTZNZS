// ============================================================
// 文件：stores/adminAuth.ts
// 用途：管理员登录状态（与学生分开管理）
// ============================================================

import { create } from 'zustand'
import type { User } from '../types'

const TOKEN_KEY = 'admin_access_token'
const USER_KEY = 'admin_user'

// ============================================================
// 从 localStorage 同步恢复
// ============================================================
function loadInitialState(): {
  user: User | null
  token: string | null
  isAuthenticated: boolean
} {
  try {
    const token = localStorage.getItem(TOKEN_KEY)
    const userJson = localStorage.getItem(USER_KEY)

    if (!token || !userJson) {
      return { user: null, token: null, isAuthenticated: false }
    }

    const user = JSON.parse(userJson) as User
    return { user, token, isAuthenticated: true }
  } catch {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    return { user: null, token: null, isAuthenticated: false }
  }
}

const initialState = loadInitialState()

// ============================================================
// 与后端交互的 API
// ============================================================
async function loginRequest(username: string, password: string): Promise<{
  access_token: string
  user: User
}> {
  const response = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, role: 'admin' }),
  })

  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    const msg = data?.detail?.message || data?.detail || `登录失败（${response.status}）`
    throw new Error(typeof msg === 'string' ? msg : '登录失败')
  }

  return response.json()
}

async function logoutRequest(token: string): Promise<void> {
  try {
    await fetch('/api/auth/logout', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
    })
  } catch {
    // 忽略
  }
}

// ============================================================
// State 定义
// ============================================================
interface AdminAuthState {
  user: User | null
  token: string | null
  isAuthenticated: boolean

  login: (username: string, password: string) => Promise<User>
  logout: () => Promise<void>
  loadFromStorage: () => void
}

// ============================================================
// Store
// ============================================================
export const useAdminAuthStore = create<AdminAuthState>((set, get) => ({
  // 初始状态直接来自 localStorage
  user: initialState.user,
  token: initialState.token,
  isAuthenticated: initialState.isAuthenticated,

  login: async (username, password) => {
    const result = await loginRequest(username, password)

    localStorage.setItem(TOKEN_KEY, result.access_token)
    localStorage.setItem(USER_KEY, JSON.stringify(result.user))

    set({
      user: result.user,
      token: result.access_token,
      isAuthenticated: true,
    })

    return result.user
  },

  logout: async () => {
    const token = get().token
    if (token) {
      await logoutRequest(token)
    }

    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)

    set({
      user: null,
      token: null,
      isAuthenticated: false,
    })
  },

  loadFromStorage: () => {
    const state = loadInitialState()
    set(state)
  },
}))