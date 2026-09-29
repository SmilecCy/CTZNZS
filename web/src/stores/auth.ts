import { create } from 'zustand'
import type { User } from '../types'
import * as authApi from '../api/auth'

const TOKEN_KEY = 'access_token'
const USER_KEY = 'user'

// ============================================================
// 从 localStorage 同步恢复登录状态
// ============================================================
// 【为什么在 create 时同步执行】
//   如果放在 useEffect 里，首次渲染时 isAuthenticated 还是 false，
//   RequireAuth 会立刻跳转到 /login，用户刷新后就被踢出去了。
//
//   在 create 时同步读 localStorage，首次渲染就能拿到正确状态。
function loadInitialState(): { user: User | null; isAuthenticated: boolean } {
  try {
    const token = localStorage.getItem(TOKEN_KEY)
    const userJson = localStorage.getItem(USER_KEY)

    if (!token || !userJson) {
      return { user: null, isAuthenticated: false }
    }

    const user = JSON.parse(userJson) as User
    return { user, isAuthenticated: true }
  } catch {
    // JSON 解析失败（数据损坏），清掉
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    return { user: null, isAuthenticated: false }
  }
}

// 首次加载时同步读一次
const initialState = loadInitialState()

interface AuthState {
  user: User | null
  isAuthenticated: boolean

  login: (username: string, password: string, role?: 'user' | 'admin') => Promise<User>
  register: (username: string, password: string, displayName?: string) => Promise<User>
  logout: () => Promise<void>
  loadFromStorage: () => void   // 保留，兼容外部调用
}

export const useAuthStore = create<AuthState>((set) => ({
  // 初始状态直接来自 localStorage
  user: initialState.user,
  isAuthenticated: initialState.isAuthenticated,

  login: async (username, password, role = 'user') => {
    const result = await authApi.login({ username, password, role })

    localStorage.setItem(TOKEN_KEY, result.access_token)
    localStorage.setItem(USER_KEY, JSON.stringify(result.user))

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

    localStorage.setItem(TOKEN_KEY, result.access_token)
    localStorage.setItem(USER_KEY, JSON.stringify(result.user))

    set({
      user: result.user,
      isAuthenticated: true,
    })

    return result.user
  },

  logout: async () => {
    await authApi.logout()

    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)

    set({
      user: null,
      isAuthenticated: false,
    })
  },

  // 【保留这个方法的兼容性】
  //   虽然现在初始状态已经同步加载了，但外部代码可能还在调 loadFromStorage。
  //   保留它，让调用不出错。
  loadFromStorage: () => {
    const state = loadInitialState()
    set(state)
  },
}))