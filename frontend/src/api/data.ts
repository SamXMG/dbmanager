// 数据 CRUD API
import { get, post, qp, request } from './client'

export interface DataResp {
  columns?: { name: string }[]
  rows?: Record<string, unknown>[]
  total?: number
  page?: number
}

export interface RowResult { ok?: boolean; error?: string; row?: Record<string, unknown> }

export const getData = (p: {
  s: string; t: string; page: number; size: number; where?: string; order?: string
}) => get<DataResp>(`/api/data?${qp({ ...p, page: String(p.page), size: String(p.size) })}`)

/** 新增行(POST); transaction/tx_id 支持事务模式 */
export const insertRow = (body: Record<string, unknown>) =>
  request<RowResult>('/api/row', { method: 'POST', body })
/** 修改行(PUT) */
export const updateRow = (body: Record<string, unknown>) =>
  request<RowResult>('/api/row', { method: 'PUT', body })
/** 删除行(DELETE) */
export const deleteRow = (body: Record<string, unknown>) =>
  request<RowResult>('/api/row', { method: 'DELETE', body })
/** 批量删除行(POST /api/rows/delete, P1-9): keys=主键值数组, 单请求删多行(替代 N 次串行 DELETE) */
export const batchDeleteRows = (body: { s: string; t: string; keys: Record<string, unknown>[] }) =>
  request<RowResult>('/api/rows/delete', { method: 'POST', body })

/** 事务提交/回滚 */
export const txCommit = (txId: string | number) =>
  post<{ ok?: boolean }>('/api/transaction/commit', { tx_id: String(txId) })
export const txRollback = (txId: string | number) =>
  post<{ ok?: boolean }>('/api/transaction/rollback', { tx_id: String(txId) })

/** 列统计: COUNT/MIN/MAX + 数值列 SUM/AVG */
export const statsColumn = (body: { s: string; t: string; col: string; where?: string }) =>
  post<{ count: number; min?: unknown; max?: unknown; sum?: unknown; avg?: unknown }>(
    '/api/stats', body)
