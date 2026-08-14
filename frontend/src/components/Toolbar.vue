<script setup lang="ts">
// 数据浏览工具栏: 刷新/新增行/删除选中/粘贴插入/复制选中/导出 CSV(整表·选中)/统计/Redis 键操作
// (对齐旧版工具栏; Redis 连接显示 新建键/TTL/删除键)
import { computed } from 'vue'
import { errMsg } from '@/utils/err'
import { confirmDanger } from '@/utils/confirm'
import { useGridStore } from '@/stores/grid'
import { useTabStore } from '@/stores/tab'
import { useAuthStore } from '@/stores/auth'
import { useUIStore } from '@/stores/ui'
import { useConnectionStore } from '@/stores/connection'
import { alterTable } from '@/api/schema'

const grid = useGridStore()
const tab = useTabStore()
const auth = useAuthStore()
const ui = useUIStore()
const connStore = useConnectionStore()

const hasTable = computed(() => !!tab.current)
const canWrite = computed(() => auth.canWrite)
const isRedis = computed(() => connStore.conn?.db_type === 'redis')

/** 刷新当前页数据 */
function refresh() { grid.loadData() }

/** 流式加载全部(上限 5 万行, 虚拟滚动渲染) */
async function loadAll() {
  const cur = tab.current
  if (!cur) return
  if (!await confirmDanger(`确认加载 ${cur.s}.${cur.t} 全部数据？(上限 5 万行, 可能较慢)`)) return
  const n = await grid.loadAll()
  ui.toast('已加载 ' + n + ' 行')
}

/** 新增行(简版: 弹窗收集列值, 空值用 null) —— 走 AddRowModal 动态组件 */
function addRow() {
  const cur = tab.current
  if (!cur) return
  const cols = tab.currentMeta?.columns || []
  ui.openModal('AddRowModal', { s: cur.s, t: cur.t, columns: cols })
}

/** 删除选中行 */
async function deleteRows() {
  if (!grid.selectedRows.size) { ui.toast('请先选中行', true); return }
  if (!await confirmDanger(`确认删除选中的 ${grid.selectedRows.size} 行？`)) return
  const ok = await grid.deleteSelected()
  ui.toast(ok ? '已删除' : '删除失败', !ok)
}

/** 导出(格式选择弹窗: CSV/JSON/XML/SQL-INSERT/XLSX, 功能深度①) */
function exportData() {
  const cur = tab.current
  if (!cur) return
  ui.openModal('ExportModal', { s: cur.s, t: cur.t })
}

/** 复制选中行(TSV 带表头) */
async function copySelected() {
  const idxs = [...grid.selectedRows].sort((a, b) => a - b)
  if (!idxs.length) { ui.toast('请先选中行', true); return }
  const rows = idxs.map(i => grid.rows[i]).filter(Boolean)
  const lines = [grid.columns.map(c => c.name).join('\t'),
    ...rows.map(r => grid.columns.map(c => fmtV(r[c.name])).join('\t'))]
  try {
    await navigator.clipboard.writeText(lines.join('\n'))
    ui.toast('已复制 ' + rows.length + ' 行')
  } catch { ui.toast('复制失败', true) }
}
function fmtV(v: unknown): string {
  if (v === null || v === undefined) return ''
  return String(v)
}

