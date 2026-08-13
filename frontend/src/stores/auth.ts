// 账号 store(P0-4 加固: 令牌仅由后端 HttpOnly Cookie(dbm_user)承载, 前端不再持有/注入 X-User-Token;
// 刷新后登录态经 /api/config 的 auth_user 恢复; 彻底杜绝 XSS 通过 JS 读取/重放令牌)
import { defineStore } from 'pinia'
import { errMsg } from '@/utils/err'
import { login, register, changePwd, gatewayLogin } from '@/api/account'
import { authState, request } from '@/api/client'

export const useAuthStore = defineStore('auth', {
  state: () => {
    // 不读 localStorage: 令牌持久化是 XSS 窃取面, 已改 HttpOnly Cookie(见 /api/login Set-Cookie)
    return {
      token: null as string | null,
      role: null as 'read' | 'write' | 'admin' | null,
      name: '',
      mustChangePwd: false,   // 默认账号未改密 → 强制改密模式
    }
  },

  getters: {
    isLoggedIn: (s) => !!s.role,   // 刷新后 token 为空但 role 由 /api/config 恢复(Cookie 自动鉴权)
    canWrite: (s) => s.role === 'write' || s.role === 'admin',
    isAdmin: (s) => s.role === 'admin',
    roleLabel: (s) => {
      const map: Record<string, string> = { read: '只读', write: '读写', admin: '管理' }
      return map[s.role || ''] || ''
    },
  },

  actions: {
    /** 登录: 返回 true 成功 / false 失败(含 429 锁定)。令牌仅内存持有(请求头注入), Cookie 由后端 Set 自动携带 */
    async doLogin(username: string, password: string): Promise<{ ok: boolean; error?: string }> {
      try {
        const r = await login(username, password)
        if (r.ok && r.token) {
          this.token = r.token; this.role = r.role as 'read' | 'write' | 'admin'; this.name = r.user || username
          this.mustChangePwd = !!r.must_change_pwd   // 默认账号 → 强制改密
          // 令牌仅由后端 HttpOnly Cookie(dbm_user)承载, 前端不再持有/注入令牌(P0-4: 杜绝 XSS 窃取)
          return { ok: true }
        }
        return { ok: false, error: '登录失败' }
      } catch (e: unknown) {
        return { ok: false, error: errMsg(e, '登录失败') }
      }
    },

    /** 刷新/首载后恢复登录态: 经 /api/config(auth_user/auth_role)恢复角色, 不依赖任何持久化令牌 */
    async restore(): Promise<void> {
      try {
        const cfg = await request<{ auth_user?: string | null; auth_role?: string | null; must_change_pwd?: boolean }>('/api/config')
        if (cfg.auth_user) {
          this.role = (cfg.auth_role || 'read') as 'read' | 'write' | 'admin'
          this.name = cfg.auth_user
          this.mustChangePwd = !!cfg.must_change_pwd
        } else {
          this.role = null; this.name = ''; this.mustChangePwd = false
        }
        this.token = null   // 令牌始终不持久化: 浏览器会话走 HttpOnly Cookie
        authState.userToken = null
      } catch { /* 未登录/网络错误: 保持空态 */ }
    },

    /** 注册(返回后端提示, 如"等待管理员审批") */
    async doRegister(username: string, password: string) {
      try {
        const r = await register(username, password)
        return { ok: true, message: r.message }
      } catch (e: unknown) {
        return { ok: false, error: errMsg(e, '注册失败') }
      }
    },

    /** 改密 */
    async doChangePwd(oldPwd: string, newPwd: string) {
      try {
        await changePwd(oldPwd, newPwd)
        this.mustChangePwd = false   // 强制改密完成
        return { ok: true, message: '密码已更新' }
      } catch (e: unknown) {
        return { ok: false, error: errMsg(e, '改密失败') }
      }
    },

    /** 网关验证 */
    async doGatewayLogin(token: string) {
      try {
        await gatewayLogin(token)
        authState.gatewayToken = token
        return { ok: true }
      } catch (e: unknown) {
        return { ok: false, error: errMsg(e, '网关令牌错误') }
      }
    },

    /** 登出: 清内存令牌 + 调 /api/logout 删服务端会话并清 HttpOnly Cookie */
    async logout() {
      this.token = null; this.role = null; this.name = ''; this.mustChangePwd = false
      authState.userToken = null
      try { await request('/api/logout', { method: 'POST', body: {} }) } catch { /* 服务不可达也照常清本地 */ }
    },

    /** 设置 401 回调(弹登录弹窗) */
    setUnauthorizedHandler(fn: () => void) {
      authState.onUnauthorized = fn
    },

    /** 设置强制改密回调(业务请求被 403 must_change_pwd 拦截时弹改密窗) */
    setMustChangeHandler(fn: () => void) {
      authState.onMustChangePwd = fn
    },
  },
})