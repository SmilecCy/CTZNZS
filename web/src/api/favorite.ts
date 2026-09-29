// ============================================================
// 文件：api/favorite.ts
// 用途：收藏 API 调用
// ============================================================

import client from './client'
import type { FavoriteItem, SuccessResponse } from '../types'

export async function addFavorite(questionId: number): Promise<SuccessResponse> {
  const response = await client.post<SuccessResponse>(
    `/api/user/favorites/${questionId}`,
  )
  return response.data
}

export async function removeFavorite(questionId: number): Promise<SuccessResponse> {
  const response = await client.delete<SuccessResponse>(
    `/api/user/favorites/${questionId}`,
  )
  return response.data
}

export async function listFavorites(): Promise<FavoriteItem[]> {
  const response = await client.get<FavoriteItem[]>('/api/user/favorites')
  return response.data
}