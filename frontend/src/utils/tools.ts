// 工具向导集(阶段5 批2): 查询构建器/数据导入/测试数据/备份还原/schema对比/DB用户权限/数据字典导出
// 弹窗走 ui.showModal + setTimeout 绑 onclick 模式(对齐 Toolbar.addRow/pasteInsert)
import { useUIStore } from '@/stores/ui'
import { useSqlStore } from '@/stores/sql'
import { useConnectionStore } from '@/stores/connection'
import { useDatabaseStore } from '@/stores/database'
import { useTabStore } from '@/stores/tab'
import { useAuthStore } from '@/stores/auth'
import { getColumns, type Column } from '@/api/database'
import { importData, genData, schemaDiff, schemaSync, alterTable } from '@/api/schema'
import { listConnections, type ConnMeta } from '@/api/connection'
import { API_BASE, authHeaders } from '@/api/client'
import { STORAGE_KEYS } from '@/constants/storage'

const ui = useUIStore()
const sqlStore = useSqlStore()
const connStore = useConnectionStore()
const dbStore = useDatabaseStore()
const tabStore = useTabStore()
const auth = useAuthStore()

// P1-9 去重: esc/quoteIdent 统一收口到 sqlIdent.ts(单点维护方言规则), 此处 re-export 保持旧引用兼容
import { esc, quoteIdent, qident } from '@/utils/sqlIdent'
export { esc, quoteIdent, qident }
function dbType(): string { return connStore.conn?.db_type || 'mysql' }
function downloadBlob(blob: Blob, filename: string) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  document.body.appendChild(a); a.click(); a.remove()
  URL.revokeObjectURL(a.href)
}

