<script setup lang="ts">
// 数据网格: 排序/筛选(列头面板)/行选中(Ctrl/Shift/全选)/单元格编辑/分页/右键/列宽拖拽记忆/类型着色
// 对应旧版 js/grid.js 全量网格功能
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { confirmDanger } from '@/utils/confirm'
import { tr } from '@/i18n'
import { useGridStore, type GridColumn } from '@/stores/grid'
import { useTabStore } from '@/stores/tab'
import { useUIStore } from '@/stores/ui'
import { useAuthStore } from '@/stores/auth'
import { useConnectionStore } from '@/stores/connection'
import type { CtxItem } from '@/stores/ui'

const grid = useGridStore()
const tab = useTabStore()
const ui = useUIStore()
const auth = useAuthStore()
const connStore = useConnectionStore()

// 激活标签变化: 切走保存快照 -> 切回立即恢复(不重新请求) -> 无 tab 清空表格
let prevTabId: number | null = null
watch(() => tab.activeId, (id, oldId) => {
  if (oldId != null && oldId !== id) grid.saveSnapshot(oldId)
  if (id == null) {
    grid.reset()
    prevTabId = null
    return
  }
  loadColWidths()
  if (!grid.restoreSnapshot(id)) grid.loadData(1)
  prevTabId = id
})
watch(() => tab.tabs.map(t => t.id), ids => { grid.pruneSnapshots(ids) })
onMounted(() => {
  loadColWidths()
  if (tab.activeId != null && !grid.restoreSnapshot(tab.activeId)) grid.loadData(1)
  else if (tab.activeId == null) grid.reset()
})

function fmt(v: unknown): string {
  if (v === null || v === undefined) return ''
  if (v instanceof Date) return v.toISOString().slice(0, 19).replace('T', ' ')
  if (typeof v === 'object') {
    try { return JSON.stringify(v) } catch { return String(v) }
  }
  return String(v)
}

// ---- 类型着色(对齐旧 cellTypeClass): 数字右对齐 / 日期 / 布尔 ----
const NUM_RE = /int|decimal|numeric|float|double|real|money|number|bigint|smallint|tinyint/i
const DATE_RE = /date|time|timestamp/i
function cellClass(c: GridColumn, v: unknown): string {
  const t = c.type || ''
  if (v === null || v === undefined) return 'cell-null'
  if (NUM_RE.test(t)) return 'cell-num'
  if (DATE_RE.test(t)) return 'cell-date'
  if (typeof v === 'boolean' || t === 'bool' || t === 'boolean') return 'cell-bool'
  return ''
}

// ---- 排序 ----
function onHeadClick(col: string) { grid.setSort(col) }
function sortIcon(col: string): string {
  if (grid.sort?.col !== col) return '↕'
  return grid.sort.dir === 'asc' ? '▲' : '▼'
}

// ---- 列筛选(列头 ▾ 弹面板: op + 值) ----
// 符号(op 码)原样显示, 中文标签改为 i18n key, 模板内 tr() 翻译(随语言切换)
const FILTER_OPS = [
  ['eq', '='], ['ne', '≠'], ['gt', '>'], ['ge', '≥'], ['lt', '<'], ['le', '≤'],
  ['contains', 'filter.contains'], ['starts', 'filter.startsWith'], ['ends', 'filter.ends'], ['isnull', 'filter.isnull'], ['isnotnull', 'filter.isnotnull'],
] as const
const filterPop = ref<{ col: string; x: number; y: number } | null>(null)
const filterOp = ref('contains')
const filterVal = ref('')
function openFilter(col: string, e: MouseEvent) {
  e.stopPropagation()
  const f = grid.filters[col]
  filterOp.value = f?.op || 'contains'
  filterVal.value = f?.val || ''
  filterPop.value = { col, x: Math.min(e.clientX, window.innerWidth - 240), y: e.clientY + 8 }
}
function applyFilter() {
  if (!filterPop.value) return
  grid.setFilter(filterPop.value.col, filterOp.value, filterVal.value)
  filterPop.value = null
}
function clearFilter() {
  if (!filterPop.value) return
  grid.setFilter(filterPop.value.col, '', '')
  filterPop.value = null
}
function onDocClick() { filterPop.value = null }
onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))

