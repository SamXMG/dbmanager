<script setup lang="ts">
// 左侧对象树(阶段 2): 连接 -> 库 -> schema(智能省略) -> 类型分组 -> 对象
// 数据源 useDatabaseStore; 展开库懒加载 /api/objects; 双击对象开 tab
// 阶段5: 右键补全 表设计器/新建触发器/ER关系图/数据同步/结构同步(对齐旧版 tableCtxMenu)
import { computed, ref } from 'vue'
import { confirmDanger } from '@/utils/confirm'
import Icon from '@/components/Icon.vue'
import { useDatabaseStore, type DbObjects } from '@/stores/database'
import { useConnectionStore } from '@/stores/connection'
import { useTabStore } from '@/stores/tab'
import { useUIStore } from '@/stores/ui'
import { useSqlStore } from '@/stores/sql'
import { useAuthStore } from '@/stores/auth'
import type { CtxItem } from '@/stores/ui'
import { getColumns, getEr } from '@/api/database'
import { transferData, syncTable, alterTable } from '@/api/schema'
import { listConnections, type ConnMeta } from '@/api/connection'
import { API_BASE } from '@/api/client'
import { openImport, openGenData, openSchemaDiff, openDbUsers, exportSchemaDoc, openBackup, openRestore,
         openRenameTable, openCopyTable, openMaintainTable, openNewTable,
         togglePinnedTable, isPinned, getPinnedTables } from '@/utils/tools'

const dbStore = useDatabaseStore()
const connStore = useConnectionStore()
const tabStore = useTabStore()
const ui = useUIStore()
const sqlStore = useSqlStore()
const auth = useAuthStore()

const filter = ref('')
const loadingDb = ref('')
const pinnedList = ref(getPinnedTables())
function openPinned(p: { db: string; s: string; t: string }) {
  tabStore.openTable(p.s, p.t, p.db)
}
function unpin(p: { db: string; s: string; t: string }, e: MouseEvent) {
  e.stopPropagation()
  togglePinnedTable(p.db, p.s, p.t)
  pinnedList.value = getPinnedTables()
  ui.toast('已取消固定')
}

const connName = computed(() =>
  (connStore.conn && (connStore.conn.name || connStore.conn.server || connStore.conn.database)) || '连接')

const OBJ_ICON: Record<string, string> = { Table: 'table', View: 'view', Procedure: 'code', Function: 'code', Trigger: 'bell' }

// P1-9 去重: esc/quoteIdent 统一从 utils/sqlIdent.ts 导入(原组件内本地定义删除)
import { esc, quoteIdent } from '@/utils/sqlIdent'
async function copyText(t: string) {
  try { await navigator.clipboard.writeText(t); ui.toast('已复制: ' + t.slice(0, 60)) }
  catch { ui.toast('复制失败(浏览器限制)', true) }
}

