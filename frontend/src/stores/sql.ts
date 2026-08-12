// SQL 工作台 store(阶段 4 完整): 执行/多语句结果 tab/写模式/历史/收藏/格式化
// 对应旧前端 js/sql.js 的 runSql/addSqlBatch/loadSqlHist/toggleFav 逻辑
import { defineStore } from 'pinia'
import { runSql, explainQuery, type SqlResult } from '@/api/sql'
import { useConnectionStore } from '@/stores/connection'
import { useUIStore } from '@/stores/ui'

/** 方言标识引用(对齐旧 quoteIdent): mysql `x` / mssql [x] / 其他 "x" */
function qIdent(dbType: string, name: string): string {
  const t = (dbType || '').toLowerCase()
  if (t === 'mssql') return '[' + name + ']'
  if (t === 'mysql' || t === 'mariadb' || t === 'oceanbase' || t === 'tidb') return '`' + name + '`'
  return '"' + name + '"'
}

export interface SqlResultTab {
  id: number
  sql: string
  columns?: { name: string }[]
  rows?: Record<string, unknown>[]
  total?: number
  truncated?: boolean
  affected?: number
  readonly?: boolean
  error?: string
  explain?: boolean
}

const LS_HISTORY = 'dbm_sql_history'
const LS_FAVORITES = 'dbm_sql_favorites'
// 旧版前端 localStorage key(迁移兼容): dbm_sql_hist(数组, 元素 {sql,t} 或字符串) / dbm_sql_fav(字符串数组)
const LS_HISTORY_OLD = 'dbm_sql_hist'
const LS_FAVORITES_OLD = 'dbm_sql_fav'

/** 旧 formatSql 翻译: 关键字换行 + AND/OR 缩进(旧版 js/sql.js formatSql 简化版) */
export function formatSqlText(input: string): string {
  const combos = ['SELECT TOP', 'LEFT JOIN', 'RIGHT JOIN', 'INNER JOIN', 'OUTER JOIN',
    'UNION ALL', 'INSERT INTO', 'DELETE FROM', 'CREATE TABLE', 'ALTER TABLE',
    'DROP TABLE', 'ORDER BY', 'GROUP BY', 'CASE WHEN']
  const singles = ['SELECT', 'FROM', 'WHERE', 'HAVING', 'JOIN', 'ON', 'SET', 'VALUES',
    'UPDATE', 'LIMIT', 'TOP', 'CASE', 'WHEN', 'THEN', 'ELSE', 'END', 'UNION', 'AND', 'OR']
  let out = input
  const ph = combos.map((c, i) => ['\u0001' + i + '\u0001', c] as const)
  for (const [p, c] of ph) out = out.replace(new RegExp('\\b' + c.replace(/ /g, '\\s+') + '\\b', 'gi'), p)
  for (const kw of singles) out = out.replace(new RegExp('\\b' + kw + '\\b', 'gi'), m => '\n' + m.toUpperCase())
  for (const [p, c] of ph) out = out.split(p).join('\n' + c.toUpperCase())
  out = out.replace(/\n\s*(AND|OR)\b/gi, '\n  $1')
  out = out.replace(/[ \t]+\n/g, '\n').replace(/\n{2,}/g, '\n').replace(/^\n+/, '').trim()
  return out
}

