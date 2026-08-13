// 工具向导集(阶段5 批2): 查询构建器/数据导入/测试数据/备份还原/schema对比/DB用户权限/数据字典导出
// 弹窗统一走 ui.openModal(name, props) 动态组件渲染(GenericModal 按 name 渲染注册组件),
// 彻底取代旧版 ui.showModal(html) + setTimeout 绑 onclick + window.__xxx 全局函数注入。
import { useUIStore } from '@/stores/ui'
import { errMsg } from '@/utils/err'
import { useConnectionStore } from '@/stores/connection'
import { useDatabaseStore } from '@/stores/database'
import { useTabStore } from '@/stores/tab'
import { API_BASE, authHeaders } from '@/api/client'
import { STORAGE_KEYS } from '@/constants/storage'

const ui = useUIStore()
const connStore = useConnectionStore()
const dbStore = useDatabaseStore()
const tabStore = useTabStore()

// P1-9 去重: esc/quoteIdent 统一收口到 sqlIdent.ts(单点维护方言规则), 此处 re-export 保持旧引用兼容
import { esc, quoteIdent, qident } from '@/utils/sqlIdent'
export { esc, quoteIdent, qident }

function downloadBlob(blob: Blob, filename: string) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  document.body.appendChild(a); a.click(); a.remove()
  URL.revokeObjectURL(a.href)
}

// ================= 查询构建器 =================
// 升级为独立 Vue 组件 QueryBuilderModal.vue。此处仅做入口(连接校验 + 打开模态)。
export function openQueryBuilder() {
  if (!connStore.connected) { ui.toast('请先连接数据库', true); return }
  const tables = dbStore.tables.filter(x => x.type !== 'View')
  if (!tables.length) { ui.toast('无可用表', true); return }
  ui.openQueryBuilder()
}

// ================= 数据导入向导 =================
// 逻辑(CSV 前端解析 / XLSX 后端解析 / 列映射)已迁入 ImportDataModal.vue。此处仅入口。
export function openImport(s?: string, t?: string) {
  const cur = tabStore.current
  const sc = s || (cur && cur.s)
  const tb = t || (cur && cur.t)
  if (!sc || !tb) { ui.toast('请先打开目标表', true); return }
  ui.openModal('ImportDataModal', { s: sc, t: tb })
}

// ================= 测试数据生成器 =================
// 逻辑已迁入 GenDataModal.vue。此处仅入口。
export function openGenData(s?: string, t?: string) {
  const cur = tabStore.current
  const sc = s || (cur && cur.s)
  const tb = t || (cur && cur.t)
  if (!sc || !tb) { ui.toast('请先打开目标表', true); return }
  ui.openModal('GenDataModal', { s: sc, t: tb })
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
  } catch (e) { ui.toast('备份失败: ' + errMsg(e), true) }
}
/** 还原: 上传 SQL 脚本 -> /api/restore(危险, 双确认)。逻辑已迁入 RestoreBackupModal.vue。 */
export function openRestore() {
  if (!connStore.connected) { ui.toast('请先连接数据库', true); return }
  ui.openModal('RestoreBackupModal')
}

// ================= schema diff 结构对比(跨连接) =================
// 逻辑已迁入 SchemaDiffModal.vue。此处仅入口。
export function openSchemaDiff(s: string, t: string) {
  ui.openModal('SchemaDiffModal', { s, t })
}

// ================= DB 用户与权限(只读视图) =================
// 逻辑(拉取 / 渲染)已迁入 DbUsersModal.vue。此处仅入口。
export async function openDbUsers() {
  if (!connStore.connected) { ui.toast('请先连接数据库', true); return }
  ui.openModal('DbUsersModal')
}

// ================= 数据字典导出 =================
export async function exportSchemaDoc() {
  if (!connStore.connected) { ui.toast('请先连接数据库', true); return }
  try {
    const r = await fetch(API_BASE + '/api/export/schema', { headers: await authHeaders() })
    if (!r.ok) throw new Error('导出失败')
    downloadBlob(await r.blob(), 'data_dictionary.md')
    ui.toast('已导出数据字典')
  } catch (e) { ui.toast('导出失败: ' + errMsg(e), true) }
}

// ================= 表操作增强(对齐 Navicat 右键): 重命名/复制表/维护 =================
// 逻辑已分别迁入 RenameTableModal / CopyTableModal / MaintainTableModal。此处仅入口。
export function openRenameTable(s: string, t: string) {
  ui.openModal('RenameTableModal', { s, t })
}
export function openCopyTable(s: string, t: string) {
  ui.openModal('CopyTableModal', { s, t })
}
export function openMaintainTable(s: string, t: string) {
  ui.openModal('MaintainTableModal', { s, t })
}
/** 新建表(轻量版: 输入表名 + 调用后端)。逻辑已迁入 NewTableModal.vue。 */
export function openNewTable(db: string, s: string) {
  ui.openModal('NewTableModal', { db, s })
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
