// 结构变更/同步/数据迁移 API
import { post, request } from './client'

/** 表结构变更(字段/索引), action: add_column/modify_column/drop_column/add_index/drop_index */
export const alterTable = (body: { s: string; t: string; action: string; payload: Record<string, unknown> }) =>
  post<{ ok?: boolean; ddl?: string[] }>('/api/alter', body)

/** 结构同步(建表/对齐) */
export const syncTable = (body: Record<string, unknown>) => post('/api/sync', body)

/** 数据级同步: 源表 -> 目标表(跨库) */
export const transferData = (body: Record<string, unknown>) =>
  post<{ transferred?: number }>('/api/transfer', body)

/** 测试数据生成器 */
export const genData = (body: { s: string; t: string; rows: number }) =>
  post<{ inserted?: number }>('/api/gen-data', body)

export const schemaDiff = (body: Record<string, unknown>) => post('/api/schema/diff', body)
export const schemaSync = (body: Record<string, unknown>) => post('/api/schema/sync', body)

// ---- 导入导出 ----
export const exportCsv = (p: { s: string; t: string; where?: string; fmt?: string }) =>
  request(`/api/export?${new URLSearchParams(p as Record<string, string>).toString()}`, { method: 'GET' })

export const exportSchema = () => request('/api/export/schema', { method: 'GET' })
export const exportSql = (body: Record<string, unknown>) => post('/api/export/sql', body)
export const importData = (body: Record<string, unknown>) => post('/api/import', body)
export const importXlsx = (body: Record<string, unknown>) => post('/api/import/xlsx', body)
export const backup = () => request('/api/backup', { method: 'GET' })
export const restore = (body: Record<string, unknown>) => post('/api/restore', body)