/** 表/视图/过程/函数/触发器 右键菜单(Navicat 化) */
function onTableCtx(e: MouseEvent, db: string, s: string, t: string, type: string) {
  e.preventDefault()
  e.stopPropagation()
  const fullName = (s && s !== db ? s + '.' : '') + t
  const dbType = connStore.conn?.db_type || 'mysql'
  const w = auth.canWrite
  // 非表对象(存储过程/函数/触发器): 极简菜单(目前只有"编辑源码")
  if (type !== 'Table' && type !== 'View') {
    ui.showCtxMenu(e.clientX, e.clientY, [
      { label: '编辑源码', fn: () => ui.openRoutine(s, t, type) },
    ])
    return
  }
  // 通用项: 复制表名 / SELECT / INSERT 模板
  const pinned = isPinned(db, s, t)
  const items: CtxItem[] = [
    { label: '打开', fn: () => tabStore.openTable(s, t, db) },
  ]
  // --- 结构 ---
  items.push({ sep: true },
    { label: '设计表(可视化字段/索引/外键/触发器)', fn: () => ui.openDesigner(s, t) },
  )
  if (w) items.push({ label: '新建表...', fn: () => openNewTable(db, s) })
  // --- 维护 ---
  if (w) items.push({ sep: true },
    { label: '重命名表...', fn: () => openRenameTable(s, t) },
    { label: '复制表...', fn: () => openCopyTable(s, t) },
    { label: '维护表(检查/优化/分析/修复)', fn: () => openMaintainTable(s, t) },
    { label: '清空表(保留自增)', danger: true, fn: async () => {
      if (!await confirmDanger(`清空表 ${fullName}？\n保留自增(下次插入从原值继续)`)) return
      await execAlter(s, t, 'clear_table', {})
      ui.toast('已清空'); dbStore.loadObjects(db, true)
    }},
    { label: '截断表(重置自增)', danger: true, fn: async () => {
      if (!await confirmDanger(`截断表 ${fullName}？\n清空全部行并重置自增(SQLite 用 DELETE 模拟)`)) return
      await execAlter(s, t, 'truncate_table', {})
      ui.toast('已截断'); dbStore.loadObjects(db, true)
    }},
    { label: '删除表', danger: true, fn: async () => {
      if (!await confirmDanger(`⚠ 删除表 ${fullName}？\n该操作不可恢复！`)) return
      await execAlter(s, t, 'drop_table', {})
      ui.toast('已删除'); dbStore.loadObjects(db, true)
    }},
  )
  // --- 数据 ---
  items.push({ sep: true },
    { label: '导入向导...', fn: () => openImport(s, t) },
    { label: '生成测试数据...', fn: () => openGenData(s, t) },
  )
  if (type === 'Table') items.push({ label: '新建触发器', fn: () => sqlStore.newTrigger(s, t) })
  items.push({ label: '导出当前表(CSV/Excel)', fn: () => {
    const url = `${API_BASE}/api/export?s=${encodeURIComponent(s)}&t=${encodeURIComponent(t)}&where=&fmt=csv`
    window.open(url, '_blank')
  }})
  // --- 模型/同步 ---
  items.push({ sep: true },
    { label: 'ER 关系图', fn: () => openEr(s, t) },
  )
  if (type === 'Table') {
    items.push(
      { label: '结构对比...(跨连接)', fn: () => openSchemaDiff(s, t) },
      { label: '同步结构到其他连接', fn: () => openSchemaSync(s, t) },
      { label: '数据同步到其他库/连接', fn: () => openTransfer(db, s, t) },
    )
  }
  // --- 通用 ---
  items.push({ sep: true },
    { label: '复制表名', fn: () => copyText(fullName) },
    { label: '复制 SELECT SQL', fn: () => copyText('SELECT * FROM ' + quoteIdent(dbType, s) + '.' + quoteIdent(dbType, t)) },
  )
  if (type === 'Table') items.push({ label: '生成 INSERT 模板', fn: () => genInsertSql(db, s, t) })
  items.push({ sep: true },
    { label: '创建快捷方式(固定到树顶部)', fn: () => {
      const was = togglePinnedTable(db, s, t)
      pinnedList.value = getPinnedTables()
      ui.toast(was.find(p => p.db === db && p.s === (s || '') && p.t === t) ? '已取消固定' : '已固定(树顶部可看到)')
    }},
    { label: pinned ? '取消固定(已固定)' : '固定到顶部(快捷方式)', fn: () => {
      const was = togglePinnedTable(db, s, t)
      pinnedList.value = getPinnedTables()
      ui.toast(was.find(p => p.db === db && p.s === (s || '') && p.t === t) ? '已取消固定' : '已固定')
    }},
    { sep: true },
    { label: '调度任务...(定时备份)', fn: () => { ui.showTasks = true } },
    { label: '备份整库', fn: () => openBackup() },
    { label: '还原备份...', fn: () => openRestore() },
    { sep: true },
    { label: '用户与权限', fn: () => openDbUsers() },
    { label: '导出数据字典', fn: () => exportSchemaDoc() },
    { sep: true },
    { label: '刷新', fn: async () => {
      loadingDb.value = db
      await dbStore.loadObjects(db, true)
      loadingDb.value = ''
      ui.toast('已刷新')
    }},
  )
  ui.showCtxMenu(e.clientX, e.clientY, items)
}