export const useSqlStore = defineStore('sql', {
  state: () => ({
    tabs: [] as SqlResultTab[],
    active: null as number | null,
    sqlSeq: 0,
    writeMode: false,
    sqlText: '',
    history: [] as { sql: string; ts: number }[],
    favorites: [] as string[],
    /** 上次批量执行结果(sqls 与本次一致则覆盖对应 tab, 防同 SQL 连点堆 tab) */
    lastBatch: null as { sqls: string[]; tabIds: number[] } | null,
  }),
  getters: {
    activeTab: (s) => s.tabs.find(t => t.id === s.active) || null,
  },
  actions: {
    /** 执行当前 SQL(或指定 sql)。返回新增/更新后的结果 tab 列表 */
    async exec(sql?: string, write?: boolean): Promise<SqlResultTab[]> {
      const text = (sql ?? this.sqlText).trim()
      if (!text) throw new Error('请输入 SQL')
      const w = write ?? this.writeMode
      this.pushHistory(text)
      const connStore = useConnectionStore()
      const r = await runSql({
        sql: text, limit: 500, write: w,
        database: connStore.conn?.database || undefined,
      })
      // 多语句: 后端返回 results[] 每语句一个结果 -> 每句一个 tab; 单语句直接包装
      const results: SqlResult[] = (r.results && r.results.length ? r.results : [r])
      const sqls = results.map(x => x.sql || text)
      const batch = this.buildTabs(results, sqls, text)
      this.lastBatch = batch
      this.active = batch.tabIds[0] ?? null
      return batch.tabIds.map(id => this.tabs.find(t => t.id === id)!).filter(Boolean)
    },

    /** 结果 -> tab 列表(与上次批次完全相同则原地覆盖, 否则新建) */
    buildTabs(results: SqlResult[], sqls: string[], fallbackSql: string) {
      const prev = this.lastBatch
      const same = prev && prev.sqls.length === sqls.length && prev.sqls.every((s, i) => s === sqls[i])
      const tabIds: number[] = []
      results.forEach((res, i) => {
        const payload = { sql: sqls[i] || fallbackSql, ...res }
        if (same && prev && prev.tabIds[i] != null) {
          // 覆盖旧 tab(保持 id, 内容刷新)
          const old = this.tabs.find(t => t.id === prev.tabIds[i])
          if (old) {
            Object.assign(old, payload)
            tabIds.push(old.id)
            return
          }
        }
        const t: SqlResultTab = { ...payload, id: ++this.sqlSeq }
        this.tabs.push(t)
        tabIds.push(t.id)
      })
      return { sqls, tabIds }
    },

    /** EXPLAIN 当前 SQL */
    async explain(sql?: string): Promise<SqlResultTab> {
      const text = (sql ?? this.sqlText).trim()
      if (!text) throw new Error('请输入 SQL')
      const connStore = useConnectionStore()
      const r = await explainQuery({ sql: text, database: connStore.conn?.database || undefined })
      return this.addResult({ sql: 'EXPLAIN ' + text, ...r, explain: true })
    },

    /** 新增单个结果 tab 并激活(EXPLAIN/外部调用用) */
    addResult(tab: Omit<SqlResultTab, 'id'>): SqlResultTab {
      const t: SqlResultTab = { ...tab, id: ++this.sqlSeq }
      this.tabs.push(t)
      this.active = t.id
      return t
    },

    switchTab(id: number) { this.active = id },
    closeTab(id: number) {
      const idx = this.tabs.findIndex(t => t.id === id)
      if (idx < 0) return
      this.tabs.splice(idx, 1)
      if (this.active === id) {
        this.active = this.tabs.length ? this.tabs[Math.min(idx, this.tabs.length - 1)].id : null
      }
    },
    clearResults() {
      this.tabs = []
      this.active = null
      this.lastBatch = null
    },

    /** 历史/收藏(localStorage; 首次加载迁移旧版 key) */
    loadHistory() {
      try {
        const raw = JSON.parse(localStorage.getItem(LS_HISTORY) || 'null')
        if (Array.isArray(raw)) this.history = raw
        else {
          // 迁移旧版 dbm_sql_hist: 元素 {sql,t} 或纯字符串
          const old = JSON.parse(localStorage.getItem(LS_HISTORY_OLD) || '[]')
          this.history = old.map((x: unknown) =>
            typeof x === 'string' ? { sql: x, ts: 0 } : x as { sql: string; ts: number })
          if (this.history.length) {
            try { localStorage.setItem(LS_HISTORY, JSON.stringify(this.history)) } catch { /* */ }
          }
        }
      } catch { this.history = [] }
    },
    pushHistory(sql: string) {
      const ts = Date.now()
      this.history = [{ sql, ts }, ...this.history.filter(h => h.sql !== sql)].slice(0, 200)
      try { localStorage.setItem(LS_HISTORY, JSON.stringify(this.history)) } catch { /* */ }
    },
    clearHistory() {
      this.history = []
      try { localStorage.removeItem(LS_HISTORY) } catch { /* */ }
    },

    loadFavorites() {
      try {
        const raw = JSON.parse(localStorage.getItem(LS_FAVORITES) || 'null')
        if (Array.isArray(raw)) this.favorites = raw
        else {
          const old = JSON.parse(localStorage.getItem(LS_FAVORITES_OLD) || '[]')
          this.favorites = old
          if (this.favorites.length) {
            try { localStorage.setItem(LS_FAVORITES, JSON.stringify(this.favorites)) } catch { /* */ }
          }
        }
      } catch { this.favorites = [] }
    },
    toggleFavorite(sql: string) {
      this.favorites.includes(sql)
        ? (this.favorites = this.favorites.filter(s => s !== sql))
        : this.favorites.push(sql)
      try { localStorage.setItem(LS_FAVORITES, JSON.stringify(this.favorites)) } catch { /* */ }
    },
    clearFavorites() {
      this.favorites = []
      try { localStorage.removeItem(LS_FAVORITES) } catch { /* */ }
    },

    /** 历史/收藏一次性加载(工作台挂载时调用) */
    loadAll() {
      this.loadHistory()
      this.loadFavorites()
    },

    /** 历史回填编辑器 */
    setSqlText(sql: string) { this.sqlText = sql },

    /** 新建触发器: 按方言生成 CREATE TRIGGER 模板填入工作台并切 SQL 视图(旧版 newTrigger) */
    newTrigger(s: string, t: string): boolean {
      const connStore = useConnectionStore()
      const ui = useUIStore()
      const dt = (connStore.conn?.db_type || 'mysql').toLowerCase()
      const name = window.prompt('触发器名(如 trg_' + t + '_ins):', 'trg_' + t + '_ins')
      if (!name) return false
      const q = (n: string) => qIdent(dt, n)
      let sql = ''
      if (dt === 'mysql' || dt === 'mariadb') {
        sql = `DELIMITER $$\nCREATE TRIGGER ${q(name)} AFTER INSERT ON ${q(s)}.${q(t)}\nFOR EACH ROW\nBEGIN\n    -- 在此编写触发器逻辑\nEND$$\nDELIMITER ;`
      } else if (dt === 'postgresql' || dt === 'kingbase') {
        sql = `CREATE FUNCTION ${q(name)}_fn() RETURNS TRIGGER AS $$\nBEGIN\n    RETURN NEW;\nEND;\n$$ LANGUAGE plpgsql;\nCREATE TRIGGER ${q(name)} AFTER INSERT ON ${q(s)}.${q(t)}\nFOR EACH ROW EXECUTE FUNCTION ${q(name)}_fn();`
      } else if (dt === 'mssql') {
        sql = `CREATE TRIGGER ${q(name)} ON ${q(s)}.${q(t)}\nAFTER INSERT\nAS\nBEGIN\n    -- 在此编写触发器逻辑\nEND;`
      } else {
        ui.toast('该数据库类型暂不支持新建触发器', true)
        return false
      }
      this.setSqlText(sql)
      ui.switchView('sql')
      ui.toast('触发器模板已生成, 检查后执行')
      return true
    },

    /** 格式化当前 SQL */
    format() {
      this.sqlText = formatSqlText(this.sqlText)
    },
  },
})
