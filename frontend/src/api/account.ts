// 账号体系 API(登录/注册/改密/账号管理/网关/权限/在线会话/系统查询)
import { get, post, qp } from './client'

export interface LoginResp { ok?: boolean; token?: string; user?: string; role?: string; must_change_pwd?: boolean }
export interface UserInfo { username: string; role: string; status?: string }

/** 连接级权限: read/write 读写开关; tables 白名单(空=全部); deny_tables 黑名单 */
export interface ConnPerm { read: boolean; write: boolean; tables?: string[]; deny_tables?: string[] }

/** 在线会话(按用户聚合): 登录时间/IP/最后活跃/当前操作均为 Unix 秒 */
export interface SessionInfo {
  user: string; role: string; login_time: number; ip: string
  last_active: number; last_path?: string; sessions: number
}

export const login = (username: string, password: string) =>
  post<LoginResp>('/api/login', { username, password })
export const register = (username: string, password: string) =>
  post<{ ok?: boolean; message?: string }>('/api/register', { username, password })
export const changePwd = (old_pwd: string, new_pwd: string) =>
  post<{ ok?: boolean; message?: string }>('/api/password', { old_password: old_pwd, new_password: new_pwd })

export const listUsers = () => get<{ users: UserInfo[] }>('/api/users')
export const saveUser = (body: Record<string, unknown>) => post('/api/users', body)
export const deleteUser = (username: string) => post('/api/users/delete', { username })
export const approveUser = (username: string, role: string, action: 'approve' | 'reject') =>
  post('/api/users/approve', { username, role, action })

// 细粒度权限(连接/表级读写): 仅 admin
export const getUserPerms = (username: string) =>
  get<{ perms: Record<string, ConnPerm>; connections: string[] }>(
    '/api/users/perms?username=' + encodeURIComponent(username))
export const saveUserPerms = (usernames: string[], perms: Record<string, ConnPerm>) =>
  post<{ ok?: boolean; message?: string }>('/api/users/perms', { usernames, perms })
export const fetchConnTables = (name: string) =>
  post<{ tables?: string[]; ok?: boolean; error?: string }>('/api/conn/tables', { name })

// 在线用户管理: 仅 admin
export const listSessions = () => get<{ sessions: SessionInfo[] }>('/api/sessions')
export const kickSession = (username: string) =>
  post<{ ok?: boolean; message?: string }>('/api/sessions/kick', { username })

// 系统数据查询(内置 SQLite 只读 SELECT)与审计查询: 仅 admin
export const sysQuery = (sql: string) =>
  post<{ rows?: Record<string, unknown>[] }>('/api/sysdb', { sql })
export const auditQuery = (params: { user?: string; action?: string; limit?: number }) =>
  get<{ rows?: Record<string, unknown>[] }>(
    '/api/audit?' + qp(params as Record<string, string | number | undefined>))

export const gatewayLogin = (token: string) => post('/api/gateway/login', { token })
export const gatewayStatus = () => get<{ ok?: boolean }>('/api/gateway/status')

// 服务器配置(dbmanager.conf): 仅 admin; GET 读 / POST 写, 敏感键掩码
// apply: restart=需重启生效(host/port/ssl), instant=保存即生效
export interface ConfigItem { value: string; masked: boolean; default: string; env: string; apply: 'restart' | 'instant' }
export interface ConfigSections { [section: string]: { [key: string]: ConfigItem } }
export const getConfigSettings = () =>
  get<{ sections: ConfigSections; config_file: string }>('/api/config/settings')
export const saveConfigSettings = (sections: ConfigSections) =>
  post<{ ok?: boolean; message?: string; restart_required?: boolean; restart_keys?: string[] }>(
    '/api/config/settings', { sections })
export const restartServer = () =>
  post<{ ok?: boolean; message?: string }>('/api/config/restart')
