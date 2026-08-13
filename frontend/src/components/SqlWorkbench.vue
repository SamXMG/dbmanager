<script setup lang="ts">
// SQL 工作台(阶段 4): 工具栏 + CodeMirror 编辑器 + 历史/收藏 + 多结果 tab + 结果内过滤 + 结果表格
// 对齐旧版 js/sql.js 的 sqlView 全部功能(执行/格式化/解释/写模式/导出 CSV/导出 Excel/清空历史/看全文)
import { computed, onMounted, ref } from 'vue'
import Icon from '@/components/Icon.vue'
import { errMsg } from '@/utils/err'
import { confirmDanger } from '@/utils/confirm'
import SqlEditor from '@/components/SqlEditor.vue'
import { useSqlStore } from '@/stores/sql'
import { useUIStore } from '@/stores/ui'
import { exportSqlXlsx } from '@/api/sql'
import { openQueryBuilder } from '@/utils/tools'

const sqlStore = useSqlStore()
const ui = useUIStore()

const showHist = ref(false)
const histKw = ref('')
const filterKw = ref('')

// 编辑器 v-model <-> store(切视图后 SQL 不丢)
const sqlText = computed({
  get: () => sqlStore.sqlText,
  set: (v: string) => sqlStore.setSqlText(v),
})

onMounted(() => { sqlStore.loadAll() })

// ---- 执行 / 解释 / 格式化 ----
async function onExec() {
  try {
    if (sqlStore.writeMode && !await confirmDanger('写模式执行: 将真实修改数据库且不可撤销。\n建议先备份或确认 WHERE 条件准确。\n确认继续执行吗？', '写模式执行')) return
    const tabs = await sqlStore.exec()
    if (tabs.length && tabs[0].error) ui.toast('SQL 执行失败: ' + tabs[0].error, true)
  } catch (e) {
    ui.toast('SQL 执行失败: ' + errMsg(e), true)
  }
}
async function onExplain() {
  try {
    const tab = await sqlStore.explain()
    ui.openModal('ExplainPlanModal', { tabId: tab.id })
  } catch (e) { ui.toast('EXPLAIN 失败: ' + errMsg(e), true) }
}
/** 结果集图表: 打开 ResultChartModal(读取当前结果 tab) */
function openChart() {
  const tab = sqlStore.activeTab
  if (!tab || !tab.columns?.length) { ui.toast('当前没有可绘制的结果集', true); return }
  ui.openModal('ResultChartModal')
}
function onFormat() {
  const before = sqlStore.sqlText
  sqlStore.format()
  ui.toast(sqlStore.sqlText === before ? 'SQL 已是最佳格式' : '已格式化')
}

