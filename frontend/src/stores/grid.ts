// 网格 store(阶段 3 完整): 分页数据/排序/筛选/行选中/单元格编辑
// 对应旧前端 js/grid.js 的全局状态与操作; 阶段5补全: 事务传递/列类型/批量粘贴
import { defineStore } from 'pinia'
import { getData, insertRow, updateRow, batchDeleteRows, type DataResp } from '@/api/data'
import { useTabStore } from '@/stores/tab'
import { useConnectionStore } from '@/stores/connection'
import { useUIStore } from '@/stores/ui'

export interface GridFilter { op: string; val: string }

/** 网格列(含类型/主键, 供类型着色) */
export interface GridColumn {
  name: string
  type?: string
  nullable?: boolean
  is_pk?: boolean
}

/** 单个 tab 的网格状态快照(真 tab 体验: 切走保存、切回立即恢复, 不重新请求) */
export interface GridSnapshot {
  columns: GridColumn[]
  rows: Record<string, unknown>[]
  total: number
  page: number
  pageSize: number
  sort: { col: string; dir: 'asc' | 'desc' } | null
  filters: Record<string, GridFilter>
}

// P1-9: 方言列引用统一收口到 utils/sqlIdent.ts(原本地定义删除, 防三处方言规则漂移)
import { quoteIdent } from '@/utils/sqlIdent'
export { quoteIdent }

