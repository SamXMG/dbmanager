// SQL 工作台 API(阶段 4): 执行/解释 + 结果导出(xlsx 走后端 blob)
import { post, authHeaders, API_BASE } from './client'

/** 归一化执行计划节点(后端 PG/MySQL 统一结构, 前端树渲染) */
export interface PlanNode {
  operation: string
  object?: string | null
  rows_est?: number | null
  rows_actual?: number | null
  cost_est?: number | null
  time_actual_ms?: number | null
  loops?: number | null
  buffers?: string | null
  filter?: string | null
  detail?: string | null
  children?: PlanNode[]
}

export interface SqlResult {
  sql?: string
  columns?: { name: string }[]
  rows?: Record<string, unknown>[]
  total?: number
  truncated?: boolean
  affected?: number
  ok?: boolean
  readonly?: boolean
  error?: string
  message?: string
  /** 执行计划返回形态: tree(归一化 plan)/ table(多列)/ text(单列) */
  mode?: string
  /** mode=tree 时的归一化计划树 */
  plan?: PlanNode | null
  /** mode=tree 时的方言标识(postgresql / mysql) */
  dialect?: string
  /** 多语句批量执行时返回(results 数组, 每语句一个结果) */
  results?: SqlResult[]
}

/** 执行 SQL; write=true 写模式(只读账号/只读连接会被后端 403) */
export const runSql = (body: { sql: string; limit?: number; write?: boolean; database?: string }) =>
  post<SqlResult>('/api/sql', body)

export const explainQuery = (body: { sql: string; database?: string }) =>
  post<SqlResult & { mode?: string }>('/api/explain', body)

/** 导出查询结果 Excel: 后端 /api/export/sql 生成 xlsx 并触发下载(复用会话鉴权头) */
export async function exportSqlXlsx(
  columns: { name: string }[],
  rows: Record<string, unknown>[],
  filename = 'query_result.xlsx',
): Promise<void> {
  // P1-9 去重: 统一走 client.authHeaders()
  const headers: Record<string, string> = { 'Content-Type': 'application/json', ...(await authHeaders()) }
  const r = await fetch(API_BASE + '/api/export/sql', {
    method: 'POST', headers,
    body: JSON.stringify({ columns, rows }),
  })
  if (!r.ok) {
    const d = await r.json().catch(() => ({}))
    throw new Error(d.error || '导出失败')
  }
  const blob = await r.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(a.href)
}
