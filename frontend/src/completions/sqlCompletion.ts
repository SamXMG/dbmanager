// SQL 补全(CodeMirror 6 方案 B): lang-sql 关键字补全 + 自定义 completionSource
// 算法部分从旧前端 js/sql.js:55-144 翻译(parseSqlAliases/getTableColsCached/
// resolveDotCandidates/buildSqlCandidates), DOM 渲染部分弃用(CM6 autocomplete 接管)
import type { CompletionContext, CompletionResult } from '@codemirror/autocomplete'
import { getColumns } from '@/api/database'

// ---- SQL 关键字(与旧 js/sql.js SQL_KW_SET 一致) ----
export const SQL_KW_SET = new Set((
  'SELECT TOP DISTINCT FROM WHERE AND OR NOT IN EXISTS LIKE BETWEEN IS NULL ORDER BY GROUP HAVING AS ' +
  'JOIN INNER LEFT RIGHT OUTER ON SET VALUES INSERT INTO UPDATE DELETE CREATE TABLE ALTER DROP INDEX ' +
  'UNIQUE PRIMARY KEY FOREIGN REFERENCES CASE WHEN THEN ELSE END UNION LIMIT OFFSET COUNT SUM AVG MAX ' +
  'MIN COALESCE NULLIF CAST CONVERT GETDATE DATEADD DATEDIFF LEN LOWER UPPER TRIM REPLACE SUBSTRING ' +
  'ISNULL CURRENT_DATE NOW').toLowerCase().split(' '))

// ---- MySQL/MariaDB 常见保留字: 表/字段名自动加反引号(旧 MYSQL_RESERVED) ----
const MYSQL_RESERVED = new Set((
  'LEAVE ORDER GROUP KEY DESC RANK USER REFERENCES CHECK INTERVAL NATURAL PRIMARY FOREIGN TABLE INDEX ' +
  'SELECT FROM WHERE AND OR NOT IN EXISTS LIKE BETWEEN IS NULL UNION JOIN INNER LEFT RIGHT OUTER ON SET ' +
  'VALUES UPDATE DELETE CREATE ALTER DROP TRIGGER PROCEDURE FUNCTION DATABASE SCHEMA DEFAULT CONSTRAINT ' +
  'UNIQUE COLLATE COLUMN VIEW VALUE').split(' '))

export function quoteSqlIdent(dbType: string, name: string): string {
  if (dbType === 'mysql' && MYSQL_RESERVED.has(String(name).toUpperCase())) return '`' + name + '`'
  return name
}

// ---- 补全数据源(由组件注入: useDatabaseStore.tables + useTabStore.currentMeta) ----
export interface CompletionData {
  dbType: string
  tables: { schema?: string; name: string; type?: string }[]
  columns: { name: string; type?: string }[]
}

// ---- 从 SQL 提取 FROM/JOIN 后的表引用与别名(旧 parseSqlAliases, 去掉 DOM 依赖) ----
export function parseSqlAliases(sqlText: string): Record<string, string> {
  const map: Record<string, string> = {}
  const re = /(?:FROM|JOIN)\s+([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*){0,2})(?:\s+(?:AS\s+)?([A-Za-z_$][\w$]*))?/gi
  let m: RegExpExecArray | null
  while ((m = re.exec(sqlText))) {
    const tableRef = m[1]
    map[tableRef.toLowerCase()] = tableRef // 表名自身也可触发
    const alias = m[2]
    if (alias && !SQL_KW_SET.has(alias.toLowerCase())) {
      map[alias.toLowerCase()] = tableRef // 别名 -> 真实表
    }
  }
  return map
}

