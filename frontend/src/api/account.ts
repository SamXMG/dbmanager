// 账号体系 API(登录/注册/改密/账号管理/网关)
import { get, post } from './client'

export interface LoginResp { ok?: boolean; token?: string; user?: string; role?: string; must_change_pwd?: boolean }
export interface UserInfo { username: string; role: string }

export const login = (username: string, password: string) =>
  post<LoginResp>('/api/login', { username, password })
export const register = (username: string, password: string) =>
  post<{ ok?: boolean; message?: string }>('/api/register', { username, password })
export const changePwd = (old_pwd: string, new_pwd: string) =>
  post<{ ok?: boolean; message?: string }>('/api/password', { old_pwd, new_pwd })

export const listUsers = () => get<{ users: UserInfo[] }>('/api/users')
export const saveUser = (body: Record<string, unknown>) => post('/api/users', body)
export const deleteUser = (username: string) => post('/api/users/delete', { username })

export const gatewayLogin = (token: string) => post('/api/gateway/login', { token })
export const gatewayStatus = () => get<{ ok?: boolean }>('/api/gateway/status')
