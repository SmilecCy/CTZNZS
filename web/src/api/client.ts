// ============================================================
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
    