// ---- 光标前是否处于 "<对象>." 上下文(旧 getDotContext, 改 CM6 状态) ----
export function getDotContext(doc: string, pos: number): { ref: string; typed: string; insertStart: number } | null {
  const prefix = doc.slice(0, pos)
  const m = prefix.match(/([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\.([\w$]*)$/)
  if (!m) return null
  return { ref: m[1], typed: m[2], insertStart: pos - m[2].length }
}

// ---- 按需拉列缓存(旧 getTableColsCached; 走 api/database.getColumns) ----
const colCache = new Map<string, { name: string; type?: string }[] | null>()
export async function getTableColsCached(
  schema: string, table: string,
): Promise<{ name: string; type?: string }[] | null> {
  const key = (schema || '') + '|' + table
  if (colCache.has(key)) return colCache.get(key) ?? null
  try {
    const d = await getColumns(schema, table)
    if (Array.isArray(d)) {
      colCache.set(key, d)
      return d
    }
  } catch {
    /* 忽略: 未知对象/无权限等场景静默 */
  }
  colCache.set(key, null)
  return null
}

// ---- 解析 <对象>. 到具体表并返回字段候选(旧 resolveDotCandidates) ----
export interface DotCandidate { items: { label: string; kind: string }[]; insertStart: number }

export async function resolveDotCandidates(
  dc: { ref: string; typed: string; insertStart: number },
  doc: string,
  data: CompletionData,
): Promise<DotCandidate | null> {
  const ref = dc.ref.toLowerCase()
  const aliases = parseSqlAliases(doc)
  let schema = ''
  let table = ''
  const tableRef = aliases[ref] // 1) 别名映射
  if (tableRef) {
    const parts = tableRef.split('.')
    if (parts.length === 2) { schema = parts[0]; table = parts[1] }
    else { table = parts[0] }
  } else if (ref.includes('.')) { // 2) schema.表 或系统对象(sys.xxx)
    const idx = ref.lastIndexOf('.')
    schema = ref.slice(0, idx)
    table = ref.slice(idx + 1)
  } else { // 3) 裸表名 -> 在 tables 中解析 schema
    table = ref
    const hits = (data.tables || []).filter(t => (t.name || '').toLowerCase() === ref)
    if (hits.length === 1) schema = hits[0].schema || ''
    else if (hits.length > 1) schema = (hits.find(t => t.schema) || hits[0]).schema || ''
  }
  if (!table) return null
  const cols = await getTableColsCached(schema, table)
  if (!cols || !cols.length) return null
  const typed = dc.typed.toLowerCase()
  const items = cols
    .filter(c => !typed || (c.name || '').toLowerCase().startsWith(typed))
    .map(c => ({ label: c.name, kind: 'c' }))
    .slice(0, 50)
  return { items, insertStart: dc.insertStart }
}

// ---- 普通前缀候选: 关键字+表+字段(旧 buildSqlCandidates) ----
export function buildCandidates(prefix: string, data: CompletionData): { label: string; kind: string }[] {
  const p = prefix.toLowerCase()
  const out: { label: string; kind: string }[] = []
  const seen = new Set<string>()
  const push = (label: string, kind: string) => {
    const k = kind + ':' + label.toLowerCase()
    if (!seen.has(k)) { seen.add(k); out.push({ label, kind }) }
  }
  SQL_KW_SET.forEach(k => { if (k.startsWith(p)) push(k.toUpperCase(), 'k') })
  ;(data.tables || []).forEach(t => {
    if ((t.name || '').toLowerCase().startsWith(p)) push(quoteSqlIdent(data.dbType, t.name), 't')
  })
  ;(data.columns || []).forEach(c => {
    if ((c.name || '').toLowerCase().startsWith(p)) push(quoteSqlIdent(data.dbType, c.name), 'c')
  })
  return out.slice(0, 50)
}

// ---- CM6 completionSource 工厂(方案 B) ----
export function createSqlCompletionSource(getData: () => CompletionData) {
  return async (ctx: CompletionContext): Promise<CompletionResult | null> => {
    const data = getData()
    const doc = ctx.state.doc.toString()
    const pos = ctx.pos
    // 1) dot 上下文优先: 别名/表. 后的字段
    const dc = getDotContext(doc, pos)
    if (dc) {
      const r = await resolveDotCandidates(dc, doc, data)
      if (r && r.items.length) {
        return {
          from: r.insertStart,
          options: r.items.map(it => ({
            label: it.label,
            type: 'variable',
            detail: '字段',
          })),
        }
      }
    }
    // 2) 普通前缀: 关键字/表/当前表字段
    const word = ctx.matchBefore(/[\w$]*/)
    if (!word || (!word.text && !ctx.explicit)) return null
    const items = buildCandidates(word.text, data)
    if (!items.length) return null
    return {
      from: word.from,
      options: items.map(it => ({
        label: it.label,
        type: it.kind === 't' ? 'class' : it.kind === 'c' ? 'variable' : 'keyword',
        detail: it.kind === 't' ? '表' : it.kind === 'c' ? '字段' : '关键字',
      })),
    }
  }
}
