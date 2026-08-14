<script setup lang="ts">
// 左侧对象树(阶段 2): 连接 -> 库 -> schema(智能省略) -> 类型分组 -> 对象
// 数据源 useDatabaseStore; 展开库懒加载 /api/objects; 双击对象开 tab
// 阶段5: 右键补全 表设计器/新建触发器/ER关系图/数据同步/结构同步(对齐旧版 tableCtxMenu)
import { computed, ref } from 'vue'
import { errMsg } from '@/utils/err'
import { confirmDanger } from '@/utils/confirm'
import { tr } from '@/i18n'
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
  ui.toast(tr('tree.unpinned'))
}

const connName = computed(() =>
  (connStore.conn && (connStore.conn.name || connStore.conn.server || connStore.conn.database)) || tr('header.notLoggedIn'))

const OBJ_ICON: Record<string, string> = { Table: 'table', View: 'view', Procedure: 'code', Function: 'code', Trigger: 'bell' }

// P1-9 去重: esc/quoteIdent 统一从 utils/sqlIdent.ts 导入(原组件内本地定义删除)
import { esc, quoteIdent } from '@/utils/sqlIdent'
async function copyText(txt: string) {
  try { await navigator.clipboard.writeText(txt); ui.toast(tr('tree.copied', { text: txt.slice(0, 60) })) }
  catch { ui.toast(tr('tree.copyFailed'), true) }
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
      { label: tr('ctx.editSource'), fn: () => ui.openRoutine(s, t, type) },
    ])
    return
  }
  // 通用项: 复制表名 / SELECT / INSERT 模板
  const pinned = isPinned(db, s, t)
  const items: CtxItem[] = [
    { label: tr('ctx.open'), fn: () => tabStore.openTable(s, t, db) },
  ]
  // --- 结构 ---
  items.push({ sep: true },
    { label: tr('ctx.designTable'), fn: () => ui.openDesigner(s, t) },
  )
  if (w) items.push({ label: tr('ctx.newTable'), fn: () => openNewTable(db, s) })
  // --- 维护 ---
  if (w) items.push({ sep: true },
    { label: tr('ctx.renameTable'), fn: () => openRenameTable(s, t) },
    { label: tr('ctx.copyTable'), fn: () => openCopyTable(s, t) },
    { label: tr('ctx.maintainTable'), fn: () => openMaintainTable(s, t) },
    { label: tr('ctx.clearTable'), danger: true, fn: async () => {
      if (!await confirmDanger(tr('confirm.clearTable', { name: fullName }))) return
      await execAlter(s, t, 'clear_table', {})
      ui.toast(tr('tree.cleared')); dbStore.loadObjects(db, true)
    }},
    { label: tr('ctx.truncateTable'), danger: true, fn: async () => {
      if (!await confirmDanger(tr('confirm.truncateTable', { name: fullName }))) return
      await execAlter(s, t, 'truncate_table', {})
      ui.toast(tr('tree.truncated')); dbStore.loadObjects(db, true)
    }},
    { label: tr('ctx.dropTable'), danger: true, fn: async () => {
      if (!await confirmDanger(tr('confirm.dropTable', { name: fullName }))) return
      await execAlter(s, t, 'drop_table', {})
      ui.toast(tr('tree.deleted')); dbStore.loadObjects(db, true)
    }},
  )
  // --- 数据 ---
  items.push({ sep: true },
    { label: tr('ctx.importWizard'), fn: () => openImport(s, t) },
    { label: tr('ctx.genTestData'), fn: () => openGenData(s, t) },
  )
  if (type === 'Table') items.push({ label: tr('ctx.newTrigger'), fn: () => sqlStore.newTrigger(s, t) })
  items.push({ label: tr('ctx.exportTable'), fn: () => {
    const url = `${API_BASE}/api/export?s=${encodeURIComponent(s)}&t=${encodeURIComponent(t)}&where=&fmt=csv`
    window.open(url, '_blank')
  }})
  // --- 模型/同步 ---
  items.push({ sep: true },
    { label: tr('ctx.erDiagram'), fn: () => openEr(s, t) },
  )
  if (type === 'Table') {
    items.push(
      { label: tr('ctx.schemaDiff'), fn: () => openSchemaDiff(s, t) },
      { label: tr('ctx.syncStructure'), fn: () => openSchemaSync(s, t) },
      { label: tr('ctx.syncData'), fn: () => openTransfer(db, s, t) },
    )
  }
  // --- 通用 ---
  items.push({ sep: true },
    { label: tr('ctx.copyTableName'), fn: () => copyText(fullName) },
    { label: tr('ctx.copySelectSql'), fn: () => copyText('SELECT * FROM ' + quoteIdent(dbType, s) + '.' + quoteIdent(dbType, t)) },
  )
  if (type === 'Table') items.push({ label: tr('ctx.genInsert'), fn: () => genInsertSql(db, s, t) })
  items.push({ sep: true },
    { label: tr('ctx.createShortcut'), fn: () => {
      const was = togglePinnedTable(db, s, t)
      pinnedList.value = getPinnedTables()
      ui.toast(was.find(p => p.db === db && p.s === (s || '') && p.t === t) ? tr('tree.unpinned') : tr('tree.pinnedTop'))
    }},
    { label: pinned ? tr('tree.unpin') : tr('tree.pinTop'), fn: () => {
      const was = togglePinnedTable(db, s, t)
      pinnedList.value = getPinnedTables()
      ui.toast(was.find(p => p.db === db && p.s === (s || '') && p.t === t) ? tr('tree.unpinned') : tr('tree.pinned'))
    }},
    { sep: true },
    { label: tr('ctx.scheduleTask'), fn: () => { ui.showTasks = true } },
    { label: tr('ctx.backupDb'), fn: () => openBackup() },
    { label: tr('ctx.restoreBackup'), fn: () => openRestore() },
    { sep: true },
    { label: tr('ctx.usersPermissions'), fn: () => openDbUsers() },
    { label: tr('ctx.exportDict'), fn: () => exportSchemaDoc() },
    { sep: true },
    { label: tr('ctx.refresh'), fn: async () => {
      loadingDb.value = db
      await dbStore.loadObjects(db, true)
      loadingDb.value = ''
      ui.toast(tr('tree.refreshed'))
    }},
  )
  ui.showCtxMenu(e.clientX, e.clientY, items)
}

