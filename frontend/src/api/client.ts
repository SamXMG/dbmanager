// API 客户端: 原生 fetch 封装 + 鉴权头注入 + 401 统一处理 + RSA 密码加密
// 对应旧前端 js/base.js 的 api()/rsaEncrypt()/encConn()/encBody() 逻辑

// node 环境(单测)无 window, 惰性取 origin(生产/浏览器恒为 location.origin)
export const API_BASE = typeof window !== 'undefined'
  ? window.location.origin || 'http://127.0.0.1:8770'
  : 'http://127.0.0.1:8770'

// ---- 鉴权状态(由 useAuthStore / useConnectionStore 写入) ----
export const authState = {
  session: null as string | null,        // X-Session 服务端会话
  conn: null as Record<string, unknown> | null, // X-Conn 手动连接(含明文密码)
  userToken: null as string | null,      // 预留(令牌现仅由 HttpOnly Cookie 承载, 不再用于头注入)
  gatewayToken: null as string | null,   // X-Gateway-Token 公网访问
  onUnauthorized: null as (() => void) | null, // 401 require_login 回调(弹登录)
  onMustChangePwd: null as (() => void) | null, // 403 must_change_pwd 回调(弹强制改密)
}

// ---- RSA 密码加密(从 base.js 原样搬) ----
let pubKey: string | null = null // 服务端 RSA 公钥(用于加密密码, 防 HTTP 抓包)

export function setPubKey(k: string | null) { pubKey = k }

export async function rsaEncrypt(text: string): Promise<string> {
  if (!text || !pubKey || !window.crypto || !crypto.subtle) return text // 非安全上下文/无公钥回退明文
  try {
    const b64 = pubKey
      .replace(/-----BEGIN PUBLIC KEY-----/g, '')
      .replace(/-----END PUBLIC KEY-----/g, '')
      .replace(/\s+/g, '')
    const bin = atob(b64)
    const bytes = new Uint8Array(bin.length)
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
    const key = await crypto.subtle.importKey('spki', bytes.buffer,
      { name: 'RSA-OAEP', hash: 'SHA-256' }, false, ['encrypt'])
    const enc = await crypto.subtle.encrypt({ name: 'RSA-OAEP' }, key,
      new TextEncoder().encode(text))
    let s = ''
    const out = new Uint8Array(enc)
    for (let i = 0; i < out.length; i++) s += String.fromCharCode(out[i])
    return 'rsa:' + btoa(s)
  } catch {
    return text
  }
}

// X-Conn 头: Base64 编码连接 JSON(密码先 RSA 加密)
export async function buildConnHeader(c: Record<string, unknown>): Promise<string> {
  const cc = { ...c }
  if (cc.pwd) cc.pwd = await rsaEncrypt(String(cc.pwd))
  const bytes = new TextEncoder().encode(JSON.stringify(cc))
  let bin = ''
  for (const b of bytes) bin += String.fromCharCode(b)
  return btoa(bin)
}

/** 统一鉴权头构建(P1-9 去重): 会话 > 手动连接 > 网关; 令牌仅由 HttpOnly Cookie 承载, 不再注入 X-User-Token(P0-4) */
export async function authHeaders(): Promise<Record<string, string>> {
  const h: Record<string, string> = {}
  if (authState.session) h['X-Session'] = authState.session
  else if (authState.conn) h['X-Conn'] = await buildConnHeader(authState.conn)
  if (authState.gatewayToken) h['X-Gateway-Token'] = authState.gatewayToken
  return h
}

// 请求体: 若有 pwd 字段则 RSA 加密
export async function encBody(obj: Record<string, unknown> | null): Promise<string | null> {
  if (!obj) return null
  if (typeof obj.pwd === 'string' && obj.pwd) obj.pwd = await rsaEncrypt(obj.pwd)
  return JSON.stringify(obj)
}

export function qp(obj: Record<string, string | number | undefined>): string {
  return Object.entries(obj)
    .filter(([, v]) => v !== undefined && v !== '')
    .map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(String(v)))
    .join('&')
}

// ---- 核心请求 ----
export async function request<T = any>(
  path: string,
  opts: { method?: string; body?: Record<string, unknown> | string | null;
          headers?: Record<string, string>; raw?: boolean } = {},
): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers || {}) }
  if (opts.body && typeof opts.body === 'object' && !(opts.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }
  // 鉴权头注入(优先级: 会话 > 手动连接; 登录/公钥接口不注入) — 复用 authHeaders() 单点
  const skipAuth = path.includes('/api/login') || path.includes('/api/pubkey')
  if (!skipAuth) Object.assign(headers, await authHeaders())
  let body: BodyInit | null = null
  if (opts.body) {
    body = typeof opts.body === 'string'
      ? opts.body
      : (await encBody(opts.body as Record<string, unknown>)) as string
  }
  const r = await fetch(API_BASE + path, {
    method: opts.method || (body ? 'POST' : 'GET'),
    headers,
    body,
  })
  // 401 统一处理(孤儿 token / 未登录)
  if (r.status === 401) {
    const d = await r.json().catch(() => ({}))
    if (d.require_login && authState.onUnauthorized) {
      authState.userToken = null
      authState.onUnauthorized()
    }
    if (d.require_gateway) throw new Error(d.error || '需要公网访问验证')
    throw new Error(d.error || '请先登录')
  }
  // 403 统一处理: 强制改密拦截——业务操作被服务端 403 时弹改密窗
  if (r.status === 403) {
    const d = await r.json().catch(() => ({}))
    if (d.must_change_pwd && authState.onMustChangePwd) {
      authState.onMustChangePwd()
      throw new Error(d.error || '请先修改默认密码')
    }
    throw new Error(d.error || '无权限执行该操作')
  }
  const d = await r.json().catch(() => ({}))
  // P0-5: 4xx/5xx 一律 reject(原先 500 无 error 字段时静默当成功返回 {}, 掩盖服务端故障)
  if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status))
  return d as T
}

export const get = <T = any>(p: string) => request<T>(p, { method: 'GET' })
export const post = <T = any>(p: string, body?: Record<string, unknown>) =>
  request<T>(p, { method: 'POST', body })
