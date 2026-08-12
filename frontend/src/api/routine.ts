// 存储过程/函数/触发器 API
import { post } from './client'

export const saveRoutine = (body: Record<string, unknown>) =>
  post<{ ok?: boolean }>('/api/routine/save', body)
export const dropRoutine = (body: Record<string, unknown>) =>
  post<{ ok?: boolean }>('/api/routine/drop', body)
export const executeRoutine = (body: Record<string, unknown>) =>
  post<{ ok?: boolean; rows?: Record<string, unknown>[]; columns?: { name: string }[] }>(
    '/api/routine/execute', body)

// ---- 事务 ----
export const txCommit = (txId: string | number) =>
  post<{ ok?: boolean }>('/api/transaction/commit', { tx_id: txId })
export const txRollback = (txId: string | number) =>
  post<{ ok?: boolean }>('/api/transaction/rollback', { tx_id: txId })