// ---- 选中 ----
function onRowClick(i: number, e: MouseEvent) {
  grid.selectRow(i, e.ctrlKey || e.metaKey, e.shiftKey)
}
function onRowDblClick(i: number) {
  if (grid.columns.length) grid.startEdit(i, 0)
}
function toggleAll(e: Event) {
  const checked = (e.target as HTMLInputElement).checked
  if (checked) {
    grid.rows.forEach((_, i) => grid.selectedRows.add(i))
  } else {
    grid.selectedRows = new Set()
  }
}
const allChecked = () => grid.rows.length > 0 && grid.selectedRows.size === grid.rows.length

// ---- 编辑 ----
let editVal = ''
function onEditInput(e: Event) { editVal = (e.target as HTMLInputElement).value }
async function onEditCommit() {
  const ok = await grid.commitEdit(editVal)
  if (!ok) ui.toast(tr('grid.saveFailed'), true)
}

// ---- 分页 ----
// total=-1(count 超时/失败): 显示总数未知并禁用翻页(对齐旧版); 正常才计算页数
const pageCount = () => Math.max(1, Math.ceil((grid.total > 0 ? grid.total : 1) / grid.pageSize))
const totalKnown = computed(() => grid.total >= 0)
function goPage(p: number) {
  if (p < 1 || p > pageCount() || !totalKnown.value) return
  grid.loadData(p)
}

// ---- 基础版虚拟滚动(大表 >300 行/页时只渲染可视区, 固定行高 32px) ----
// P1-9: 视口高度改为 dgScroll.clientHeight 实测值 + ResizeObserver 自适应(原硬编码 900px)
const ROW_H = 32
const VIRTUAL_THRESHOLD = 300
const scrollTop = ref(0)
const dgScroll = ref<HTMLElement | null>(null)
const viewH = ref(900)
let _resizeObs: ResizeObserver | null = null
function updateViewH() {
  if (dgScroll.value) viewH.value = dgScroll.value.clientHeight || 900
}
onMounted(() => {
  updateViewH()
  if (dgScroll.value && typeof ResizeObserver !== 'undefined') {
    _resizeObs = new ResizeObserver(updateViewH)
    _resizeObs.observe(dgScroll.value)
  }
})
onBeforeUnmount(() => { _resizeObs?.disconnect(); _resizeObs = null })
const virtualMode = computed(() => grid.rows.length > VIRTUAL_THRESHOLD)
interface VRow { r: Record<string, unknown>; i: number }
const viewRows = computed<VRow[]>(() => {
  const rows = grid.rows
  if (!virtualMode.value) return rows.map((r, i) => ({ r, i }))
  const start = Math.max(0, Math.floor(scrollTop.value / ROW_H) - 10)
  const end = Math.min(rows.length, Math.ceil((scrollTop.value + viewH.value) / ROW_H) + 10)
  const out: VRow[] = []
  for (let i = start; i < end; i++) out.push({ r: rows[i], i })
  return out
})
const topPadH = computed(() => (viewRows.value[0]?.i || 0) * ROW_H)
const botPadH = computed(() => {
  const last = viewRows.value[viewRows.value.length - 1]
  return last ? (grid.rows.length - last.i - 1) * ROW_H : 0
})
function onScroll() {
  if (dgScroll.value) scrollTop.value = dgScroll.value.scrollTop
}

