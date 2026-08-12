// 表结构/元数据 API
import { get, post, qp } from './client'

export interface Column {
  name: string
  type?: string
  nullable?: boolean
  default?: unknown
  is_pk?: boolean
  identity?: boolean
}

export interface TableInfo { schema?: string; name: string; type?: string }

export const listTables = (body: Record<string, unknown> = {}) =>
  post<TableInfo[]>('/api/tables', body)

export const getColumns = (s: string, t: string) =>
  get<Column[]>(`/api/columns?${qp({ s, t })}`)

export const getIndexes = (s: string, t: string) =>
  get<{ name?: string; columns?: string; is_unique?: boolean }[]>(
    `/api/indexes?${qp({ s, t })}`)

export const getRelations = (s: string, t: string) =>
  get(`/api/relations?${qp({ s, t })}`)

export const getEr = (s: string, t: string) =>
  get(`/api/er?${qp({ s, t })}`)

/** Navicat 风格树: 按库取该库的表/视图/存储过程/函数/触发器 */
export const getObjects = (database: string) =>
  post<{ tables: TableInfo[]; routines: RoutineInfo[] }>('/api/objects', { database })

export interface RoutineInfo { schema?: string; name: string; type: string }

export const listRoutines = () => get<RoutineInfo[]>('/api/routines')
export const getRoutineSource = (s: string, name: string, kind: string) =>
  get(`/api/routine/source?${qp({ s, name, kind })}`)
export const getRoutineParams = (s: string, name: string, kind: string) =>
  get(`/api/routine/params?${qp({ s, name, kind })}`)
