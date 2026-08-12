// 连接 store: API/CONN/SESSION/PUB_KEY/CONN_LIST/DEFAULT_CONN(阶段 1 完整实现)
import { defineStore } from 'pinia'
import { getConfig, getPubKey, connect, listConnections, deleteConnection, listDatabases, type ConnMeta, type ConnectResp } from '@/api/connection'
import { authState, setPubKey } from '@/api/client'

export const useConnectionStore = defineStore('connection', {
  state: () => ({
    conn: null as ConnMeta | null,
    session: null as string | null,
    pubKey: null as string | null,
    connList: [] as ConnMeta[],
    defaultConn: null as string | null,
    // node 环境(单测)无 window, 惰性取 origin
    apiBase: (typeof window !== 'undefined' ? window.location.origin : '') || 'http://127.0.0.1:8770',
    tables: [] as { schema?: string; name: string; type?: string }[],
    connected: false,
    databases: [] as string[],
    registerEnabled: false,
    authRequired: false,
    gatewayRequired: false,
  }),

  actions: {
    /** 初始化配置: 获取 api_base/网关状态/认证状态 + RSA 公钥 */
    async initConfig() {
      try {
        const cfg = await getConfig()
        if (cfg.api_base) this.apiBase = cfg.api_base
        // 用户保存的连接优先(saved_connections); connections 是 Navicat 自动发现(可能为空)
        if (cfg.saved_connections !== undefined) this.connList = cfg.saved_connections
        else if (cfg.connections !== undefined) this.connList = cfg.connections
        if (cfg.default_conn) this.defaultConn = cfg.default_conn
        if (cfg.register_enabled !== undefined) this.registerEnabled = !!cfg.register_enabled
        if (cfg.auth_required !== undefined) this.authRequired = !!cfg.auth_required
        if (cfg.gateway_required !== undefined) this.gatewayRequired = !!cfg.gateway_required
      } catch { /* 网关未验证时 getConfig 401, 前端弹网关弹窗 */ }
      try {
        const pk = await getPubKey()
        if (pk.pubkey) { this.pubKey = pk.pubkey; setPubKey(pk.pubkey) }
      } catch { /* pubKey 非关键路径 */ }
    },

    /** 建立连接(按名直连或手动) */
    async connectAndGo(body: Record<string, unknown>): Promise<ConnectResp> {
      const r = await connect(body)
      this.conn = r.connection
      this.session = r.session
      this.tables = r.tables || []
      this.connected = true
      // 同步到 client.ts 鉴权状态
      authState.session = r.session
      authState.conn = null
      // 拉取所有数据库(树显示全部库; MSSQL 多库/MySQL 单库)
      try {
        this.databases = await listDatabases({})
      } catch {
        this.databases = []
      }
      return r
    },

    /** 断开连接 */
    disconnect() {
      this.conn = null
      this.session = null
      this.tables = []
      this.connected = false
      authState.session = null
      authState.conn = null
    },

    /** 刷新已保存连接列表 */
    async refreshConnList() {
      try { this.connList = await listConnections() } catch { /* 未登录时 401 */ }
    },

    /** 删除已保存连接 */
    async deleteConn(name: string) {
      await deleteConnection(name)
      this.connList = this.connList.filter(c => c.name !== name)
    },
  },
})