// ---- 列宽拖拽 + 记忆(表维度 localStorage, 对齐旧 colWKey/saveColWidth/applyColWidths) ----
const colW = reactive<Record<string, string>>({})
function colKey(): string {
  const cur = tab.current
  const conn = connStore.conn
  if (!cur) return ''
  return 'dbm_colw|' + (conn?.db_type || '') + '|' + (conn?.server || '') + '|' + (conn?.database || '') + '|' + cur.s + '|' + cur.t
}
function loadColWidths() {
  for (const k of Object.keys(colW)) delete colW[k]
  const key = colKey()
  if (!key) return
  try {
    const saved = JSON.parse(localStorage.getItem(key) || '{}') as Record<string, number>
    for (const [n, w] of Object.entries(saved)) if (w > 0) colW[n] = w + 'px'
  } catch { /* */ }
}
function startResize(e: MouseEvent, colName: string) {
  e.preventDefault(); e.stopPropagation()
  const startX = e.clientX
  const startW = colW[colName] ? parseInt(colW[colName]) : (document.querySelector(`th[data-c="${CSS.escape(colName)}"]`) as HTMLElement)?.offsetWidth || 120
  const onMove = (ev: MouseEvent) => {
    colW[colName] = Math.max(60, startW + ev.clientX - startX) + 'px'
  }
  const onUp = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
    const key = colKey()
    if (!key) return
    try {
      const saved = JSON.parse(localStorage.getItem(key) || '{}') as Record<string, number>
      saved[colName] = parseInt(colW[colName])
      localStorage.setItem(key, JSON.stringify(saved))
    } catch { /* */ }
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

// ---- 右键菜单(对齐旧版 cellCtxMenu/rowCtxMenu) ----
// P1-9 去重: esc 统一从 utils/sqlIdent.ts 导入(原组件内本地定义删除)
import { esc } from '@/utils/sqlIdent'
async function copyText(txt: string, okMsg = tr('grid.copied')) {
  try { await navigator.clipboard.writeText(txt); ui.toast(okMsg) }
  catch { ui.toast(tr('grid.copyFailed'), true) }
}

/** 单元格右键: 编辑此字段 / 复制值 / 设为 NULL / 复制整行 JSON */
function onCellCtx(e: MouseEvent, i: number, c: string) {
  e.preventDefault()
  e.stopPropagation()
  const row = grid.rows[i]
  if (!row) return
  const val = row[c]
  const items: CtxItem[] = []
  if (auth.canWrite) items.push({ label: tr('grid.editField'), fn: () => grid.startEdit(i, grid.columns.findIndex(x => x.name === c)) })
  items.push({ label: tr('grid.copyValue'), fn: () => copyText(val == null ? 'NULL' : String(val), tr('grid.copiedValue')) })
  if (auth.canWrite && val !== null && val !== undefined) {
    items.push({ label: tr('grid.setNull'), danger: true, fn: () => setCellNull(i, c) })
  }
  items.push({ sep: true }, {
    label: tr('grid.copiedRowJson'), fn: () => copyText(JSON.stringify(row, null, 2), tr('grid.copiedRowJson')),
  })
  ui.showCtxMenu(e.clientX, e.clientY, items)
}
async function setCellNull(i: number, c: string) {
  if (!await confirmDanger(tr('grid.confirmNull', { col: c }))) return
  const ok = await grid.setCellNull(i, grid.columns.findIndex(x => x.name === c))
  ui.toast(ok ? tr('grid.setNullOk') : tr('grid.setNullFail'), !ok)
}

/** 行右键: 编辑行(弹窗)/ 复制行 JSON / 复制整行(TSV) / 删除行 */
function onRowCtx(e: MouseEvent, i: number) {
  e.preventDefault()
  const row = grid.rows[i]
  if (!row) return
  const items: CtxItem[] = []
  if (auth.canWrite) items.push({ label: tr('grid.editRow'), fn: () => openEditRow(i) })
  items.push(
    { label: tr('grid.copyRowJson'), fn: () => copyText(JSON.stringify(row, null, 2), tr('grid.copiedRowJson')) },
    { label: tr('grid.copyRowTsv'), fn: () => copyText(grid.columns.map(c => fmt(row[c.name])).join('\t'), tr('grid.copiedRowTsv')) },
  )
  if (auth.canWrite) {
    items.push({ sep: true }, {
      label: tr('grid.deleteRow'), danger: true, fn: async () => {
        if (!await confirmDanger(tr('grid.confirmDeleteRow'))) return
        grid.selectRow(i, false, false)
        const ok = await grid.deleteSelected()
        ui.toast(ok ? tr('grid.deleted') : tr('grid.deleteFail'), !ok)
      },
    })
  }
  ui.showCtxMenu(e.clientX, e.clientY, items)
}

/** 编辑行弹窗: 预填当前值, 提交整行 PUT(走 EditRowModal 动态组件) */
function openEditRow(i: number) {
  const cur = tab.current
  const row = grid.rows[i]
  const cols = tab.currentMeta?.columns || []
  if (!cur || !row || !cols.length) { ui.toast(tr('grid.cantEdit'), true); return }
  ui.openModal('EditRowModal', { s: cur.s, t: cur.t, row, columns: cols, i })
}

async function copyRow(i: number) {
  const row = grid.rows[i]
  if (!row) return
  await copyText(grid.columns.map(c => fmt(row[c.name])).join('\t'), tr('grid.copied'))
}
</script>

<template>
  <div class="datagrid">
    <!-- 滚动容器 -->
    <div ref="dgScroll" class="dg-scroll" @scroll="onScroll">
      <!-- 空态 -->
      <div v-if="!grid.columns.length && !grid.loading" class="empty2" style="padding:24px;text-align:center">
        {{ tr('grid.emptyOpen') }}
      </div>

      <table v-else class="dg">
        <colgroup>
          <col style="width:44px" />
          <col v-for="c in grid.columns" :key="'w' + c.name" :style="{ width: colW[c.name] || undefined }" />
        </colgroup>
        <thead>
          <tr>
            <th class="rowidx">
              <input type="checkbox" :checked="allChecked()" @change="toggleAll" :title="tr('grid.selectAllPage')" />
            </th>
            <th v-for="c in grid.columns" :key="c.name" @click="onHeadClick(c.name)"
                :data-c="c.name" :class="{ sorted: grid.sort?.col === c.name }" :title="tr('grid.sortTitle', { name: c.name })">
              <span class="col-name">{{ c.name }}</span>
              <span class="sort">{{ sortIcon(c.name) }}</span>
              <span class="fbtn" :class="{ on: !!grid.filters[c.name] }" :title="tr('grid.filter')"
                    @click.stop="openFilter(c.name, $event)">▾</span>
              <span class="th-resize" :title="tr('grid.resizeCol')" @mousedown.stop="startResize($event, c.name)"></span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="virtualMode && topPadH" class="vs-spacer"><td colspan="99" :style="{ height: topPadH + 'px' }"></td></tr>
          <tr v-for="({ r, i }) in viewRows" :key="i"
              :class="{ sel: grid.selectedRows.has(i) }"
              @click="onRowClick(i, $event)" @dblclick="onRowDblClick(i)"
              @contextmenu="onRowCtx($event, i)">
            <td class="rowidx">{{ (grid.page - 1) * grid.pageSize + i + 1 }}</td>
            <template v-for="(c, ci) in grid.columns" :key="ci">
              <td v-if="grid.editingCell && grid.editingCell.r === i && grid.editingCell.c === ci" class="edit-cell">
                <input :value="fmt(r[c.name])" autofocus
                       @input="onEditInput" @keydown.enter="onEditCommit"
                       @keydown.esc="grid.cancelEdit" @blur="onEditCommit" />
              </td>
              <td v-else :class="cellClass(c, r[c.name])"
                  :title="fmt(r[c.name])"
                  @contextmenu.stop="onCellCtx($event, i, c.name)">{{ fmt(r[c.name]) }}</td>
            </template>
          </tr>
          <tr v-if="virtualMode && botPadH" class="vs-spacer"><td colspan="99" :style="{ height: botPadH + 'px' }"></td></tr>
          <tr v-if="grid.loading"><td class="rowidx"></td><td colspan="99" class="loading-td">{{ tr('grid.loading') }}</td></tr>
          <tr v-else-if="!grid.rows.length"><td class="rowidx"></td><td colspan="99" class="loading-td">{{ tr('grid.noData') }}</td></tr>
        </tbody>
      </table>
    </div>

    <!-- 列筛选面板 -->
    <div v-if="filterPop" class="filter-pop" :style="{ left: filterPop.x + 'px', top: filterPop.y + 'px' }" @click.stop>
      <div class="fp-title">{{ tr('grid.filterTitle', { col: filterPop.col }) }}</div>
      <select v-model="filterOp">
        <option v-for="[k, lbl] in FILTER_OPS" :key="k" :value="k">{{ tr(lbl) }}</option>
      </select>
      <input v-if="filterOp !== 'isnull' && filterOp !== 'isnotnull'" v-model="filterVal"
             :placeholder="tr('grid.valuePlaceholder')" @keydown.enter="applyFilter" />
      <div class="fp-acts">
        <button class="sm" @click="clearFilter">{{ tr('grid.clear') }}</button>
        <button class="sm primary" @click="applyFilter">{{ tr('grid.apply') }}</button>
      </div>
    </div>

    <!-- 分页 -->
    <div class="pager" v-if="grid.total > 0 || !totalKnown">
      <button class="sm" :disabled="grid.page <= 1 || !totalKnown" @click="goPage(grid.page - 1)">{{ tr('grid.prevPage') }}</button>
      <span class="page-info" v-if="totalKnown">{{ tr('grid.pageInfo', { page: grid.page, totalPages: pageCount(), rows: grid.total }) }}</span>
      <span class="page-info" v-else>{{ tr('grid.pageInfoUnknown', { rows: grid.total }) }}</span>
      <button class="sm" :disabled="grid.page >= pageCount() || !totalKnown" @click="goPage(grid.page + 1)">{{ tr('grid.nextPage') }}</button>
      <span class="spacer"></span>
      <select :value="grid.pageSize" @change="grid.loadData(1, Number(($event.target as HTMLSelectElement).value))">
        <option :value="50">{{ tr('grid.perPage', { n: 50 }) }}</option>
        <option :value="100">{{ tr('grid.perPage', { n: 100 }) }}</option>
        <option :value="200">{{ tr('grid.perPage', { n: 200 }) }}</option>
        <option :value="500">{{ tr('grid.perPage', { n: 500 }) }}</option>
        <option :value="1000">{{ tr('grid.perPage', { n: 1000 }) }}</option>
        <option :value="2000">{{ tr('grid.perPage', { n: 2000 }) }}</option>
      </select>
    </div>
  </div>
</template>

<style scoped>
.datagrid { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.dg-scroll { flex: 1; min-height: 0; overflow: auto; }
table.dg { width: max-content; min-width: 100%; border-collapse: collapse; font-size: 13px; table-layout: auto; }
.dg thead th { position: sticky; top: 0; background: var(--panel2); text-align: left; padding: 5px 8px; border-bottom: 1px solid var(--border); cursor: pointer; user-select: none; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 300px; z-index: 1; position: relative; }
.dg thead th.sorted { color: var(--primary); }
.dg .col-name { overflow: hidden; text-overflow: ellipsis; }
.dg .sort { font-size: 10px; margin-left: 2px; color: var(--text3); }
.dg .fbtn { font-size: 10px; margin-left: 4px; color: var(--text3); cursor: pointer; }
.dg .fbtn:hover, .dg .fbtn.on { color: var(--primary); }
.th-resize { position: absolute; right: 0; top: 0; bottom: 0; width: 5px; cursor: col-resize; }
.th-resize:hover { background: rgba(22, 93, 255, 0.35); }
.dg td { padding: 4px 8px; border-bottom: 1px solid var(--border, #f0f1f3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 300px; }
.dg td.cell-null { color: var(--text3); font-style: italic; }
.dg td.cell-num { text-align: right; font-variant-numeric: tabular-nums; }
.dg td.cell-date { color: var(--text2); }
.dg td.cell-bool { text-align: center; }
.dg td.rowidx { width: 44px; color: var(--text3); font-size: 11px; text-align: right; user-select: none; }
.dg th.rowidx { width: 44px; cursor: default; text-align: center; }
.dg tbody tr:hover td { background: rgba(128,128,128,0.05); }
.dg tbody tr.sel td { background: rgba(22,93,255,0.10); }
.dg td.edit-cell { padding: 1px; }
.dg td.edit-cell input { width: 100%; box-sizing: border-box; padding: 3px 6px; border: 1px solid var(--primary); border-radius: 3px; font-size: 13px; background: var(--panel, #fff); color: inherit; }
.loading-td { text-align: center; color: var(--text3); padding: 16px !important; }
.vs-spacer td { padding: 0 !important; border: none !important; }
.pager { display: flex; align-items: center; gap: 10px; padding: 6px 10px; border-top: 1px solid var(--border); font-size: 12px; color: var(--text2, var(--text3)); flex-shrink: 0; }
.page-info { flex-shrink: 0; }
.spacer { flex: 1; }
.empty2 { color: var(--text3); font-size: 13px; }
button.sm { padding: 4px 10px; font-size: 12px; }
select { padding: 3px 6px; font-size: 12px; }

/* 列筛选面板 */
.filter-pop {
  position: fixed; z-index: 9500; width: 220px;
  background: var(--panel, #fff); border: 1px solid var(--border); border-radius: 8px;
  box-shadow: 0 6px 20px rgba(0,0,0,0.14); padding: 10px; font-size: 13px; display: flex; flex-direction: column; gap: 8px;
}
.fp-title { font-size: 12px; color: var(--text2, var(--text3)); font-weight: 600; }
.filter-pop select, .filter-pop input { padding: 4px 8px; border: 1px solid var(--border2, var(--border)); border-radius: 5px; font-size: 13px; background: var(--panel, #fff); color: inherit; }
.fp-acts { display: flex; justify-content: flex-end; gap: 6px; }
</style>
