// ============================================================
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
    