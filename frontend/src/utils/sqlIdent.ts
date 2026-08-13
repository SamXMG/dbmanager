// 统一 SQL 标识符转义与 HTML 转义工具(P1-9 去重)
// 原分散于 tools.ts / grid.ts / ObjectTree.vue / DataGrid.vue / SqlWorkbench.vue / TableDesignerModal.vue
// 引用方统一从这里 import, 方言规则单点维护
export function esc(s: unknown): string {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;')
}

export function quoteIdent(dbType: string, name: string): string {
  const t = (dbType || '').toLowerCase()
  if (t === 'mssql') return '[' + name + ']'
  if (t === 'mysql' || t === 'mariadb' || t === 'oceanbase' || t === 'tidb') return '`' + name + '`'
  return '"' + name + '"'
}

/** 别名(向后兼容旧名 qident) */
export const qident = quoteIdent
