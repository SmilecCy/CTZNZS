// ============================================================
// 文件：api/note.ts
// 用途：笔记 API 调用
// ============================================================

import client from './client'
import type { NoteItem, SuccessResponse } from '../types'

export async function saveNote(questionId: number, content: string): Promise<SuccessResponse> {
  const response = await client.post<SuccessResponse>(
    `/api/user/notes/${questionId}`,
    { content },
  )
  return response.data
}

export async function getNote(questionId: number): Promise<NoteItem> {
  const response = await client.get<NoteItem>(`/api/user/notes/${questionId}`)
  return response.data
}