/** 库右键菜单 */
function onDbCtx(e: MouseEvent, db: string) {
  e.preventDefault(); e.stopPropagation()
  ui.showCtxMenu(e.clientX, e.clientY, [
    { label: '新建查询', fn: () => { sqlStore.setSqlText(`-- 当前库: ${db}\nSELECT * FROM ` + db + '.LIMIT 100'); ui.switchView('sql') } },
    { label: '新建表...', fn: () => openNewTable(db, '') },
    { sep: true },
    { label: '备份整库', fn: () => openBackup() },
    { label: '还原备份...', fn: () => openRestore() },
    { label: '调度任务...(定时备份)', fn: () => { ui.showTasks = true } },
    { sep: true },
    { label: '导出数据字典', fn: () => exportSchemaDoc() },
    { label: '用户与权限', fn: () => openDbUsers() },
    { sep: true },
    { label: '刷新', fn: async () => {
      loadingDb.value = db
      await dbStore.loadObjects(db, true)
      loadingDb.value = ''
      ui.toast('已刷新')
    }},
  ])
}

/** 连接右键菜单 */
function onConnCtx(e: MouseEvent) {
  e.preventDefault(); e.stopPropagation()
  ui.showCtxMenu(e.clientX, e.clientY, [
    { label: '刷新对象树', fn: async () => {
      try {
        const conn = connStore.conn
        if (!conn) return
        const { listDatabases } = await import('@/api/connection')
        const dbs = await listDatabases({ db_type: conn.db_type, server: conn.server, port: conn.port,
                                         database: conn.database, uid: conn.uid, pwd: '' })
        dbStore.loadTables([], dbs || [])
        for (const db of dbStore.databases) await dbStore.loadObjects(db, true)
        ui.toast('已刷新')
      } catch (e) { ui.toast('刷新失败: ' + (e as Error).message, true) }
    }},
  ])
}

/** alter helper(本文件内复用) */
async function execAlter(s: string, t: string, action: string, payload: Record<string, unknown>) {
  return alterTable({ s, t, action, payload })
}

// ---- ER 关系图: /api/er -> 中心表 + 外键关联表 SVG(renderErSvg 翻译) ----
interface ErColumn { name: string; type?: string }
interface ErTable { schema: string; name: string; columns: ErColumn[]; pk: string[] }
interface ErRel { from_schema: string; from_table: string; to_schema: string; to_table: string; from_columns: string[]; to_columns: string[] }
interface DbObject { schema?: string; name: string; type?: string }

async function openEr(s: string, t: string) {
  try {
    const d = await getEr(s, t) as unknown as { tables: ErTable[]; relations: ErRel[] }
    const tables = d.tables || [], rels = d.relations || []
    if (!tables.length) { ui.toast('无表数据', true); return }
    const svg = genErSvg(s, t, tables, rels)
    ui.showModal(`<h3>ER 关系图 · ${esc(s ? s + '.' : '')}${esc(t)} <span style="color:#86909c;font-weight:400;font-size:12px">(${tables.length} 表 · ${rels.length} 关系)</span></h3>
      <div style="overflow:auto;max-height:70vh">${svg}</div>
      <div class="acts"><button class="primary" data-action="close">关闭</button></div>`)
  } catch (e) { ui.toast('ER 图加载失败: ' + (e as Error).message, true) }
}

