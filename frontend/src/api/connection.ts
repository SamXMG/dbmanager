// 连接/配置 API(契约见迁移方案第五章)
import { get, post } from './client'

export interface ConnMeta {
  name?: string
  db_type?: string
  server?: string
  port?: number | string
  database?: string
  uid?: string
  has_pwd?: boolean
  visible_to?: string[]
  mode?: string
}

export interface ConnectResp {
  ok: boolean
  session: string
  connection: ConnMeta
  tables: { schema?: string; name: string; type?: string }[]
}

export interface ConfigResp {
  api_base?: string
  auth_required?: boolean
  auth_user?: string | null
  auth_role?: string | null
  register_enabled?: boolean
  gateway_required?: boolean
  default_conn?: string | null
  connections?: ConnMeta[]
  saved_connections?: ConnMeta[]
}

export const getConfig = () => get<ConfigResp>('/api/config')
export const getPubKey = () => get<{ pubkey?: string }>('/api/pubkey')

/** 建立连接: 按名直连({name}) 或 手动连接(完整连接对象) */
export const connect = (body: Record<string, unknown>) =>
  post<ConnectResp>('/api/connect', body)

/** 测试连接(不建立会话) */
export const testConn = (body: Record<string, unknown>) =>
  post<{ ok: boolean; message?: string; error?: string }>('/api/test', body)

export const listDatabases = (body: Record<string, unknown> = {}) =>
  post<string[]>('/api/databases', body)

export const shutdown = () => post('/api/shutdown')

// ---- 连接管理(账号体系下需登录; 设置 visible_to/mode 需 admin) ----
export const listConnections = () => get<ConnMeta[]>('/api/connections')
export const saveConnection = (body: Record<string, unknown>) =>
  post<{ ok: boolean; connection?: ConnMeta }>('/api/connections', body)
export const deleteConnection = (name: string) =>
  post<{ ok: boolean }>('/api/connections/delete', { name })