// ---- 导出 ----
function downloadBlob(blob: Blob, filename: string) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(a.href)
}
function exportCsv() {
  const tab = sqlStore.activeTab
  if (!tab || !tab.columns?.length) { ui.toast('当前没有可导出的查询结果', true); return }
  let csv = '\ufeff' + tab.columns.map(c => '"' + String(c.name).replace(/"/g, '""') + '"').join(',') + '\r\n'
  ;(tab.rows || []).forEach(r => {
    csv += tab.columns!.map(c => {
      const v = r[c.name]
      if (v == null) return ''
      return '"' + String(v).replace(/"/g, '""') + '"'
    }).join(',') + '\r\n'
  })
  downloadBlob(new Blob([csv], { type: 'text/csv;charset=utf-8' }), 'query_result.csv')
  ui.toast('已导出查询结果 CSV')
}
async function exportXlsx() {
  const tab = sqlStore.activeTab
  if (!tab || !tab.columns?.length) { ui.toast('当前没有可导出的查询结果', true); return }
  try {
    await exportSqlXlsx(tab.columns, tab.rows || [])
    ui.toast('已导出 ' + (tab.rows?.length || 0) + ' 行')
  } catch (e) { ui.toast('导出失败: ' + errMsg(e), true) }
}

// ---- 结果渲染 ----
const CELL_TRUNC = 300
const activeTab = computed(() => sqlStore.activeTab)
function fmt(v: unknown): string {
  if (v === null || v === undefined) return ''
  if (typeof v === 'object') {
    try { return JSON.stringify(v) } catch { return String(v) }
  }
  return String(v)
}
function isTrunc(v: unknown): boolean { return fmt(v).length > CELL_TRUNC }
function disp(v: unknown): string {
  const s = fmt(v)
  return s.length > CELL_TRUNC ? s.slice(0, CELL_TRUNC) + '…' : s
}

/** 结果内过滤(不重新查询) */
const filteredRows = computed(() => {
  const tab = sqlStore.activeTab
  if (!tab?.rows?.length || !tab.columns?.length) return tab?.rows || []
  const kw = filterKw.value.trim().toLowerCase()
  if (!kw) return tab.rows
  return tab.rows.filter(r =>
    tab.columns!.some(c => {
      const v = r[c.name]
      return v != null && String(v).toLowerCase().includes(kw)
    }))
})
const filterInfo = computed(() => {
  const tab = sqlStore.activeTab
  if (!tab?.rows?.length) return ''
  const kw = filterKw.value.trim()
  return kw ? `过滤: ${filteredRows.value.length} / 共 ${tab.rows.length} 行` : ''
})
const hint = computed(() => {
  const tab = sqlStore.activeTab
  if (!tab) return ''
  if (tab.error) return ''
  if (tab.columns?.length) {
    const n = tab.rows?.length || 0
    return `共 ${tab.total ?? n} 行` + (tab.truncated ? ` (已截断, 仅显示前 ${n} 行)` : '')
  }
  if (tab.affected != null) return `执行成功 (影响 ${tab.affected} 行)`
  return ''
})

// ---- 截断单元格双击看全文(弹窗) ----
// P1-9 去重: esc 统一从 utils/sqlIdent.ts 导入(原组件内本地定义删除)
import { esc } from '@/utils/sqlIdent'
async function copyText(t: string, okMsg = '已复制') {
  try { await navigator.clipboard.writeText(t); ui.toast(okMsg) }
  catch { ui.toast('复制失败', true) }
}

/** 结果表格右键: 复制单元格值 / 复制整行 JSON */
function onCellCtx(e: MouseEvent, row: Record<string, unknown>, col: string) {
  e.preventDefault()
  e.stopPropagation()
  const v = row[col]
  ui.showCtxMenu(e.clientX, e.clientY, [
    { label: '复制值', fn: () => copyText(v == null ? 'NULL' : String(v), '已复制值') },
    { label: '复制整行 JSON', fn: () => copyText(JSON.stringify(row, null, 2), '已复制整行 JSON') },
  ])
}
function onRowCtx(e: MouseEvent, row: Record<string, unknown>) {
  e.preventDefault()
  ui.showCtxMenu(e.clientX, e.clientY, [
    { label: '复制整行 JSON', fn: () => copyText(JSON.stringify(row, null, 2), '已复制整行 JSON') },
  ])
}
function showCellDetail(col: string, v: unknown) {
  ui.openModal('CellDetailModal', { col, text: v == null ? '' : String(v) })
}

// ---- 历史 / 收藏 ----
function fmtHistTime(t: number): string {
  if (!t) return ''
  const d = new Date(t), now = new Date()
  const hm = ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2)
  return d.toDateString() === now.toDateString() ? hm : ((d.getMonth() + 1) + '/' + d.getDate() + ' ' + hm)
}
const filteredHist = computed(() => {
  const kw = histKw.value.trim().toLowerCase()
  return sqlStore.history.filter(x => !kw || x.sql.toLowerCase().includes(kw))
})
const favItems = computed(() => filteredHist.value.filter(x => sqlStore.favorites.includes(x.sql)))
const restItems = computed(() => filteredHist.value.filter(x => !sqlStore.favorites.includes(x.sql)))
function useHist(sql: string, run = false) {
  sqlStore.setSqlText(sql)
  if (run) onExec()
}
function toggleHist() { showHist.value = !showHist.value }
async function clearAll() {
  if (!await confirmDanger('确认清空全部 SQL 历史与收藏？')) return
  sqlStore.clearHistory()
  sqlStore.clearFavorites()
  ui.toast('已清空')
}

// ---- 结果 tab 标签 ----
function tabLabel(t: { sql: string }): string {
  const oneLine = t.sql.replace(/\s+/g, ' ').trim()
  return oneLine.length > 40 ? oneLine.slice(0, 40) + '…' : oneLine
}
</script>

<template>
  <div class="sql-workbench">
    <!-- 工具栏 -->
    <div class="sql-bar">
      <button class="primary sm" @click="onExec" title="执行 (Ctrl+Enter)">▶ 执行</button>
      <button class="sm" @click="onFormat" title="美化当前 SQL (Ctrl+Shift+F)">格式化</button>
      <button class="sm" @click="openQueryBuilder" title="可视化构建 SELECT 查询">构建器</button>
      <button class="sm" @click="onExplain" title="查看当前 SQL 的执行计划 (EXPLAIN)">解释</button>
      <button class="sm" @click="openChart" title="将当前结果集绘制为柱状图">图表</button>
      <button class="sm" :class="sqlStore.writeMode ? 'write-on' : 'write-off'" @click="sqlStore.writeMode = !sqlStore.writeMode"
              :title="sqlStore.writeMode ? '写模式已开启, 可执行 DML/DDL' : '只读模式, 仅允许 SELECT/SHOW/EXPLAIN/DESC'">
        写模式: {{ sqlStore.writeMode ? '开' : '关' }}
      </button>
      <button class="sm" @click="exportCsv" title="导出当前结果 CSV">导出CSV</button>
      <button class="sm" @click="exportXlsx" title="导出当前结果 Excel">导出Excel</button>
      <button class="sm" @click="clearAll" title="清空 SQL 历史与收藏">清空历史</button>
      <span class="sql-hint">{{ hint }}</span>
    </div>

    <!-- 编辑器 -->
    <div class="sql-editor-box">
      <SqlEditor v-model="sqlText" @exec="onExec" @format="onFormat" />
    </div>

    <!-- 历史 / 收藏(折叠) -->
    <div class="hist-head" v-if="sqlStore.history.length">
      <button class="sm" @click="toggleHist">{{ showHist ? '▾' : '▸' }} 历史/收藏
        <span class="hist-count">{{ sqlStore.favorites.length }} 收藏 · {{ sqlStore.history.length }} 条</span>
      </button>
    </div>
    <div class="sql-hist" v-if="showHist && sqlStore.history.length">
      <input v-model="histKw" class="hist-search" placeholder="搜索 SQL 历史..." title="按内容过滤历史/收藏" />
      <div class="hist-items">
        <template v-if="favItems.length">
          <span class="hist-group"><Icon name="star" :size="12" /> 收藏</span>
          <span v-for="x in favItems" :key="'f' + x.ts + x.sql" class="hist-item fav"
                :title="x.sql">
            <span class="hist-star" @click.stop="sqlStore.toggleFavorite(x.sql)"><Icon name="star" :size="12" /></span>
            <span class="hist-text" @click="useHist(x.sql)" @dblclick="useHist(x.sql, true)">{{ x.sql.length > 60 ? x.sql.slice(0, 60) + '…' : x.sql }}</span>
            <span v-if="x.ts" class="hist-time">{{ fmtHistTime(x.ts) }}</span>
          </span>
        </template>
        <template v-if="restItems.length">
          <span class="hist-group">历史</span>
          <span v-for="x in restItems" :key="'h' + x.ts + x.sql" class="hist-item" :title="x.sql">
            <span class="hist-star" @click.stop="sqlStore.toggleFavorite(x.sql)"><Icon name="star" :size="12" /></span>
            <span class="hist-text" @click="useHist(x.sql)" @dblclick="useHist(x.sql, true)">{{ x.sql.length > 60 ? x.sql.slice(0, 60) + '…' : x.sql }}</span>
            <span v-if="x.ts" class="hist-time">{{ fmtHistTime(x.ts) }}</span>
          </span>
        </template>
        <span v-if="!filteredHist.length" class="hist-empty">无匹配历史</span>
      </div>
    </div>

    <!-- 多结果 tab -->
    <div class="sql-tabs" v-if="sqlStore.tabs.length">
      <span v-for="t in sqlStore.tabs" :key="t.id" class="sql-tab"
            :class="{ active: t.id === sqlStore.active }"
            @click="sqlStore.switchTab(t.id)" :title="t.sql">
        Q{{ t.id }}: {{ tabLabel(t) }}
        <span class="x" @click.stop="sqlStore.closeTab(t.id)">×</span>
      </span>
      <span class="tab-spacer"></span>
      <span class="tab-clear" @click="sqlStore.clearResults()" title="清空全部结果">清空</span>
    </div>

    <!-- 结果内过滤 -->
    <div class="sql-filter" v-if="activeTab && activeTab.columns?.length">
      <input v-model="filterKw" type="search" placeholder="在当前结果中过滤 (不重新查询)..." title="按任意列内容过滤当前结果集, 清空恢复全部" />
      <span class="sql-filter-info">{{ filterInfo }}</span>
    </div>

    <!-- 结果表格 -->
    <div class="gridwrap sql-result">
      <!-- 空态: 无 tab -->
      <div v-if="!activeTab" class="empty2">执行 SQL 后结果显示在这里, 每条语句一个结果 tab</div>
      <!-- 错误态 -->
      <div v-else-if="activeTab.error" class="sql-error">{{ activeTab.error }}</div>
      <!-- 成功但无结果集(写操作/DDL) -->
      <div v-else-if="!activeTab.columns?.length" class="empty2">执行成功{{ activeTab.affected != null ? ' (影响 ' + activeTab.affected + ' 行)' : '' }}</div>
      <!-- 结果集 -->
      <table v-else class="dg">
        <thead>
          <tr>
            <th v-for="c in activeTab.columns" :key="c.name">{{ c.name }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in filteredRows" :key="i" @contextmenu="onRowCtx($event, row)">
            <td v-for="c in activeTab.columns" :key="c.name"
                :class="{ null: row[c.name] === null || row[c.name] === undefined, trunc: isTrunc(row[c.name]) }"
                :title="isTrunc(row[c.name]) ? '内容过长, 双击查看完整内容' : fmt(row[c.name])"
                @dblclick="showCellDetail(c.name, row[c.name])"
                @contextmenu.stop="onCellCtx($event, row, c.name)">
              {{ disp(row[c.name]) }}
            </td>
          </tr>
          <tr v-if="!filteredRows.length">
            <td colspan="99" class="loading-td">无数据</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.sql-workbench { flex: 1; display: flex; flex-direction: column; min-height: 0; padding: 10px 14px; }
.sql-bar { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.sql-hint { color: var(--text3); font-size: 12px; margin-left: auto; }
.sql-editor-box { flex: 0 0 30%; min-height: 110px; }

/* 写模式按钮: 开=红底白字, 关=浅红 */
button.write-on { background: var(--danger-solid); color: #fff; border-color: var(--danger-solid); }
button.write-off { background: var(--danger-bg); color: var(--danger-solid); border-color: var(--danger-bg); }

/* 历史折叠头 */
.hist-head { margin: 4px 0; }
.hist-count { color: var(--text3); font-size: 11px; margin-left: 4px; }
.sql-hist { display: flex; flex-direction: column; gap: 6px; margin: 4px 0 8px; max-height: 220px; }
.hist-search { flex: 0 0 auto; width: 240px; padding: 4px 8px; border: 1px solid var(--border2, var(--border)); border-radius: 5px; font-size: 12px; outline: none; background: var(--panel, #fff); color: inherit; }
.hist-items { display: flex; flex-wrap: wrap; gap: 4px; overflow-y: auto; align-content: flex-start; }
.hist-group { flex-basis: 100%; font-size: 11px; color: var(--text3); margin-top: 2px; }
.hist-item { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; font-size: 12px; background: var(--panel2); border: 1px solid var(--border); border-radius: 4px; cursor: default; }
.hist-item.fav { border-color: var(--warning-solid); background: var(--warning-bg); }
.hist-star { cursor: pointer; color: var(--warning-solid); }
.hist-text { cursor: pointer; max-width: 340px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: Consolas, monospace; }
.hist-time { color: var(--text3); font-size: 11px; }
.hist-empty { color: var(--text3); font-size: 12px; padding: 4px 0; }

/* 多结果 tab */
.sql-tabs { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; padding: 6px 0 8px; border-bottom: 1px solid var(--border); margin-bottom: 8px; flex-shrink: 0; }
.sql-tab { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; font-size: 12px; background: var(--panel3, #f2f3f5); border: 1px solid var(--border); border-radius: 4px; cursor: pointer; max-width: 280px; white-space: nowrap; overflow: hidden; color: var(--text); }
.sql-tab.active { background: var(--primary); border-color: var(--primary); color: #fff; }
.sql-tab .x { color: inherit; opacity: .7; font-weight: 700; }
.sql-tab .x:hover { opacity: 1; }
.tab-spacer { flex: 1; }
.tab-clear { font-size: 12px; color: var(--text3); cursor: pointer; }
.tab-clear:hover { color: var(--danger-solid); }

/* 结果内过滤 */
.sql-filter { display: flex; align-items: center; gap: 8px; padding: 4px 0 8px; flex-shrink: 0; }
.sql-filter input { flex: 0 0 300px; padding: 5px 10px; border: 1px solid var(--border2, var(--border)); border-radius: 6px; font-size: 12px; outline: none; background: var(--panel, #fff); color: inherit; }
.sql-filter input:focus { border-color: var(--primary); }
.sql-filter-info { font-size: 12px; color: var(--text3); }

/* 结果表格: 容器已 overflow:auto; 表格 max-content 列宽自适应, 列多时横向滚动不压扁 */
.gridwrap.sql-result { flex: 1; min-height: 0; overflow: auto; border: 1px solid var(--border); border-radius: 6px; }
table.dg { width: max-content; min-width: 100%; border-collapse: collapse; font-size: 13px; }
.dg thead th { position: sticky; top: 0; background: var(--panel2); text-align: left; padding: 5px 8px; border-bottom: 1px solid var(--border); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 300px; z-index: 1; }
.dg td { padding: 4px 8px; border-bottom: 1px solid var(--border, #f0f1f3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 300px; }
.dg td.null { color: var(--text3); font-style: italic; }
.dg td.trunc { color: var(--primary); cursor: pointer; }
.dg tbody tr:hover td { background: rgba(128, 128, 128, 0.05); }
.loading-td { text-align: center; color: var(--text3); padding: 16px !important; }
.empty2 { color: var(--text3); font-size: 13px; padding: 24px; text-align: center; }
.sql-error { color: var(--danger-solid); padding: 16px 20px; font-size: 13px; white-space: pre-wrap; }
button.sm { padding: 4px 10px; font-size: 12px; }
</style>