// ================= 查询构建器 =================
/** 可视化拼 SELECT(旧版 openQueryBuilder): 选表 -> 勾列 -> 条件 -> 排序 -> limit -> 生成 SQL 到工作台 */
export async function openQueryBuilder() {
  if (!connStore.connected) { ui.toast('请先连接数据库', true); return }
  let tables = dbStore.tables.filter(x => x.type !== 'View')
  if (!tables.length) { ui.toast('无可用表', true); return }
  const opts = tables.map(t => `<option value="${esc(t.schema + '\u0001' + t.name)}">${esc(t.schema ? t.schema + '.' : '')}${esc(t.name)}</option>`).join('')
  ui.showModal(`<h3>查询构建器</h3>
    <div class="field"><label>表</label><select id="qbTable">${opts}</select></div>
    <div class="field"><label>选择列(勾选参与查询)</label><div id="qbCols" style="max-height:140px;overflow:auto;border:1px solid #eee;border-radius:6px;padding:6px"></div></div>
    <h4 style="margin:8px 0 4px;font-size:13px">条件(WHERE, AND 连接)</h4>
    <div id="qbCond"></div>
    <button class="sm" onclick="window.__qbAdd && window.__qbAdd()">+ 条件</button>
    <div class="field" style="margin-top:8px"><label>排序</label>
      <div class="row2"><select id="qbSortCol"><option value="">无</option></select><select id="qbSortDir"><option value="ASC">升序</option><option value="DESC">降序</option></select></div>
    </div>
    <div class="field"><label>LIMIT</label><input id="qbLimit" type="number" value="100" style="width:120px"></div>
    <div class="acts"><button onclick="closeModal()">取消</button><button class="primary" onclick="window.__qbBuild && window.__qbBuild()">生成 SQL</button></div>`)
  const sel = document.getElementById('qbTable') as HTMLSelectElement
  const loadCols = async () => {
    const [s, t] = sel.value.split('\u0001')
    try {
      const cols = await getColumns(s, t)
      const box = document.getElementById('qbCols')
      if (box) box.innerHTML = cols.map(c => `<label style="display:block;padding:2px 6px;cursor:pointer"><input type="checkbox" value="${esc(c.name)}" checked> ${esc(c.name)} <span style="color:#86909c;font-size:11px">${esc(c.type || '')}</span></label>`).join('')
      const sc = document.getElementById('qbSortCol') as HTMLSelectElement
      if (sc) sc.innerHTML = '<option value="">无</option>' + cols.map(c => `<option value="${esc(c.name)}">${esc(c.name)}</option>`).join('')
    } catch { /* */ }
  }
  await loadCols()
  sel.addEventListener('change', loadCols)
  ;(window as unknown as Record<string, unknown>).__qbAdd = () => {
    const cols = [...document.querySelectorAll('#qbCols input')].map(x => (x as HTMLInputElement).value)
    if (!cols.length) { ui.toast('请先选择列', true); return }
    const box = document.getElementById('qbCond')
    if (box) box.insertAdjacentHTML('beforeend',
      `<div class="row2" style="margin-bottom:4px"><select class="qb-c">${cols.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('')}</select>` +
      `<select class="qb-op"><option value="=">=</option><option value="!=">!=</option><option value=">">&gt;</option><option value=">=">&gt;=</option><option value="<">&lt;</option><option value="<=">&lt;=</option><option value="LIKE">LIKE</option><option value="IN">IN</option><option value="IS NULL">IS NULL</option></select>` +
      `<input class="qb-v" placeholder="值(IS NULL 可空)" style="flex:1"><button class="sm danger" onclick="this.parentNode.remove()">✕</button></div>`)
  }
  ;(window as unknown as Record<string, unknown>).__qbBuild = () => {
    const [s, t] = sel.value.split('\u0001')
    const q = (n: string) => qident(dbType(), n)
    const checked = [...document.querySelectorAll('#qbCols input:checked')].map(x => (x as HTMLInputElement).value)
    const cols = checked.length ? checked.map(q).join(', ') : '*'
    let sql = 'SELECT ' + cols + ' FROM ' + q(s) + '.' + q(t)
    const conds = [...document.querySelectorAll('#qbCond .row2')].map(el => {
      const c = (el.querySelector('.qb-c') as HTMLSelectElement).value
      const op = (el.querySelector('.qb-op') as HTMLSelectElement).value
      const v = (el.querySelector('.qb-v') as HTMLInputElement).value.trim()
      if (op === 'IS NULL') return q(c) + ' IS NULL'
      if (v === '') return null
      const val = (op === 'LIKE' || op === 'IN') ? v : (isNaN(Number(v)) ? "'" + v.replace(/'/g, "''") + "'" : v)
      return q(c) + ' ' + op + ' ' + val
    }).filter(Boolean) as string[]
    if (conds.length) sql += ' WHERE ' + conds.join(' AND ')
    const sortCol = (document.getElementById('qbSortCol') as HTMLSelectElement).value
    if (sortCol) sql += ' ORDER BY ' + q(sortCol) + ' ' + (document.getElementById('qbSortDir') as HTMLSelectElement).value
    const lim = parseInt((document.getElementById('qbLimit') as HTMLInputElement).value, 10)
    if (lim > 0) sql += ' LIMIT ' + lim
    sqlStore.setSqlText(sql)
    ui.closeModal()
    ui.switchView('sql')
    ui.toast('SQL 已生成, 检查后按 Ctrl+Enter 执行')
  }
}

// ================= 数据导入向导(CSV 前端解析 / XLSX 后端解析 -> 列映射) =================
export function openImport(s?: string, t?: string) {
  const cur = tabStore.current
  const sc = s || (cur && cur.s)
  const tb = t || (cur && cur.t)
  if (!sc || !tb) { ui.toast('请先打开目标表', true); return }
  ui.showModal(`<h3>数据导入 · ${esc(sc)}.${esc(tb)}</h3>
    <div class="field"><label>文件(CSV / XLSX)</label><input type="file" id="impFile" accept=".csv,.xlsx,.xls"></div>
    <div class="field"><label>导入方式</label><select id="impMode"><option value="insert">追加插入</option><option value="replace">清空后导入</option></select></div>
    <div id="impMap" style="max-height:200px;overflow:auto;border:1px solid #eee;border-radius:6px;padding:6px;margin-top:8px"></div>
    <div id="impPrev" style="color:#86909c;font-size:12px;margin-top:6px"></div>
    <div class="acts"><button onclick="closeModal()">取消</button><button class="primary" onclick="window.__impRun && window.__impRun()" id="impGo">导入</button></div>`)
  const fileEl = document.getElementById('impFile') as HTMLInputElement
  const parseAndMap = async () => {
    const f = fileEl.files?.[0]
    if (!f) return
    try {
      let header: string[] = [], rows: string[][] = []
      if (/\.xlsx?$/i.test(f.name)) {
        const d = await uploadXlsx(f)
        header = d.header || []
        rows = d.rows || []
      } else {
        const text = await f.text()
        const parsed = parseCsvText(text)
        header = parsed[0] || []
        rows = parsed.slice(1)
      }
      const cols: Column[] = await getColumns(sc, tb)
      const box = document.getElementById('impMap')
      if (box) box.innerHTML = header.map((h, i) =>
        `<div class="row2" style="margin-bottom:4px"><label style="width:110px;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(h)}">${esc(h || '(空列' + i + ')')}</label>` +
        `<select id="impMap_${i}" style="flex:1">${cols.map(c => `<option value="${esc(c.name)}" ${c.name === h ? 'selected' : ''}>${esc(c.name)} (${esc(c.type || '')})</option>`).join('')}</select></div>`).join('')
      const prev = document.getElementById('impPrev')
      if (prev) prev.textContent = `文件 ${rows.length} 行 × ${header.length} 列 → 目标表 ${cols.length} 列`
    } catch (e) { ui.toast('解析失败: ' + (e as Error).message, true) }
  }
  fileEl.addEventListener('change', parseAndMap)
  ;(window as unknown as Record<string, unknown>).__impRun = async () => {
    const mapping: (string | null)[] = (document.querySelectorAll('#impMap select') ? [...document.querySelectorAll('#impMap select')].map(s => (s as HTMLSelectElement).value) : []) as string[]
    const f = fileEl.files?.[0]
    if (!f || !mapping.length) { ui.toast('请先选择文件并映射列', true); return }
    let header: string[] = [], rows: string[][] = []
    if (/\.xlsx?$/i.test(f.name)) { const d = await uploadXlsx(f); header = d.header || []; rows = d.rows || [] }
    else { const parsed = parseCsvText(await f.text()); header = parsed[0] || []; rows = parsed.slice(1) }
    const data = rows.map(r => {
      const o: Record<string, unknown> = {}
      header.forEach((h, i) => { const cn = mapping[i]; if (cn) o[cn] = r[i] !== undefined && r[i] !== '' ? r[i] : null })
      return o
    })
    if (!confirm(`确认导入 ${data.length} 行到 ${sc}.${tb}？`)) return
    try {
      const d = await importData({ s: sc, t: tb, columns: mapping.filter(Boolean) as string[], rows: data })
      ui.closeModal()
      ui.toast('已导入 ' + (d as { affected?: number }).affected + ' 行')
    } catch (e) { ui.toast('导入失败: ' + (e as Error).message, true) }
  }
}

/** 上传 xlsx 到后端解析(原始二进制, 带鉴权头) */
async function uploadXlsx(file: File): Promise<{ header: string[]; rows: string[][] }> {
  // P1-9 去重: 统一走 client.authHeaders()
  const headers: Record<string, string> = { 'Content-Type': 'application/octet-stream', ...(await authHeaders()) }
  const r = await fetch(API_BASE + '/api/import/xlsx', { method: 'POST', headers, body: await file.arrayBuffer() })
  const d = await r.json().catch(() => ({}))
  if (d.error) throw new Error(d.error)
  return d
}
/** 解析 CSV 文本(引号包裹, 逗号分隔) */
function parseCsvText(text: string): string[][] {
  const lines = text.replace(/\r\n/g, '\n').replace(/\uFEFF/g, '').split('\n').filter(l => l.trim() !== '')
  return lines.map(l => {
    const out: string[] = []
    let cur = '', inQ = false
    for (let i = 0; i < l.length; i++) {
      const ch = l[i]
      if (inQ) {
        if (ch === '"' && l[i + 1] === '"') { cur += '"'; i++ }
        else if (ch === '"') inQ = false
        else cur += ch
      } else if (ch === '"') inQ = true
      else if (ch === ',') { out.push(cur); cur = '' }
      else cur += ch
    }
    out.push(cur)
    return out
  })
}

// ================= 测试数据生成器 =================
export function openGenData(s?: string, t?: string) {
  const cur = tabStore.current
  const sc = s || (cur && cur.s)
  const tb = t || (cur && cur.t)
  if (!sc || !tb) { ui.toast('请先打开目标表', true); return }
  ui.showModal(`<h3>生成测试数据 · ${esc(sc)}.${esc(tb)}</h3>
    <div class="field"><label>生成行数(上限 50000)</label><input id="gdRows" type="number" value="100" min="1" max="50000"></div>
    <p style="color:#86909c;font-size:12px">按列类型智能生成(自增主键/只读列跳过)</p>
    <div class="acts"><button onclick="closeModal()">取消</button><button class="primary" onclick="window.__gdRun && window.__gdRun()">生成</button></div>`)
  ;(window as unknown as Record<string, unknown>).__gdRun = async () => {
    const n = parseInt((document.getElementById('gdRows') as HTMLInputElement).value, 10) || 100
    if (!confirm(`确认生成 ${n} 行测试数据到 ${sc}.${tb}？`)) return
    try {
      const d = await genData({ s: sc, t: tb, rows: n })
      ui.closeModal()
      ui.toast('已生成 ' + (d as { inserted?: number }).inserted + ' 行')
    } catch (e) { ui.toast('生成失败: ' + (e as Error).message, true) }
  }
}

// ================= 备份 / 还原 =================
/** 备份: /api/backup 下载 SQL 脚本 */
export async function openBackup() {
  if (!connStore.connected) { ui.toast('请先连接数据库', true); return }
  try {
    const r = await fetch(API_BASE + '/api/backup', { headers: await authHeaders() })
    if (!r.ok) throw new Error('备份失败')
    const blob = await r.blob()
    const cd = r.headers.get('Content-Disposition') || ''
    const m = cd.match(/filename="?([^";]+)"?/)
    downloadBlob(blob, m ? m[1] : 'backup.sql')
    ui.toast('备份已下载')
  } catch (e) { ui.toast('备份失败: ' + (e as Error).message, true) }
}
/** 还原: 上传 SQL 脚本 -> /api/restore(危险, 双确认) */
export function openRestore() {
  if (!connStore.connected) { ui.toast('请先连接数据库', true); return }
  ui.showModal(`<h3>还原备份</h3>
    <p style="color:#d4660a;font-size:12px">⚠ 将执行备份脚本中的 CREATE/INSERT(仅 DDL+DML)。建议先备份当前库。</p>
    <div class="field"><label>SQL 脚本(.sql)</label><input type="file" id="rsFile" accept=".sql,.txt"></div>
    <div class="acts"><button onclick="closeModal()">取消</button><button class="primary" onclick="window.__rsRun && window.__rsRun()">还原</button></div>`)
  ;(window as unknown as Record<string, unknown>).__rsRun = async () => {
    const f = (document.getElementById('rsFile') as HTMLInputElement).files?.[0]
    if (!f) { ui.toast('请选择 SQL 文件', true); return }
    if (!confirm('确认还原？将执行文件中的全部 SQL(不可撤销)!')) return
    try {
      const sql = await f.text()
      const d = await import('@/api/schema').then(m => m.restore({ sql }))
      ui.closeModal()
      ui.toast('还原完成: 成功' + (d as { executed?: unknown[] }).executed?.length + ' / 失败' + (d as { failed?: unknown[] }).failed?.length)
    } catch (e) { ui.toast('还原失败: ' + (e as Error).message, true) }
  }
}

// ================= schema diff 结构对比(跨连接) =================
export async function openSchemaDiff(s: string, t: string) {
  let conns: ConnMeta[] = []
  try { conns = await listConnections() } catch { /* */ }
  if (!conns.length) { ui.toast('请先保存目标连接', true); return }
  ui.showModal(`<h3>结构对比 · ${esc(s)}.${esc(t)}</h3>
    <div class="field"><label>目标连接</label><select id="sdDst">${conns.map(c => `<option value="${esc(c.name)}">${esc(c.name)} (${esc(c.db_type)})</option>`).join('')}</select></div>
    <div id="sdOut" style="max-height:240px;overflow:auto;border:1px solid #eee;border-radius:6px;padding:8px;margin-top:8px;font-size:12px">对比结果将显示在这里</div>
    <div class="acts"><button onclick="closeModal()">关闭</button><button class="primary" onclick="window.__sdRun && window.__sdRun()">对比</button></div>`)
  ;(window as unknown as Record<string, unknown>).__sdRun = async () => {
    const dstName = (document.getElementById('sdDst') as HTMLSelectElement).value
    const conn = connStore.conn
    const src = conn && conn.name ? { name: conn.name } : conn || {}
    try {
      const d = await schemaDiff({ src, dst: { name: dstName }, schema: s, table: t })
      const out = document.getElementById('sdOut')
      const diff = (d as { diff?: string[] }).diff || []
      if (out) out.innerHTML = diff.length
        ? diff.map(x => '<div style="padding:3px 0;border-bottom:1px solid #f5f6f8">' + esc(x) + '</div>').join('')
        : '<div class="empty2">无差异(结构一致)</div>'
    } catch (e) { ui.toast('对比失败: ' + (e as Error).message, true) }
  }
}

// ================= DB 用户与权限(只读视图) =================
export async function openDbUsers() {
  if (!connStore.connected) { ui.toast('请先连接数据库', true); return }
  ui.showModal(`<h3>用户与权限</h3><div class="empty2" style="padding:20px">加载中...</div>`)
  try {
    const d = await getDbUsers()
    if (!d.supported) {
      ui.showModal('<h3>用户与权限</h3><div class="empty2" style="padding:20px">当前数据库类型不支持用户与权限管理</div><div class="acts"><button onclick="closeModal()">关闭</button></div>')
      return
    }
    const sec = (title: string, rows: Record<string, unknown>[], cols: [string, string][]) => {
      if (!rows || !rows.length) return `<h4 style="margin:10px 0 4px">${title} (0)</h4><div class="empty2">无数据</div>`
      let s = `<h4 style="margin:10px 0 4px">${title} (${rows.length})</h4><table style="width:100%;border-collapse:collapse;font-size:12px">`
      s += `<tr>${cols.map(c => `<th style="text-align:left;padding:3px 6px;border-bottom:1px solid #eee">${esc(c[1])}</th>`).join('')}</tr>`
      rows.forEach(r => {
        s += `<tr>${cols.map(c => { const v = r[c[0]]; if (v === true) return '<td style="padding:3px 6px">是</td>'; if (v === false) return '<td style="padding:3px 6px">否</td>'; return `<td style="padding:3px 6px">${esc(v == null ? '-' : v)}</td>`; }).join('')}</tr>`
      })
      return s + '</table>'
    }
    ui.showModal(`<h3>用户与权限</h3>
      <div style="color:#86909c;font-size:12px;margin-bottom:6px">只读视图 — 登录 / 用户 / 角色 / 权限</div>
      ${sec('服务器登录', d.logins, [['name', '登录名'], ['type', '类型'], ['disabled', '已禁用'], ['created', '创建日期'], ['host', '主机'], ['has_pwd', '有密码']])}
      ${sec('数据库用户', d.users, [['name', '用户名'], ['type', '类型'], ['default_schema', '默认架构'], ['login', '关联登录']])}
      ${sec('角色成员', d.roles, [['role', '角色'], ['member', '成员']])}
      ${sec('显式权限', d.permissions, [['grantee', '授权对象'], ['permission', '权限'], ['state', '状态'], ['object', '对象']])}
      <div class="acts"><button class="primary" onclick="closeModal()">关闭</button></div>`)
  } catch (e) {
    ui.toast('加载用户权限失败: ' + (e as Error).message, true)
    ui.showModal(`<h3>用户与权限</h3><div class="empty2" style="padding:20px">加载失败: ${esc((e as Error).message)}</div><div class="acts"><button onclick="closeModal()">关闭</button></div>`)
  }
}

// ================= 数据字典导出 =================
export async function exportSchemaDoc() {
  if (!connStore.connected) { ui.toast('请先连接数据库', true); return }
  try {
    const r = await fetch(API_BASE + '/api/export/schema', { headers: await authHeaders() })
    if (!r.ok) throw new Error('导出失败')
    downloadBlob(await r.blob(), 'data_dictionary.md')
    ui.toast('已导出数据字典')
  } catch (e) { ui.toast('导出失败: ' + (e as Error).message, true) }
}

// ---- 内部工具 ----
// P1-9 去重: authHeaders 统一从 client.ts 导入(原本地副本删除)
async function getDbUsers(): Promise<{
  supported: boolean; logins: Record<string, unknown>[]; users: Record<string, unknown>[];
  roles: Record<string, unknown>[]; permissions: Record<string, unknown>[]
}> {
  const h = await authHeaders()
  const r = await fetch(API_BASE + '/api/db-users', { headers: h })
  const d = await r.json().catch(() => ({}))
  if (d.error) throw new Error(d.error)
  return d
}


// ================= 表操作增强(对齐 Navicat 右键): 重命名/复制表/维护 =================
/** 重命名表(支持 schema) */
export function openRenameTable(s: string, t: string) {
  ui.showModal(`<h3>重命名表</h3>
    <div class="field"><label>原表名</label><div>${esc(s ? s + '.' : '')}${esc(t)}</div></div>
    <div class="field"><label>新表名</label><input id="rnNew" value="${esc(t)}" autofocus></div>
    <div class="acts"><button onclick="closeModal()">取消</button><button class="primary" onclick="window.__rnRun && window.__rnRun()">重命名</button></div>`)
  ;(window as unknown as Record<string, unknown>).__rnRun = async () => {
    const new_name = (document.getElementById('rnNew') as HTMLInputElement).value.trim()
    if (!new_name || new_name === t) { ui.toast('请输入不同的新表名', true); return }
    try {
      await alterTable({ s, t, action: 'rename_table', payload: { new_name } })
      ui.closeModal(); ui.toast('已重命名: ' + t + ' → ' + new_name)
    } catch (e) { ui.toast('重命名失败: ' + (e as Error).message, true) }
  }
}

/** 复制表(可带数据 / 仅结构) */
export function openCopyTable(s: string, t: string) {
  ui.showModal(`<h3>复制表</h3>
    <div class="field"><label>原表</label><div>${esc(s ? s + '.' : '')}${esc(t)}</div></div>
    <div class="field"><label>新表名</label><input id="cpNew" value="${esc(t)}_copy" autofocus></div>
    <div class="field"><label>复制选项</label><select id="cpMode">
      <option value="with">复制结构 + 数据</option>
      <option value="only">仅复制结构</option>
    </select></div>
    <div class="acts"><button onclick="closeModal()">取消</button><button class="primary" onclick="window.__cpRun && window.__cpRun()">复制</button></div>`)
  ;(window as unknown as Record<string, unknown>).__cpRun = async () => {
    const new_name = (document.getElementById('cpNew') as HTMLInputElement).value.trim()
    const with_data = (document.getElementById('cpMode') as HTMLSelectElement).value === 'with'
    if (!new_name || new_name === t) { ui.toast('请输入不同的新表名', true); return }
    try {
      const d = await alterTable({ s, t, action: 'copy_table', payload: { new_name, with_data } })
      ui.closeModal(); ui.toast('已复制 → ' + ((d as { new_table?: string }).new_table || new_name) + (with_data ? '(含数据)' : '(仅结构)'))
    } catch (e) { ui.toast('复制失败: ' + (e as Error).message, true) }
  }
}

/** 维护表(CHECK/OPTIMIZE/REPAIR/ANALYZE/VACUUM) */
export function openMaintainTable(s: string, t: string) {
  ui.showModal(`<h3>维护表 · ${esc(s ? s + '.' : '')}${esc(t)}</h3>
    <div class="field"><label>维护操作</label><select id="mtOp">
      <option value="check">检查完整性 (CHECK / PRAGMA integrity_check)</option>
      <option value="optimize">优化 (OPTIMIZE / VACUUM)</option>
      <option value="analyze">更新统计 (ANALYZE)</option>
      <option value="repair">修复 (REPAIR / VACUUM FULL)</option>
    </select></div>
    <p style="color:#86900c;font-size:12px">不同数据库支持的操作不同(根据方言自动映射)</p>
    <div id="mtResult" style="max-height:240px;overflow:auto;border:1px solid #eee;border-radius:6px;padding:6px;font-size:12px;display:none"></div>
    <div class="acts"><button onclick="closeModal()">关闭</button><button class="primary" onclick="window.__mtRun && window.__mtRun()">执行</button></div>`)
  ;(window as unknown as Record<string, unknown>).__mtRun = async () => {
    const op = (document.getElementById('mtOp') as HTMLSelectElement).value
    try {
      const d = await alterTable({ s, t, action: 'maintain', payload: { op } })
      const box = document.getElementById('mtResult') as HTMLDivElement
      box.style.display = 'block'
      const rows = (d as { rows?: Record<string, unknown>[] }).rows || []
      box.innerHTML = rows.length
        ? '<pre style="margin:0;white-space:pre-wrap">' + esc(JSON.stringify(rows, null, 2)) + '</pre>'
        : '<pre style="margin:0;color:#86900c">操作完成(无返回行, 多数 DDL 维护操作无输出)</pre>'
      ui.toast('维护完成')
    } catch (e) { ui.toast('维护失败: ' + (e as Error).message, true) }
  }
}

/** 新建表(轻量版: 输入表名 + 调用后端; 字段复杂设计走 TableDesignerModal) */
export function openNewTable(db: string, s: string) {
  ui.showModal(`<h3>新建表 · ${esc(db)}${s ? '.' + esc(s) : ''}</h3>
    <div class="field"><label>表名</label><input id="ntName" autofocus></div>
    <p style="color:#86900c;font-size:12px">将创建空表; 字段设计请打开表后右键「设计表」</p>
    <div class="acts"><button onclick="closeModal()">取消</button><button class="primary" onclick="window.__ntRun && window.__ntRun()">创建</button></div>`)
  ;(window as unknown as Record<string, unknown>).__ntRun = async () => {
    const name = (document.getElementById('ntName') as HTMLInputElement).value.trim()
    if (!name) { ui.toast('请填写表名', true); return }
    try {
      await alterTable({ s, t: name, action: 'create_table', payload: {} })
      ui.closeModal(); ui.toast('已创建表 ' + name)
    } catch (e) { ui.toast('创建失败: ' + (e as Error).message, true) }
  }
}

// ================= 固定表(快捷方式): localStorage 持久化 =================
// P1-9: 存储键集中到 constants/storage.ts
const PIN_KEY = STORAGE_KEYS.PINNED_TABLES

export interface PinnedTable { db: string; s: string; t: string }

export function getPinnedTables(): PinnedTable[] {
  try {
    const raw = localStorage.getItem(PIN_KEY)
    return raw ? JSON.parse(raw) as PinnedTable[] : []
  } catch { return [] }
}

export function togglePinnedTable(db: string, s: string, t: string): PinnedTable[] {
  const list = getPinnedTables()
  const idx = list.findIndex(p => p.db === db && p.s === (s || '') && p.t === t)
  if (idx >= 0) list.splice(idx, 1)
  else list.unshift({ db, s: s || '', t })
  try { localStorage.setItem(PIN_KEY, JSON.stringify(list)) } catch { /* */ }
  return list
}

export function isPinned(db: string, s: string, t: string): boolean {
  return getPinnedTables().some(p => p.db === db && p.s === (s || '') && p.t === t)
}