/** 库右键菜单 */
function onDbCtx(e: MouseEvent, db: string) {
  e.preventDefault(); e.stopPropagation()
  ui.showCtxMenu(e.clientX, e.clientY, [
    { label: tr('ctx.newQuery'), fn: () => { sqlStore.setSqlText(`-- 当前库: ${db}\nSELECT * FROM ` + db + '.LIMIT 100'); ui.switchView('sql') } },
    { label: tr('ctx.newTable'), fn: () => openNewTable(db, '') },
    { sep: true },
    { label: tr('ctx.backupDb'), fn: () => openBackup() },
    { label: tr('ctx.restoreBackup'), fn: () => openRestore() },
    { label: tr('ctx.scheduleTask'), fn: () => { ui.showTasks = true } },
    { sep: true },
    { label: tr('ctx.exportDict'), fn: () => exportSchemaDoc() },
    { label: tr('ctx.usersPermissions'), fn: () => openDbUsers() },
    { sep: true },
    { label: tr('ctx.refresh'), fn: async () => {
      loadingDb.value = db
      await dbStore.loadObjects(db, true)
      loadingDb.value = ''
      ui.toast(tr('tree.refreshed'))
    }},
  ])
}

/** 连接右键菜单 */
function onConnCtx(e: MouseEvent) {
  e.preventDefault(); e.stopPropagation()
  ui.showCtxMenu(e.clientX, e.clientY, [
    { label: tr('ctx.refreshTree'), fn: async () => {
      try {
        const conn = connStore.conn
        if (!conn) return
        const { listDatabases } = await import('@/api/connection')
        const dbs = await listDatabases({ db_type: conn.db_type, server: conn.server, port: conn.port,
                                         database: conn.database, uid: conn.uid, pwd: '' })
        dbStore.loadTables([], dbs || [])
        for (const db of dbStore.databases) await dbStore.loadObjects(db, true)
        ui.toast(tr('tree.refreshed'))
      } catch (e) { ui.toast(tr('tree.refreshFailed', { msg: errMsg(e) }), true) }
    }},
  ])
}

/** alter helper(本文件内复用) */
async function execAlter(s: string, t: string, action: string, payload: Record<string, unknown>) {
  return alterTable({ s, t, action, payload })
}

// ---- ER 关系图: 走 ERDiagramModal 动态组件(getEr 数据 + SVG 均在该组件内渲染, 无注入) ----
function openEr(s: string, t: string) {
  ui.openModal('ERDiagramModal', { s, t })
}

// ---- 数据同步(跨库 / 跨连接同名表): 两种模式整合进 SyncModal 动态组件 ----
function openTransfer(_db: string, s: string, t: string) {
  ui.openModal('SyncModal', { s, t })
}

// ---- 结构同步(跨连接, 同名表): 同走 SyncModal ----
function openSchemaSync(s: string, t: string) {
  ui.openModal('SyncModal', { s, t })
}

/** 生成 INSERT 模板(列名 + ? 占位, 对齐旧版 genInsertSql) */
async function genInsertSql(db: string, s: string, t: string) {
  try {
    const cols = await getColumns(s, t)
    if (!cols.length) { ui.toast(tr('tree.noColumns'), true); return }
    const dbType = connStore.conn?.db_type || 'mysql'
    const q = (n: string) => quoteIdent(dbType, n)
    copyText(`INSERT INTO ${q(s)}.${q(t)} (${cols.map(c => q(c.name)).join(', ')}) VALUES (${cols.map(() => '?').join(', ')});`)
  } catch (e) { ui.toast(tr('tree.genFailed', { msg: errMsg(e) }), true) }
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
  const all = [...obj.tables.map(t => t.schema || tr('tree.defaultSchema')),
               ...(obj.routines || []).map(r => r.schema || tr('tree.defaultSchema'))]
  // 全部等于库名(MySQL 语义) -> 省略 schema 层
  if (all.every(s => s === db)) return []
  return [...new Set(all)]
}