/** 导出选中行 CSV(前端生成带 BOM) */
function exportSelected() {
  const idxs = [...grid.selectedRows].sort((a, b) => a - b)
  if (!idxs.length) { ui.toast('请先选中行', true); return }
  const rows = idxs.map(i => grid.rows[i]).filter(Boolean)
  let csv = '\ufeff' + grid.columns.map(c => '"' + String(c.name).replace(/"/g, '""') + '"').join(',') + '\r\n'
  rows.forEach(r => {
    csv += grid.columns.map(c => {
      const v = r[c.name]
      if (v == null) return ''
      return '"' + String(v).replace(/"/g, '""') + '"'
    }).join(',') + '\r\n'
  })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
  a.download = 'selected_rows.csv'
  document.body.appendChild(a); a.click(); a.remove()
  URL.revokeObjectURL(a.href)
  ui.toast('已导出选中 ' + rows.length + ' 行')
}

/** Excel/CSV 批量粘贴插入: 逻辑(解析 TSV/CSV -> 列映射 -> /api/import)已迁入 PasteInsertModal.vue。 */
function pasteInsert() {
  const cur = tab.current
  const meta = tab.currentMeta
  if (!cur || !meta) return
  ui.openModal('PasteInsertModal', { s: cur.s, t: cur.t, columns: meta.columns })
}

/** 列统计(简版: 弹窗选列) —— 走 ColumnStatsModal 动态组件 */
function showStats() {
  const cur = tab.current
  const meta = tab.currentMeta
  if (!cur || !meta) return
  ui.openModal('ColumnStatsModal', { s: cur.s, t: cur.t, columns: meta.columns })
}

// ---- Redis 键操作(对齐旧版 redisNewKey/redisTtl/redisDelKey) ----
// 新建 / TTL 弹窗逻辑已迁入 RedisKeyModal / RedisTtlModal(均走 /api/alter)。
function redisNewKey() {
  const cur = tab.current
  if (!cur) return
  ui.openModal('RedisKeyModal', { s: cur.s, t: cur.t })
}
async function redisTtl() {
  const cur = tab.current
  if (!cur) return
  ui.openModal('RedisTtlModal', { s: cur.s, t: cur.t })
}
async function redisDelKey() {
  const cur = tab.current
  if (!cur) return
  if (!await confirmDanger(`[危险] 将删除整个键 "${cur.t}"，该键下所有数据不可恢复！\n确定继续吗？`)) return
  try {
    await alterTable({ s: cur.s, t: cur.t, action: 'drop', payload: {} })
    ui.toast('已删除键 ' + cur.t)
    tab.closeTab(tab.activeId ?? -1)
  } catch (e) { ui.toast('删除失败: ' + errMsg(e), true) }
}
</script>

<template>
  <div class="toolbar" v-if="hasTable">
    <button class="sm" @click="refresh" title="刷新当前数据 (Ctrl+R)">刷新</button>
    <button class="sm" @click="loadAll" title="流式加载全部数据(上限 5 万行, 虚拟滚动)">加载全部</button>
    <button v-if="canWrite" class="sm" @click="addRow">新增行</button>
    <button v-if="canWrite" class="sm" @click="pasteInsert" title="从 Excel/CSV 粘贴批量插入">粘贴插入</button>
    <button v-if="canWrite" class="sm danger" @click="deleteRows"
            :disabled="!grid.selectedRows.size">删除选中{{ grid.selectedRows.size ? `(${grid.selectedRows.size})` : '' }}</button>
    <button class="sm" @click="copySelected" :disabled="!grid.selectedRows.size"
            title="复制选中行(TSV 带表头)">复制选中</button>
    <button class="sm" @click="exportSelected" :disabled="!grid.selectedRows.size"
            title="导出选中行为 CSV">导出选中</button>
    <button class="sm" @click="exportData">导出</button>
    <button class="sm" @click="showStats">统计</button>
    <template v-if="isRedis">
      <button v-if="canWrite" class="sm" @click="redisNewKey" title="新建 Redis 键">新建键</button>
      <button v-if="canWrite" class="sm" @click="redisTtl" title="设置键过期时间">TTL</button>
      <button v-if="canWrite" class="sm danger" @click="redisDelKey" title="删除整个键">删除键</button>
    </template>
    <span class="spacer"></span>
    <span class="count" v-if="grid.total">共 {{ grid.total }} 行 · 第 {{ grid.page }} 页</span>
  </div>
</template>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.spacer { flex: 1; }
.count { font-size: 12px; color: var(--text2, var(--text3)); }
button.sm { padding: 4px 10px; font-size: 12px; }
</style>