export function quoteSql(v: string): string { return "'" + String(v).replace(/'/g, "''") + "'" }

export const useGridStore = defineStore('grid', {
  state: () => ({
    columns: [] as GridColumn[],
    rows: [] as Record<string, unknown>[],
    total: 0,
    page: 1,
    pageSize: 100,
    loading: false,
    sort: null as { col: string; dir: 'asc' | 'desc' } | null,
    filters: {} as Record<string, GridFilter>,
    selectedRows: new Set<number>(),
    lastSelIdx: -1,
    editingCell: null as { r: number; c: number } | null,
    currentTab: 'data' as 'data' | 'struct' | 'sql',
    /** 按 tab id 的网格快照(切换 tab 即时恢复, 关闭清理) */
    snapshots: {} as Record<number, GridSnapshot>,
  }),
  getters: {
    selectedCount: (s) => s.selectedRows.size,
  },
  actions: {
    /** 当前表上下文(从 tab store 取) */
    _cur() {
      const tab = useTabStore().current
      return tab ? { s: tab.s, t: tab.t } : null
    },

    /** 持久化 key(表维度, 对齐旧 tabStateKey): 排序/筛选跨会话记忆 */
    _stateKey(): string {
      const conn = useConnectionStore().conn
      const cur = useTabStore().current
      if (!cur) return ''
      return 'dbm_tabstate|' + (conn?.db_type || '') + '|' + (conn?.server || '') + '|' +
        (conn?.database || '') + '|' + cur.s + '|' + cur.t
    },
    _restorePersisted() {
      const key = this._stateKey()
      if (!key) return
      try {
        const d = JSON.parse(localStorage.getItem(key) || 'null') as
          { sort?: { col: string; dir: 'asc' | 'desc' } | null; filters?: Record<string, GridFilter>; pageSize?: number } | null
        if (d) {
          this.sort = d.sort || null
          this.filters = d.filters || {}
          if (d.pageSize) this.pageSize = d.pageSize
        }
      } catch { /* */ }
    },
    _savePersisted() {
      const key = this._stateKey()
      if (!key) return
      try {
        localStorage.setItem(key, JSON.stringify({
          sort: this.sort, filters: this.filters, pageSize: this.pageSize,
        }))
      } catch { /* */ }
    },

    /** 事务参数(对齐旧 txObj): 事务模式开启时按当前 tab 建独立事务 */
    _txPayload(): Record<string, unknown> {
      if (!useUIStore().transactionMode) return {}
      const tabStore = useTabStore()
      return { transaction: true, tx_id: String(tabStore.activeId ?? 0) }
    },

    /** 组合筛选 WHERE(对齐旧 buildFilterClause: 方言列引用 + eq/ne/gt/ge/lt/le/contains/starts/ends/isnull) */
    buildWhere(): string {
      const dbType = useConnectionStore().conn?.db_type || 'mssql'
      const parts: string[] = []
      for (const [col, f] of Object.entries(this.filters)) {
        if (!f || !f.op) continue
        const qcol = quoteIdent(dbType, col)
        const val = String(f.val ?? '')
        switch (f.op) {
          case 'isnull': parts.push(`${qcol} IS NULL`); break
          case 'isnotnull': parts.push(`${qcol} IS NOT NULL`); break
          case 'contains': parts.push(`${qcol} LIKE ${quoteSql('%' + val + '%')}`); break
          case 'starts': parts.push(`${qcol} LIKE ${quoteSql(val + '%')}`); break
          case 'ends': parts.push(`${qcol} LIKE ${quoteSql('%' + val)}`); break
          case 'eq': parts.push(`${qcol} = ${quoteSql(val)}`); break
          case 'ne': parts.push(`${qcol} <> ${quoteSql(val)}`); break
          case 'gt': parts.push(`${qcol} > ${quoteSql(val)}`); break
          case 'ge': parts.push(`${qcol} >= ${quoteSql(val)}`); break
          case 'lt': parts.push(`${qcol} < ${quoteSql(val)}`); break
          case 'le': parts.push(`${qcol} <= ${quoteSql(val)}`); break
        }
      }
      return parts.join(' AND ')
    },

    /** 组合排序(对齐旧前端: col:dir, 如 salary:desc) */
    buildOrder(): string {
      if (!this.sort) return ''
      return this.sort.col + ':' + this.sort.dir
    },

    /** 加载当前表数据(旧 loadData); 首次打开恢复持久化排序/筛选, 成功后保存 */
    async loadData(page?: number, size?: number) {
      const cur = this._cur()
      if (!cur) return
      const tabStore = useTabStore()
      const p = page ?? this.page
      const sz = size ?? this.pageSize
      // 无快照的首次加载: 恢复持久化状态(排序/筛选)
      const isFirst = !this.snapshots[tabStore.activeId ?? -1]
      if (isFirst && p === 1 && !page && !size) this._restorePersisted()
      this.loading = true
      try {
        const d: DataResp = await getData({
          s: cur.s, t: cur.t, page: p, size: sz,
          where: this.buildWhere(), order: this.buildOrder(),
        })
        this.columns = d.columns || []
        this.rows = d.rows || []
        this.total = d.total ?? 0
        this.page = p
        this.pageSize = sz
        tabStore.currentPage = p
        this.selectedRows = new Set()
        this._savePersisted()
      } finally {
        this.loading = false
      }
    },

    /** 点击列头排序: 无->asc->desc->无 循环 */
    setSort(col: string) {
      if (this.sort && this.sort.col === col) {
        this.sort = this.sort.dir === 'asc'
          ? { col, dir: 'desc' }
          : null
      } else {
        this.sort = { col, dir: 'asc' }
      }
      this.loadData(1)
    },

    /** 设置列筛选(空值移除) */
    setFilter(col: string, op: string, val: string) {
      if (!val) delete this.filters[col]
      else this.filters[col] = { op, val }
      this.loadData(1)
    },

    /** 单行选中(ctrl=加选, shift=范围) */
    selectRow(idx: number, additive = false, range = false) {
      if (range && this.lastSelIdx >= 0) {
        const [a, b] = [Math.min(this.lastSelIdx, idx), Math.max(this.lastSelIdx, idx)]
        if (!additive) this.selectedRows = new Set()
        for (let i = a; i <= b; i++) this.selectedRows.add(i)
      } else if (additive) {
        this.selectedRows.has(idx) ? this.selectedRows.delete(idx) : this.selectedRows.add(idx)
      } else {
        this.selectedRows = new Set([idx])
      }
      this.lastSelIdx = idx
    },

    /** 单元格编辑 */
    startEdit(r: number, c: number) { this.editingCell = { r, c } },
    cancelEdit() { this.editingCell = null },

    /** 提交单元格修改(PUT /api/row) */
    async commitEdit(value: unknown): Promise<boolean> {
      const cell = this.editingCell
      const cur = this._cur()
      if (!cell || !cur) return false
      const row = this.rows[cell.r]
      const col = this.columns[cell.c]
      if (!row || !col) return false
      try {
        const payload: Record<string, unknown> = {
          s: cur.s, t: cur.t,
          key: this._pkValues(row),  // 主键定位行
          values: { [col.name]: value },
          ...this._txPayload(),
        }
        await updateRow(payload)
        this.editingCell = null
        await this.loadData()
        return true
      } catch {
        return false
      }
    },

    /** 单元格置空(PUT values {col: null}; 旧版 setCellNull, 仅可空列) */
    async setCellNull(r: number, c: number): Promise<boolean> {
      const cur = this._cur()
      const row = this.rows[r]
      const col = this.columns[c]
      if (!cur || !row || !col) return false
      try {
        await updateRow({
          s: cur.s, t: cur.t,
          key: this._pkValues(row),
          values: { [col.name]: null },
          ...this._txPayload(),
        })
        await this.loadData()
        return true
      } catch {
        return false
      }
    },

    /** 更新整行多字段(PUT /api/row; 右键「编辑行」弹窗用) */
    async updateRowValues(r: number, values: Record<string, unknown>): Promise<boolean> {
      const cur = this._cur()
      const row = this.rows[r]
      if (!cur || !row) return false
      try {
        await updateRow({ s: cur.s, t: cur.t, key: this._pkValues(row), values, ...this._txPayload() })
        await this.loadData()
        return true
      } catch {
        return false
      }
    },

    /** 新增行(POST /api/row) */
    async insert(values: Record<string, unknown>): Promise<boolean> {
      const cur = this._cur()
      if (!cur) return false
      try {
        await insertRow({ s: cur.s, t: cur.t, values, ...this._txPayload() })
        await this.loadData()
        return true
      } catch {
        return false
      }
    },

    /** 删除选中行(P1-9): 批量接口一次请求删除(POST /api/rows/delete), 替代原 N 次串行 DELETE */
    async deleteSelected(): Promise<boolean> {
      const cur = this._cur()
      if (!cur || !this.selectedRows.size) return false
      try {
        const keys = [...this.selectedRows]
          .sort((a, b) => b - a)
          .map(i => this._pkValues(this.rows[i]))
          .filter(k => Object.keys(k).length)
        if (!keys.length) return false
        await batchDeleteRows({ s: cur.s, t: cur.t, keys, ...this._txPayload() } as never)
        this.selectedRows = new Set()
        await this.loadData()
        return true
      } catch {
        return false
      }
    },

    /** 主键值(无主键信息时用整行做 key, 由后端解析) */
    _pkValues(row: Record<string, unknown>): Record<string, unknown> {
      // 优先找 is_pk 列; 无则回退整行(后端 mutate 用 key 匹配)
      const pk: Record<string, unknown> = {}
      const hasPk = (this.columns as unknown as { is_pk?: boolean }[]).some(c => c.is_pk)
      if (hasPk) {
        ;(this.columns as unknown as { name: string; is_pk?: boolean }[]).forEach(c => {
          if (c.is_pk && row[c.name] !== undefined) pk[c.name] = row[c.name]
        })
      }
      return Object.keys(pk).length ? pk : { ...row }
    },

    /** 流式加载全部行(每批 2000, 上限 50000; 虚拟滚动渲染; P1-9: 分批直接 append 到 rows, 免临时大数组) */
    async loadAll(): Promise<number> {
      const cur = this._cur()
      if (!cur) return 0
      const MAX = 50000, BATCH = 2000
      let page = 1
      this.loading = true
      try {
        const acc: Record<string, unknown>[] = []
        for (; page < 60; page++) {
          const d: DataResp = await getData({
            s: cur.s, t: cur.t, page, size: BATCH,
            where: this.buildWhere(), order: this.buildOrder(),
          })
          if (page === 1) this.columns = d.columns || []
          const rows = d.rows || []
          acc.push(...rows)
          if (acc.length >= MAX || rows.length < BATCH) break
        }
        this.rows = acc
        this.total = acc.length
        this.page = 1
        this.pageSize = BATCH
        this.selectedRows = new Set()
        return acc.length
      } finally {
        this.loading = false
      }
    },

    /** 保存当前网格状态为 tab 快照(切换走时调用) */
    saveSnapshot(tabId: number) {
      this.snapshots[tabId] = {
        columns: this.columns, rows: this.rows, total: this.total,
        page: this.page, pageSize: this.pageSize,
        sort: this.sort ? { ...this.sort } : null,
        filters: { ...this.filters },
      }
    },

    /** 恢复 tab 快照(切回时调用); 无快照返回 false 由调用方 loadData */
    restoreSnapshot(tabId: number): boolean {
      const s = this.snapshots[tabId]
      if (!s) return false
      this.columns = s.columns
      this.rows = s.rows
      this.total = s.total
      this.page = s.page
      this.pageSize = s.pageSize
      this.sort = s.sort
      this.filters = { ...s.filters }
      this.selectedRows = new Set()
      this.editingCell = null
      return true
    },

    /** 删除 tab 快照(关闭 tab 时调用) */
    dropSnapshot(tabId: number) { delete this.snapshots[tabId] },

    /** 清理已不存在 tab 的快照(防泄漏) */
    pruneSnapshots(validIds: number[]) {
      for (const k of Object.keys(this.snapshots)) {
        if (!validIds.includes(Number(k))) delete this.snapshots[Number(k)]
      }
    },

    /** 清空(切表/断连) */
    reset() {
      this.columns = []; this.rows = []; this.total = 0; this.page = 1
      this.sort = null; this.filters = {}; this.selectedRows = new Set()
      this.editingCell = null
    },
  },
})