function typeGroups(db: string, schema: string | null) {
  const obj = dbStore.dbObjects(db)
  if (!obj) return []
  const inSch = (arr: Array<{ schema?: string; name: string; type?: string }>) =>
    schema ? arr.filter(x => (x.schema || tr('tree.defaultSchema')) === schema) : arr
  const tables = inSch(obj.tables).filter(t => t.type !== 'View')
  const views = inSch(obj.tables).filter(t => t.type === 'View')
  const routines = inSch(obj.routines || [])
  return [
    { label: tr('tree.groupTable'), items: tables, icon: 'table' },
    { label: tr('tree.groupView'), items: views, icon: 'view' },
    { label: tr('tree.groupProc'), items: routines.filter(r => r.type === 'Procedure'), icon: 'code' },
    { label: tr('tree.groupFunc'), items: routines.filter(r => r.type === 'Function'), icon: 'code' },
    { label: tr('tree.groupTrigger'), items: routines.filter(r => r.type === 'Trigger'), icon: 'bell' },
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
      <input v-model="filter" :placeholder="tr('tree.searchPlaceholder')" />
      <div v-if="pinnedList.length" class="pinned-bar">
        <span class="pin-label"><Icon name="pin" :size="13"/> {{ tr('tree.pinned') }}</span>
        <span v-for="p in pinnedList" :key="p.db + '.' + p.s + '.' + p.t" class="pin-item"
              :title="p.db + '.' + p.s + '.' + p.t + tr('tree.rightClickToUnpin')"
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
        <div v-if="!flatItems.length" class="empty2">{{ tr('tree.noMatch') }}</div>
      </template>

      <!-- 树形模式 -->
      <template v-else>
        <div class="tnode root" @contextmenu.prevent="onConnCtx($event)">
          <span class="caret" :class="{ open: dbStore.expanded.size > 0 }">▾</span>
          <span><Icon name="link" :size="13"/> {{ connName }}</span>
        </div>
        <div v-if="!dbStore.databases.length" class="empty2" style="padding:8px 12px">
          {{ tr('tree.noDbInfo', { db: connStore.conn?.database || '-' }) }}
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
                <div v-else class="empty2" style="padding:2px 12px">{{ tr('tree.none') }}</div>
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
                           @dblclick="openObj(db, sch === tr('tree.defaultSchema') ? '' : sch, t.name, (t.type || 'Table'))"
                           @contextmenu="onTableCtx($event, db, sch === tr('tree.defaultSchema') ? '' : sch, t.name, (t.type || 'Table'))">
                        <span><Icon :name="t.type === 'View' ? 'view' : 'table'" :size="13" /> {{ t.name }}</span>
                        <span class="ty">{{ (t.type || 'Table') }}</span>
                      </div>
                    </div>
                    <div v-else class="empty2" style="padding:2px 12px">{{ tr('tree.none') }}</div>
                  </div>
                </div>
              </template>
            </template>
          </div>
          <div v-else-if="dbStore.expanded.has(db)" class="empty2" style="padding:4px 12px">{{ tr('tree.loading') }}</div>
        </template>
      </template>
    </div>
  </div>
</template>

<style scoped>
.obj-tree { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.s-head { padding: 6px 8px; }
.s-head input { width: 100%; box-sizing: border-box; padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px; background: transparent; color: inherit; }
.pinned-bar { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; align-items: center; }
.pin-label { font-size: 11px; color: var(--text3); margin-right: 2px; }
.pin-item { display: inline-flex; align-items: center; gap: 3px; padding: 2px 6px; background: var(--primary-bg); color: var(--primary); border-radius: 10px; font-size: 12px; cursor: pointer; }
.pin-item:hover { background: var(--primary-bg); filter: brightness(0.94); }
.pin-item .x { font-weight: 700; opacity: 0.6; padding: 0 2px; }
.pin-item .x:hover { opacity: 1; color: var(--warning); }
.list { flex: 1; overflow: auto; min-height: 0; }
.tnode { display: flex; align-items: center; gap: 4px; padding: 3px 8px; cursor: pointer; font-size: 13px; }
.tnode:hover { background: rgba(128,128,128,0.08); }
.tnode.root { font-weight: 600; }
.tnode.lvl1 { padding-left: 14px; }
.tnode.lvl2 { padding-left: 28px; }
.caret { font-size: 10px; color: var(--text3); transition: transform .12s; display: inline-block; }
.caret.open { transform: rotate(90deg); }
.loading { color: var(--text3); font-size: 12px; }
.tbl-group-body { padding-left: 14px; }
.grp { margin: 2px 0; }
.grp-head { padding: 2px 8px; font-size: 12px; color: var(--text2, var(--text3)); }
.grp-body { }
.item { display: flex; align-items: center; gap: 6px; padding: 3px 10px; cursor: pointer; font-size: 13px; }
.item:hover { background: rgba(128,128,128,0.08); }
.item .ty { margin-left: auto; font-size: 11px; color: var(--text3); flex-shrink: 0; }
.empty2 { color: var(--text3); font-size: 12px; padding: 6px 10px; }
</style>