function genErSvg(schema: string, name: string, tables: ErTable[], rels: ErRel[]): string {
  const TW = 190, TH = 26, TDH = 18, PAD = 30
  const centerKey = schema + '.' + name
  const ordered = [tables.find(t => (t.schema + '.' + t.name) === centerKey) || tables[0]]
    .concat(tables.filter(t => (t.schema + '.' + t.name) !== centerKey).sort((a, b) => b.columns.length - a.columns.length))
  const n = ordered.length
  const cols = Math.max(1, Math.ceil(Math.sqrt(n * 1.4)))
  const rowsN = Math.ceil(n / cols)
  const maxCols = Math.max(1, ...ordered.map(t => t.columns.length))
  const cellW = TW + PAD, cellH = 90 + maxCols * TDH + PAD
  const W = Math.max(600, cols * cellW + PAD), H = Math.max(400, rowsN * cellH + PAD)
  const pos: Record<string, { x: number; y: number }> = {}
  ordered.forEach((t, i) => {
    const cx = i % cols, cy = Math.floor(i / cols)
    pos[t.schema + '.' + t.name] = { x: PAD + cx * cellW, y: PAD + cy * cellH }
  })
  let box = ''
  ordered.forEach(t => {
    const p = pos[t.schema + '.' + t.name]
    const h = TH + t.columns.length * TDH
    box += `<rect x="${p.x}" y="${p.y}" width="${TW}" height="${h}" rx="6" fill="var(--panel, #fff)" stroke="#86909c"/>`
    box += `<rect x="${p.x}" y="${p.y}" width="${TW}" height="${TH}" rx="6" fill="#165dff" opacity="0.15"/>`
    box += `<text x="${p.x + 8}" y="${p.y + 17}" font-size="12" font-weight="600" fill="var(--text, #1d2129)">${esc(t.name)}</text>`
    t.columns.forEach((c, ci) => {
      const y = p.y + TH + 14 + ci * TDH
      const isPk = t.pk.includes(c.name)
      box += `<text x="${p.x + 8}" y="${y}" font-size="11" fill="${isPk ? '#f7ba1e' : 'var(--text2, #86909c)'}">${esc(c.name)}</text>`
      box += `<text x="${p.x + TW - 8}" y="${y}" font-size="10" text-anchor="end" fill="var(--text3, #999)">${esc(String(c.type || '').split('(')[0])}</text>`
    })
  })
  let lines = ''
  rels.forEach(r => {
    const from = pos[r.from_schema + '.' + r.from_table]
    const to = pos[r.to_schema + '.' + r.to_table]
    if (!from || !to) return
    const x1 = from.x + TW, y1 = from.y + TH + 8
    const x2 = to.x, y2 = to.y + TH + 8
    const mx = (x1 + x2) / 2
    lines += `<path d="M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}" fill="none" stroke="#165dff" stroke-width="1.2" marker-end="url(#erArrow)"/>`
    const lbl = (r.from_columns || []).map((c, i) => c + ' → ' + ((r.to_columns || [])[i] || '')).join(', ')
    lines += `<text x="${mx}" y="${(y1 + y2) / 2 - 4}" font-size="10" fill="#165dff" text-anchor="middle">${esc(lbl)}</text>`
  })
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" style="width:100%;min-width:${W}px;background:var(--panel, #fff);border-radius:8px">
    <defs><marker id="erArrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#165dff"/></marker></defs>
    ${box}${lines}</svg>`
}

// ---- 数据同步(跨库, 目标表须存在): /api/transfer ----
async function openTransfer(db: string, s: string, t: string) {
  const cur = connStore.conn?.database || ''
  const dbs = dbStore.databases.filter((d: string) => d && d !== cur)
  const opts = [cur, ...dbs]
  ui.showModal(`<h3>数据同步 · ${esc(s)}.${esc(t)}</h3>
    <div style="color:#86909c;font-size:12px;margin-bottom:10px">源表数据复制到目标表(同名列交集, 目标自增主键由数据库生成)</div>
    <div class="field"><label>目标库</label><select id="trDb">${opts.map(d => `<option value="${esc(d)}" ${d === cur ? 'selected' : ''}>${esc(d)}</option>`).join('')}</select></div>
    <div class="field"><label>目标表(须已存在)</label><input id="trTable" placeholder="如 ${esc(t)}_copy"></div>
    <p style="color:#d4660a;font-size:12px">⚠ 源表全部数据将插入目标表</p>
    <div class="acts"><button data-action="close">取消</button><button class="primary" id="trGo">开始同步</button></div>`)
  setTimeout(() => {
    const go = document.getElementById('trGo')
    if (go) go.onclick = async () => {
      const toDb = (document.getElementById('trDb') as HTMLSelectElement).value
      const toT = (document.getElementById('trTable') as HTMLInputElement).value.trim()
      if (!toT) { ui.toast('请填写目标表', true); return }
      try {
        const d = await transferData({ s, t, to_db: toDb, to_t: toT })
        ui.closeModal()
        ui.toast('已同步 ' + (d.transferred ?? 0) + ' 行数据')
      } catch (e) { ui.toast('同步失败: ' + (e as Error).message, true) }
    }
  }, 0)
}

// ---- 结构同步(跨连接, 同名表): /api/sync ----
async function openSchemaSync(s: string, t: string) {
  let conns: ConnMeta[] = []
  try { conns = await listConnections() } catch { /* */ }
  let html = `<h3>同步表数据 · ${esc(s)}.${esc(t)}</h3>
    <div style="color:#86909c;font-size:12px;margin-bottom:10px">把当前连接中该表数据复制到目标连接的<b>同名表</b>(按同名列匹配)</div>`
  if (!conns.length) {
    html += '<div class="empty2">请先在「我的连接」中保存目标连接</div>'
  } else {
    html += `<div class="field"><label>目标连接</label><select id="syncDst">${conns.map(c => `<option value="${esc(c.name)}">${esc(c.name)} (${esc(c.db_type)} · ${esc(c.server || '')})</option>`).join('')}</select></div>
      <div class="field"><label>模式</label><select id="syncMode"><option value="append">追加(不清空目标)</option><option value="replace">清空目标后复制</option></select></div>
      <div class="acts"><button data-action="close">取消</button><button class="primary" id="syncGo">开始同步</button></div>`
  }
  ui.showModal(html)
  setTimeout(() => {
    const go = document.getElementById('syncGo')
    if (go) go.onclick = async () => {
      const dstName = (document.getElementById('syncDst') as HTMLSelectElement).value
      const mode = (document.getElementById('syncMode') as HTMLSelectElement).value
      if (!dstName) { ui.toast('请选择目标连接', true); return }
      if (!await confirmDanger(`确认将 ${s}.${t} 同步到「${dstName}」(${mode === 'replace' ? '清空目标后复制' : '追加'})?`)) return
      const conn = connStore.conn
      const src = conn && conn.name ? { name: conn.name } : conn || {}
      try {
        const d = await syncTable({ src, dst: { name: dstName }, schema: s, table: t, mode })
        ui.closeModal()
        ui.toast('同步完成: 复制 ' + (d as { synced?: number }).synced + ' 行')
      } catch (e) { ui.toast('同步失败: ' + (e as Error).message, true) }
    }
  }, 0)
}

/** 生成 INSERT 模板(列名 + ? 占位, 对齐旧版 genInsertSql) */
async function genInsertSql(db: string, s: string, t: string) {
  try {
    const cols = await getColumns(s, t)
    if (!cols.length) { ui.toast('无字段', true); return }
    const dbType = connStore.conn?.db_type || 'mysql'
    const q = (n: string) => quoteIdent(dbType, n)
    copyText(`INSERT INTO ${q(s)}.${q(t)} (${cols.map(c => q(c.name)).join(', ')}) VALUES (${cols.map(() => '?').join(', ')});`)
  } catch (e) { ui.toast('生成失败: ' + (e as Error).message, true) }
}

// 搜索平铺(已加载对象)
const flatItems = computed(() => {
  const f = filter.value.toLowerCase()
  if (!f) return null
  const out: { db: string; s: string; name: string; type: string }[] = []
  for (const [db, obj] of Object.entries(dbStore.treeCache)) {
    ;(obj.tables || []).forEach(t => {
      if ((t.name || '').toLowerCase().includes(f)) out.push({ db, s: t.schema || '', name: t.name, type: t.type || 'Table' })
    })
    ;(obj.routines || []).forEach(r => {
      if ((r.name || '').toLowerCase().includes(f)) out.push({ db, s: r.schema || '', name: r.name, type: r.type })
    })
  }
  return out.slice(0, 200)
})

/** 某库的分组渲染数据: schema 列表(空=省略层) + 类型分组 */
function dbSchemas(db: string): string[] {
  const obj = dbStore.dbObjects(db)
  if (!obj) return []
  const all = [...obj.tables.map(t => t.schema || '(默认)'),
               ...(obj.routines || []).map(r => r.schema || '(默认)')]
  // 全部等于库名(MySQL 语义) -> 省略 schema 层
  if (all.every(s => s === db)) return []
  return [...new Set(all)]
}

function typeGroups(db: string, schema: string | null) {
  const obj = dbStore.dbObjects(db)
  if (!obj) return []
  const inSch = (arr: DbObject[]) =>
    schema ? arr.filter(x => (x.schema || '(默认)') === schema) : arr
  const tables = inSch(obj.tables).filter(t => t.type !== 'View')
  const views = inSch(obj.tables).filter(t => t.type === 'View')
  const routines = inSch(obj.routines || [])
  return [
    { label: '表', items: tables, icon: 'table' },
    { label: '视图', items: views, icon: 'view' },
    { label: '存储过程', items: routines.filter(r => r.type === 'Procedure'), icon: 'code' },
    { label: '函数', items: routines.filter(r => r.type === 'Function'), icon: 'code' },
    { label: '触发器', items: routines.filter(r => r.type === 'Trigger'), icon: 'bell' },
  ]
}

async function toggleDb(db: string) {
  if (!dbStore.expanded.has(db)) {
    loadingDb.value = db
    await dbStore.loadObjects(db)
    loadingDb.value = ''
  }
  dbStore.toggleDb(db)
  dbStore.switchDb(db) // SQL 目标库联动
}

function openObj(db: string, s: string, name: string, type: string) {
  if (type === 'Table' || type === 'View') tabStore.openTable(s, name, db)
  else if (type === 'Procedure' || type === 'Function' || type === 'Trigger') {
    ui.openRoutine(s, name, type)
  }
}
</script>

<template>
  <div class="obj-tree">
    <div class="s-head">
      <input v-model="filter" placeholder="搜索表/集合/键..." />
      <div v-if="pinnedList.length" class="pinned-bar">
        <span class="pin-label"><Icon name="pin" :size="13"/> 固定</span>
        <span v-for="p in pinnedList" :key="p.db + '.' + p.s + '.' + p.t" class="pin-item"
              :title="p.db + '.' + p.s + '.' + p.t + ' (右键取消)'"
              @dblclick="openPinned(p)" @contextmenu.prevent="unpin(p, $event)">
          {{ p.s && p.s !== p.db ? p.s + '.' : '' }}{{ p.t }}
          <span class="x" @click.stop="unpin(p, $event)">×</span>
        </span>
      </div>
    </div>
    <div class="list">
      <!-- 搜索平铺模式 -->
      <template v-if="flatItems">
        <div v-for="(it, i) in flatItems" :key="i" class="item"
             :title="it.db + '.' + (it.s ? it.s + '.' : '') + it.name"
             @dblclick="openObj(it.db, it.s, it.name, it.type)"
             @contextmenu="onTableCtx($event, it.db, it.s, it.name, it.type)">
          <span><Icon :name="OBJ_ICON[it.type] || 'table'" :size="13" /> {{ it.s && it.s !== it.db ? it.s + '.' : '' }}{{ it.name }}</span>
          <span class="ty">{{ it.type }}</span>
        </div>
        <div v-if="!flatItems.length" class="empty2">无匹配对象</div>
      </template>

      <!-- 树形模式 -->
      <template v-else>
        <div class="tnode root" @contextmenu.prevent="onConnCtx($event)">
          <span class="caret" :class="{ open: dbStore.expanded.size > 0 }">▾</span>
          <span><Icon name="link" :size="13"/> {{ connName }}</span>
        </div>
        <div v-if="!dbStore.databases.length" class="empty2" style="padding:8px 12px">
          无库信息(展开连接库: {{ connStore.conn?.database || '-' }})
        </div>

        <template v-for="db in dbStore.databases" :key="db">
          <div class="tnode lvl1" @click="toggleDb(db)" @contextmenu.prevent="onDbCtx($event, db)">
            <span class="caret" :class="{ open: dbStore.expanded.has(db) }">▾</span>
            <span><Icon name="database" :size="14" /> {{ db }}</span>
            <span v-if="loadingDb === db" class="loading">…</span>
          </div>

          <div v-if="dbStore.expanded.has(db) && dbStore.dbObjects(db)" class="tbl-group-body">
            <!-- 无 schema 层(MySQL) -->
            <template v-if="!dbSchemas(db).length">
              <div v-for="g in typeGroups(db, null)" :key="g.label" class="grp">
                <div class="grp-head"><Icon :name="g.icon" :size="13" /> {{ g.label }} ({{ g.items.length }})</div>
                <div v-if="g.items.length" class="grp-body">
                  <div v-for="t in g.items" :key="t.name" class="item"
                       :title="db + '.' + (t.schema ? t.schema + '.' : '') + t.name"
                       @dblclick="openObj(db, t.schema || '', t.name, (t.type || 'Table'))"
                       @contextmenu="onTableCtx($event, db, t.schema || '', t.name, (t.type || 'Table'))">
                    <span><Icon :name="t.type === 'View' ? 'view' : 'table'" :size="13" /> {{ t.name }}</span>
                    <span class="ty">{{ (t.type || 'Table') }}</span>
                  </div>
                </div>
                <div v-else class="empty2" style="padding:2px 12px">无</div>
              </div>
            </template>
            <!-- 有 schema 层(MSSQL dbo/guest) -->
            <template v-else>
              <template v-for="sch in dbSchemas(db)" :key="sch">
                <div class="tnode lvl2">
                  <span class="caret open">▾</span>
                  <span><Icon name="folder" :size="13" /> {{ sch }}</span>
                </div>
                <div class="tbl-group-body">
                  <div v-for="g in typeGroups(db, sch)" :key="g.label" class="grp">
                    <div class="grp-head"><Icon :name="g.icon" :size="13" /> {{ g.label }} ({{ g.items.length }})</div>
                    <div v-if="g.items.length" class="grp-body">
                      <div v-for="t in g.items" :key="t.name" class="item"
                           @dblclick="openObj(db, sch === '(默认)' ? '' : sch, t.name, (t.type || 'Table'))"
                           @contextmenu="onTableCtx($event, db, sch === '(默认)' ? '' : sch, t.name, (t.type || 'Table'))">
                        <span><Icon :name="t.type === 'View' ? 'view' : 'table'" :size="13" /> {{ t.name }}</span>
                        <span class="ty">{{ (t.type || 'Table') }}</span>
                      </div>
                    </div>
                    <div v-else class="empty2" style="padding:2px 12px">无</div>
                  </div>
                </div>
              </template>
            </template>
          </div>
          <div v-else-if="dbStore.expanded.has(db)" class="empty2" style="padding:4px 12px">加载中...</div>
        </template>
      </template>
    </div>
  </div>
</template>

<style scoped>
.obj-tree { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.s-head { padding: 6px 8px; }
.s-head input { width: 100%; box-sizing: border-box; padding: 5px 8px; border: 1px solid var(--border, #e4e7ed); border-radius: 6px; background: transparent; color: inherit; }
.pinned-bar { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; align-items: center; }
.pin-label { font-size: 11px; color: #86909c; margin-right: 2px; }
.pin-item { display: inline-flex; align-items: center; gap: 3px; padding: 2px 6px; background: var(--bg-info, #e6f1fb); color: var(--color-info, #185fa5); border-radius: 10px; font-size: 12px; cursor: pointer; }
.pin-item:hover { background: #d3e6f7; }
.pin-item .x { font-weight: 700; opacity: 0.6; padding: 0 2px; }
.pin-item .x:hover { opacity: 1; color: #d4660a; }
.list { flex: 1; overflow: auto; min-height: 0; }
.tnode { display: flex; align-items: center; gap: 4px; padding: 3px 8px; cursor: pointer; font-size: 13px; }
.tnode:hover { background: rgba(128,128,128,0.08); }
.tnode.root { font-weight: 600; }
.tnode.lvl1 { padding-left: 14px; }
.tnode.lvl2 { padding-left: 28px; }
.caret { font-size: 10px; color: #999; transition: transform .12s; display: inline-block; }
.caret.open { transform: rotate(90deg); }
.loading { color: #999; font-size: 12px; }
.tbl-group-body { padding-left: 14px; }
.grp { margin: 2px 0; }
.grp-head { padding: 2px 8px; font-size: 12px; color: var(--text2, #86909c); }
.grp-body { }
.item { display: flex; align-items: center; gap: 6px; padding: 3px 10px; cursor: pointer; font-size: 13px; }
.item:hover { background: rgba(128,128,128,0.08); }
.item .ty { margin-left: auto; font-size: 11px; color: #999; flex-shrink: 0; }
.empty2 { color: #999; font-size: 12px; padding: 6px 10px; }
</style>
