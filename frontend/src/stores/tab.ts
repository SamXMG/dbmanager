// 多文档标签 store(阶段 2 完整): TABS/activeId/current/currentMeta + 跨库独立会话
// 对应旧前端 tree.js 的 TABS/activateTab/flushActive/openTable 逻辑
import { defineStore } from 'pinia'
import { connect } from '@/api/connection'
import { getColumns, type Column } from '@/api/database'
import { authState } from '@/api/client'
import { useConnectionStore } from '@/stores/connection'

export interface Tab {
  id: number
  db?: string          // 所属库(跨库 tab 独立会话)
  s: string            // schema
  t: string            // 表名
  page: number
  size: number
  where: string
  filters: Record<string, unknown>
  sort: { col: string; dir: 'asc' | 'desc' } | null
  tab: 'data' | 'struct' | 'sql'
  meta: { columns: Column[] } | null
  session?: string | null  // 跨库独立会话
}

export const useTabStore = defineStore('tab', {
  state: () => ({
    tabs: [] as Tab[],
    activeId: null as number | null,
    tabSeq: 0,
    current: null as { s: string; t: string } | null,
    currentMeta: null as { columns: Column[] } | null,
    currentPage: 1,
    size: 100,
  }),
  getters: {
    activeTab: (s) => s.tabs.find(t => t.id === s.activeId) || null,
  },
  actions: {
    /** 打开表(查重含 db 维度; 同表不同库是两个 tab) */
    async openTable(s: string, t: string, db?: string) {
      const connStore = useConnectionStore()
      const curDb = db || s // 树里双击的表, db 即其所在库
      let tab = this.tabs.find(x => x.s === s && x.t === t && x.db === curDb)
      if (!tab) {
        tab = {
          id: ++this.tabSeq, db: curDb, s, t,
          page: 1, size: this.size, where: '', filters: {}, sort: null,
          tab: 'data', meta: null,
        }
        this.tabs.push(tab)
      }
      await this.activateTab(tab.id)
    },

    /** 激活标签: 切换上下文 + 跨库建独立会话 */
    async activateTab(id: number) {      if (this.activeId != null && this.activeId !== id) this.flushActive()
      this.activeId = id
      const tab = this.activeTab
      if (!tab) return
      this.current = { s: tab.s, t: tab.t }
      this.currentPage = tab.page
      this.currentMeta = tab.meta
      // 数据请求会话同步: 跨库 tab 用其独立会话, 否则回全局连接会话
      const connStore = useConnectionStore()
      authState.session = tab.session || connStore.session
      // 跨库(非连接库)且无独立会话 -> 按名直连带库建会话
      const connDb = (connStore.conn && connStore.conn.database) || ''
      if (tab.db && tab.db !== connDb && !tab.session
          && connStore.conn && connStore.conn.db_type !== 'sqlite') {
        try {
          const body: Record<string, unknown> = { database: tab.db }
          if (connStore.conn && connStore.conn.name) body.name = connStore.conn.name
          const d = await connect(body)
          tab.session = d.session
          authState.session = d.session // 该 tab 期间数据请求走它的会话
        } catch { /* 跨库失败不阻塞(数据请求会退回全局会话) */ }
      }
      // 元数据未加载 -> 拉列(阶段 3 数据网格用; 现在预热)
      if (!tab.meta) {
        try {
          tab.meta = { columns: await getColumns(tab.s, tab.t) }
          if (this.activeId === id) this.currentMeta = tab.meta
        } catch { /* 无权限等 */ }
      }
    },

    /** 关闭标签 */
    closeTab(id: number) {
      const idx = this.tabs.findIndex(t => t.id === id)
      if (idx < 0) return
      this.tabs.splice(idx, 1)
      if (this.activeId === id) {
        this.activeId = this.tabs.length ? this.tabs[Math.min(idx, this.tabs.length - 1)].id : null
        if (this.activeId != null) this.activateTab(this.activeId)
        else { this.current = null; this.currentMeta = null }
      }
    },

    /** 激活前把当前页/筛选/排序写回标签(对应旧 flushActive) */
    flushActive() {
      const tab = this.activeTab
      if (!tab) return
      tab.page = this.currentPage
      tab.size = this.size
      tab.meta = this.currentMeta
    },

    /** 切换到下一个标签(Ctrl+Tab, 对应旧 switchNextTab) */
    switchNextTab() {
      if (this.tabs.length < 2 || this.activeId == null) return
      const idx = this.tabs.findIndex(t => t.id === this.activeId)
      const next = this.tabs[(idx + 1) % this.tabs.length]
      if (next) this.activateTab(next.id)
    },
  },
})
