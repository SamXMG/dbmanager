<script setup lang="ts">
// EXPLAIN 执行计划可视化(取代旧版 SqlWorkbench 无弹窗/文本态展示)。
// mode=tree(PG/MySQL 归一化 plan): 递归渲染 SVG 纵向树, 计算每个节点的
//   独占耗时/代价占比(瓶颈红/次瓶颈橙)与 估算行数 vs 实际行数 偏差标记; 支持滚轮缩放/拖拽平移。
// mode=table(MySQL 旧表/SQLite/MSSQL 多列): 增强型多列表格(内容自适应列宽 + 锁定表头 +
//   横向/纵向滚动同步 + 单元格省略号 + 等宽字体 + 悬浮提示 + 双击预览 + 右键复制 + 表头排序 +
//   慢语句着色 + 工具栏复制/导出/搜索); mode=text(MSSQL/Oracle/单列): 原缩进文本。
// 由 GenericModal 在共享遮罩内渲染, 本组件只渲染 .g-modal 卡片根(本组件额外支持拖拽/缩放)。
import { ref, computed, onMounted, onBeforeUnmount, type CSSProperties } from 'vue'
import { useUIStore } from '@/stores/ui'
import { useSqlStore } from '@/stores/sql'
import type { PlanNode } from '@/api/sql'
import type { CtxItem } from '@/stores/ui'

const props = defineProps<{ tabId: number }>()
const ui = useUIStore()
const sqlStore = useSqlStore()

const tab = computed(() => sqlStore.tabs.find(t => t.id === props.tabId) || null)
const cols = computed(() => tab.value?.columns || [])
const rows = computed(() => tab.value?.rows || [])

// 单列计划(PostgreSQL / SQLite 的 QUERY PLAN)按原缩进显示; 多列(Mysql/MSSQL)走增强表格
const singleCol = computed(() => cols.value.length === 1)
const colName = computed(() => cols.value[0]?.name || '')
const planText = computed(() =>
  (rows.value || []).map(r => String(r[colName.value] ?? '')).join('\n'))
const isTree = computed(() => tab.value?.mode === 'tree' && !!tab.value?.plan)

function cell(v: unknown): string {
  if (v === null || v === undefined) return ''
  return String(v)
}

// 代码型列(显示 SQL / 参数定义等): 等宽字体 + 双击预览
function isCodeCol(name: string): boolean {
  return /stmt|sql|text|query|argument|output|defined|param|declare|command|plan|xml|substring|statement/i.test(name)
}

// ---------- 树布局与代价分析 ----------
const NW = 264, NH = 72, HGAP = 22, VGAP = 48, PAD = 24
interface TNode { n: PlanNode; cx: number; y: number; mark: 'normal' | 'warn' | 'bottleneck'; timeRatio: number; costRatio: number; rowsBias: number | null }
interface TEdge { x1: number; y1: number; x2: number; y2: number }

const treeView = computed(() => {
  const plan = tab.value?.plan
  if (!plan) return null
  const nodes: TNode[] = []
  const edges: TEdge[] = []
  let cursorX = PAD
  let maxDepth = 0
  const rootTime = plan.time_actual_ms ?? 0
  const rootCost = plan.cost_est ?? 0
  const subTime = (n: PlanNode) => n.time_actual_ms ?? 0
  const subCost = (n: PlanNode) => n.cost_est ?? 0
  function walk2(n: PlanNode, depth: number): number {
    maxDepth = Math.max(maxDepth, depth)
    const kids = n.children || []
    const cs: number[] = kids.map(k => walk2(k, depth + 1))
    const cx = kids.length ? (cs[0] + cs[cs.length - 1]) / 2 : (cursorX + NW / 2)
    if (!kids.length) cursorX += NW + HGAP
    const y = PAD + depth * (NH + VGAP)
    const kidsTime = kids.reduce((s, k) => s + subTime(k), 0)
    const kidsCost = kids.reduce((s, k) => s + subCost(k), 0)
    const exMs = subTime(n) - kidsTime           // 独占耗时(PG Actual Total Time 为子树累计)
    const exCost = subCost(n) - kidsCost
    const timeRatio = rootTime > 0 ? exMs / rootTime : 0
    const costRatio = rootCost > 0 ? exCost / rootCost : 0
    const rowsBias = (n.rows_actual != null && n.rows_est && n.rows_est > 0) ? n.rows_actual / n.rows_est : null
    const mark = (timeRatio > 0.4 || costRatio > 0.4) ? 'bottleneck'
      : (timeRatio > 0.15 || costRatio > 0.15 || (rowsBias != null && rowsBias > 10)) ? 'warn' : 'normal'
    nodes.push({ n, cx, y, mark, timeRatio, costRatio, rowsBias })
    kids.forEach((_, i) => {
      edges.push({ x1: cx, y1: y + NH, x2: cs[i], y2: PAD + (depth + 1) * (NH + VGAP) })
    })
    return cx
  }
  walk2(plan, 0)
  const W = cursorX + NW / 2 + PAD
  const H = PAD + (maxDepth + 1) * (NH + VGAP)
  return { nodes, edges, W, H }
})

function fmt(v: number | null | undefined): string {
  if (v == null) return '-'
  if (Math.abs(v) >= 1000) return Math.round(v).toLocaleString()
  if (Number.isInteger(v)) return String(v)
  return v.toFixed(2)
}
function trunc(s: string | null | undefined, n = 32): string {
  if (!s) return ''
  return s.length > n ? s.slice(0, n - 1) + '…' : s
}

// ---------- pan / zoom ----------
const tx = ref(0)
const ty = ref(0)
const scale = ref(1)
let dragging = false
let lastX = 0
let lastY = 0

function onWheel(e: WheelEvent) {
  e.preventDefault()
  const delta = e.deltaY < 0 ? 1.12 : 1 / 1.12
  const ns = Math.min(3, Math.max(0.2, scale.value * delta))
  const cx = (treeView.value?.W ?? 600) / 2
  const cy = (treeView.value?.H ?? 400) / 2
  tx.value = cx - (cx - tx.value) * (ns / scale.value)
  ty.value = cy - (cy - ty.value) * (ns / scale.value)
  scale.value = ns
}
function onDown(e: MouseEvent) { dragging = true; lastX = e.clientX; lastY = e.clientY }
function onMoveTree(e: MouseEvent) {
  if (!dragging) return
  tx.value += (e.clientX - lastX) / scale.value
  ty.value += (e.clientY - lastY) / scale.value
  lastX = e.clientX
  lastY = e.clientY
}
function onUpTree() { dragging = false }
function zoomBy(f: number) {
  const ns = Math.min(3, Math.max(0.2, scale.value * f))
  const cx = (treeView.value?.W ?? 600) / 2
  const cy = (treeView.value?.H ?? 400) / 2
  tx.value = cx - (cx - tx.value) * (ns / scale.value)
  ty.value = cy - (cy - ty.value) * (ns / scale.value)
  scale.value = ns
}
function fit() { tx.value = 0; ty.value = 0; scale.value = 1 }

// ================= 拖拽 / 缩放卡片 =================
const card = ref<HTMLElement | null>(null)
const cardX = ref(0)
const cardY = ref(0)
const cardW = ref(900)
const cardH = ref(660)
let dm: 'drag' | 'resize' | null = null
let dsx = 0, dsy = 0, dox = 0, doy = 0, dow = 0, doh = 0

function clampX(x: number): number {
  const w = cardW.value
  return Math.max(6, Math.min(x, window.innerWidth - w - 6))
}
function clampY(y: number): number {
  const h = cardH.value
  return Math.max(6, Math.min(y, window.innerHeight - h - 6))
}
function initPos() {
  cardX.value = clampX((window.innerWidth - cardW.value) / 2)
  cardY.value = clampY((window.innerHeight - cardH.value) / 2)
}
function startDrag(e: MouseEvent) {
  if ((e.target as HTMLElement).closest('button, input, .no-drag')) return
  dm = 'drag'; dsx = e.clientX; dsy = e.clientY; dox = cardX.value; doy = cardY.value
  addWin()
  e.preventDefault()
}
function startResize(e: MouseEvent) {
  dm = 'resize'; dsx = e.clientX; dsy = e.clientY; dow = cardW.value; doh = cardH.value
  addWin()
  e.preventDefault()
}
function onWinMove(e: MouseEvent) {
  if (!dm) return
  if (dm === 'drag') {
    cardX.value = clampX(dox + e.clientX - dsx)
    cardY.value = clampY(doy + e.clientY - dsy)
  } else {
    cardW.value = Math.max(520, Math.min(dow + e.clientX - dsx, window.innerWidth - 12))
    cardH.value = Math.max(340, Math.min(doh + e.clientY - dsy, window.innerHeight - 12))
  }
}
function onWinUp() { dm = null; removeWin() }
function addWin() {
  window.addEventListener('mousemove', onWinMove)
  window.addEventListener('mouseup', onWinUp)
}
function removeWin() {
  window.removeEventListener('mousemove', onWinMove)
  window.removeEventListener('mouseup', onWinUp)
}
function onWinResize() {
  cardX.value = clampX(cardX.value)
  cardY.value = clampY(cardY.value)
}
const cardStyle = computed<CSSProperties>(() => ({
  position: 'fixed',
  left: cardX.value + 'px',
  top: cardY.value + 'px',
  width: cardW.value + 'px',
  height: cardH.value + 'px',
  maxWidth: 'none',
  boxSizing: 'border-box',
}))

// ================= 表格高度拖拽(上下拖拽调高表格区) =================
// 表格区高度由 tableH 单独控制(而非 flex:1 被挤压), 并联动卡片高度,
// 其余固定元素(标题/SQL块/工具栏/表脚/关闭栏)预留 OTHER_H 高度。
const OTHER_H = 330
const tableH = ref(420)
function initTableH() {
  const ideal = Math.round(Math.min(window.innerHeight * 0.6, 600))
  tableH.value = Math.max(180, ideal)
  cardH.value = tableH.value + OTHER_H
}
let tResizing = false
let tStartY = 0
let tStartH = 0
function startTableResize(e: MouseEvent) {
  tResizing = true
  tStartY = e.clientY
  tStartH = tableH.value
  window.addEventListener('mousemove', onTableMove)
  window.addEventListener('mouseup', onTableUp)
  e.preventDefault()
  e.stopPropagation()
}
function onTableMove(e: MouseEvent) {
  if (!tResizing) return
  const nh = tStartH + (e.clientY - tStartY)
  const minH = 160
  const maxH = window.innerHeight - OTHER_H - 24
  tableH.value = Math.max(minH, Math.min(nh, maxH))
  cardH.value = tableH.value + OTHER_H
}
function onTableUp() {
  tResizing = false
  window.removeEventListener('mousemove', onTableMove)
  window.removeEventListener('mouseup', onTableUp)
}

// ================= 表格增强: 搜索 / 排序 / 慢语句着色 =================
const search = ref('')
const sortKey = ref('')
const sortDir = ref<'asc' | 'desc'>('asc')

// 自动识别"耗时/代价/读取"类数值列, 用于相对慢语句着色(单位无关, 取 Top 比例)
const durCol = computed(() => {
  const re = /time|duration|elapsed|ms|seconds?|cost|cpu|reads?|writes?|logical|physical|spool|io/i
  return cols.value.find(c => re.test(c.name))?.name || null
})
const durMax = computed(() => {
  if (!durCol.value) return null
  let m = -Infinity
  for (const r of rows.value) {
    const v = Number(r[durCol.value])
    if (isFinite(v) && v > m) m = v
  }
  return m > 0 ? m : null
})
function rowMark(r: Record<string, unknown>): '' | 'warn' | 'bad' {
  if (durMax.value == null) return ''
  const v = Number(r[durCol.value!])
  if (!isFinite(v) || v <= 0) return ''
  if (v >= durMax.value * 0.8) return 'bad'
  if (v >= durMax.value * 0.5) return 'warn'
  return ''
}

const filteredRows = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return rows.value
  return rows.value.filter(r =>
    cols.value.some(c => String(r[c.name] ?? '').toLowerCase().includes(q)))
})
const sortedRows = computed(() => {
  const list = filteredRows.value
  if (!sortKey.value) return list
  const k = sortKey.value
  const dir = sortDir.value === 'asc' ? 1 : -1
  return [...list].sort((a, b) => {
    const av = a[k], bv = b[k]
    const an = Number(av), bn = Number(bv)
    if (isFinite(an) && isFinite(bn) && (an !== 0 || bn !== 0)) return (an - bn) * dir
    return String(av ?? '').localeCompare(String(bv ?? ''), 'zh') * dir
  })
})
function sortBy(name: string) {
  if (sortKey.value === name) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = name
    sortDir.value = 'asc'
  }
}

// ================= 复制 / 导出 / 预览 / 右键 =================
async function copyText(t: string, label = '已复制到剪贴板') {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(t)
    } else {
      const ta = document.createElement('textarea')
      ta.value = t
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      ta.remove()
    }
    ui.toast(label)
  } catch {
    ui.toast('复制失败', true)
  }
}
function copyCell(r: Record<string, unknown>, c: string) {
  copyText(cell(r[c]), '已复制单元格')
}
function copyRow(r: Record<string, unknown>) {
  copyText(cols.value.map(c => cell(r[c.name])).join('\t'), '已复制整行')
}
function copyAll() {
  const head = cols.value.map(c => c.name).join('\t')
  const body = sortedRows.value.map(r => cols.value.map(c => cell(r[c.name])).join('\t')).join('\n')
  copyText(head + '\n' + body, `已复制全部 (${sortedRows.value.length} 行)`)
}
function csvCell(s: string): string {
  if (/[",\r\n]/.test(s)) return '"' + s.replace(/"/g, '""') + '"'
  return s
}
function exportCsv() {
  const head = cols.value.map(c => csvCell(c.name)).join(',')
  const body = sortedRows.value
    .map(r => cols.value.map(c => csvCell(cell(r[c.name]))).join(','))
    .join('\r\n')
  const blob = new Blob(['\ufeff' + head + '\r\n' + body], { type: 'text/csv;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `explain_${tab.value?.dialect || 'result'}_${Date.now()}.csv`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(a.href)
  ui.toast('已导出 CSV')
}

const preview = ref<string | null>(null)
const previewTitle = ref('')
function openPreview(text: string, title: string) {
  if (!text) return
  preview.value = text
  previewTitle.value = title
}
function closePreview() { preview.value = null }

function onCellContext(e: MouseEvent, r: Record<string, unknown>, c: string) {
  e.preventDefault()
  e.stopPropagation()
  const items: CtxItem[] = [
    { label: '复制单元格', fn: () => copyCell(r, c) },
    isCodeCol(c)
      ? { label: '复制 SQL', fn: () => copyCell(r, c) }
      : { label: '复制该列值', fn: () => copyCell(r, c) },
    { sep: true },
    { label: '复制整行', fn: () => copyRow(r) },
    { label: '复制全部', fn: () => copyAll() },
  ]
  ui.showCtxMenu(e.clientX, e.clientY, items)
}

onMounted(() => {
  window.addEventListener('mousemove', onMoveTree)
  window.addEventListener('mouseup', onUpTree)
  initTableH()
  initPos()
  window.addEventListener('resize', onWinResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onMoveTree)
  window.removeEventListener('mouseup', onUpTree)
  window.removeEventListener('resize', onWinResize)
  removeWin()
})
</script>

<template>
  <div class="g-modal explain-card" :style="cardStyle" ref="card">
    <!-- 标题栏(拖拽手柄) -->
    <div class="explain-head" @mousedown="startDrag">
      <h3>执行计划 EXPLAIN
        <span v-if="isTree && tab?.dialect" class="dialect">
          · {{ tab.dialect === 'postgresql' ? 'PostgreSQL (ANALYZE 实测)' : 'MySQL (估算)' }}</span>
      </h3>
      <button class="x-btn no-drag" type="button" title="关闭" @mousedown.stop @click="ui.closeModal()">✕</button>
    </div>

    <div v-if="!tab" class="empty2 pad">未找到该执行计划结果</div>
    <div v-else-if="tab.error" class="sql-error pad">{{ tab.error }}</div>

    <div v-else class="explain-body">
      <div class="explain-sql">{{ tab.sql }}</div>

      <!-- 归一化 plan 树 -->
      <template v-if="isTree && treeView">
        <div class="er-tools no-drag">
          <button type="button" class="mini" @click="zoomBy(1.2)" title="放大">＋</button>
          <button type="button" class="mini" @click="zoomBy(1 / 1.2)" title="缩小">－</button>
          <button type="button" class="mini" @click="fit" title="适应">适应</button>
          <span class="hint">滚轮缩放 · 拖拽平移 · 红=瓶颈 橙=次瓶颈 ×N=估算行数偏差</span>
        </div>
        <svg :viewBox="`0 0 ${treeView.W} ${treeView.H}`"
             @wheel.stop.prevent="onWheel" @mousedown.prevent="onDown"
             :style="{ width: '100%', height: '64vh', display: 'block',
                       background: 'var(--panel, #fff)', borderRadius: '8px',
                       cursor: dragging ? 'grabbing' : 'grab', touchAction: 'none' }">
          <g :transform="`translate(${tx},${ty}) scale(${scale})`">
            <path v-for="(e, ei) in treeView.edges" :key="'e' + ei"
                  :d="`M ${e.x1} ${e.y1} C ${(e.x1 + e.x2) / 2} ${e.y1}, ${(e.x1 + e.x2) / 2} ${e.y2}, ${e.x2} ${e.y2}`"
                  fill="none" stroke="var(--text3)" stroke-width="1.2" />
            <g v-for="(t, ti) in treeView.nodes" :key="'n' + ti" :transform="`translate(${t.cx - NW / 2},${t.y})`">
              <rect :width="NW" :height="NH" rx="6"
                    :fill="t.mark === 'bottleneck' ? '#fdeceb' : t.mark === 'warn' ? '#fff8e6' : 'var(--panel, #fff)'"
                    :stroke="t.mark === 'bottleneck' ? 'var(--danger-solid)' : t.mark === 'warn' ? 'var(--warning-solid)' : 'var(--text3)'"
                    stroke-width="1.4" />
              <g v-if="t.rowsBias != null && (t.rowsBias > 2 || t.rowsBias < 0.5)">
                <rect :x="NW - 46" y="4" width="42" height="16" rx="8"
                      :fill="t.rowsBias > 10 ? 'var(--danger-solid)' : 'var(--warning-solid)'" />
                <text :x="NW - 25" y="15" font-size="10" fill="#fff" text-anchor="middle">
                  ×{{ t.rowsBias > 10 ? t.rowsBias.toFixed(0) : t.rowsBias.toFixed(1) }}</text>
              </g>
              <text x="10" y="20" font-size="12" font-weight="600" fill="var(--text)">
                {{ trunc(t.n.operation + (t.n.object ? ' · ' + t.n.object : '')) }}</text>
              <text x="10" y="40" font-size="11" fill="var(--text2, var(--text3))">
                <tspan>行 </tspan>
                <tspan v-if="t.n.rows_actual != null">~{{ fmt(t.n.rows_est) }} → 实 {{ fmt(t.n.rows_actual) }}</tspan>
                <tspan v-else-if="t.n.rows_est != null">~{{ fmt(t.n.rows_est) }} (估算)</tspan>
                <tspan v-else>-</tspan>
              </text>
              <text x="10" y="58" font-size="11" fill="var(--text2, var(--text3))">
                <tspan v-if="t.n.time_actual_ms != null">代价 {{ fmt(t.n.cost_est) }} · {{ fmt(t.n.time_actual_ms) }}ms</tspan>
                <tspan v-else-if="t.n.cost_est != null">代价 {{ fmt(t.n.cost_est) }} (估算)</tspan>
                <tspan v-else>代价 -</tspan>
              </text>
            </g>
          </g>
        </svg>
      </template>

      <!-- 单列文本 -->
      <pre v-else-if="singleCol" class="plan-pre">{{ planText }}</pre>

      <!-- 多列增强表格 -->
      <template v-else-if="cols.length">
        <div class="tbl-toolbar no-drag">
          <input class="search" v-model="search" type="text" placeholder="搜索 SQL / 任意列…" />
          <button class="tbtn" type="button" @click="copyAll">复制全部</button>
          <button class="tbtn" type="button" @click="exportCsv">导出 CSV</button>
          <span v-if="sortKey" class="sort-state" @click="sortKey = ''; sortDir = 'asc'">排序: {{ sortKey }} {{ sortDir === 'asc' ? '↑' : '↓' }} · 清除</span>
          <span class="hint">右键复制 · 双击代码单元格预览 · 拖标题移动 · 拖右下角缩放 · 拖表格底边调高</span>
        </div>
        <div class="tbl-scroll" :style="{ height: tableH + 'px' }">
          <table class="explain-tbl">
            <thead>
              <tr>
                <th v-for="c in cols" :key="c.name"
                    :class="{ sorted: sortKey === c.name }"
                    :title="'点击排序: ' + c.name"
                    @click="sortBy(c.name)">
                  <span class="th-name">{{ c.name }}</span>
                  <span v-if="sortKey === c.name" class="th-arrow">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in sortedRows" :key="i" :class="rowMark(r)">
                <td v-for="c in cols" :key="c.name"
                    :class="{ mono: isCodeCol(c.name) }"
                    :title="cell(r[c.name])"
                    @contextmenu="onCellContext($event, r, c.name)"
                    @dblclick="isCodeCol(c.name) && openPreview(cell(r[c.name]), c.name)">
                  {{ cell(r[c.name]) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="tbl-resizer no-drag" title="上下拖动调整表格高度" @mousedown.prevent.stop="startTableResize"></div>
        <div class="tbl-foot no-drag">
          <span class="hint">{{ sortedRows.length }} 行 / 共 {{ rows.length }} 行</span>
          <span v-if="durCol" class="hint">慢语句着色依据: {{ durCol }}（相对 Top 值）</span>
        </div>
      </template>

      <div v-else class="empty2 pad">该语句无结果集(可能为非 SELECT)</div>
    </div>

    <!-- 底部操作 -->
    <div class="acts no-drag">
      <button class="primary" type="button" @click="ui.closeModal()">关闭</button>
    </div>

    <!-- 代码预览浮层 -->
    <div v-if="preview" class="code-overlay" @mousedown.self="closePreview">
      <div class="code-box">
        <div class="code-bar">
          <span>{{ previewTitle }}</span>
          <button class="x-btn" type="button" title="关闭" @click="closePreview">✕</button>
        </div>
        <pre class="code-pre">{{ preview }}</pre>
      </div>
    </div>

    <!-- 缩放手柄 -->
    <div class="resize-h no-drag" title="拖动调整窗口大小" @mousedown.stop="startResize"></div>
  </div>
</template>

<style scoped>
/* 卡片: 覆盖 GenericModal 的 :deep(.g-modal) 居中/内边距/最大高, 改为固定定位 + flex 列 */
.explain-card {
  display: flex;
  flex-direction: column;
  padding: 0;
  max-height: none;
  overflow: hidden;
  border-radius: 10px;
}
.explain-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  cursor: move;
  user-select: none;
  flex-shrink: 0;
}
.explain-head h3 { margin: 0; font-size: 15px; font-weight: 600; }
.explain-head .dialect { color: var(--text3); font-weight: 400; font-size: 12px; }
.x-btn {
  width: 28px; height: 28px; line-height: 1; padding: 0;
  border: 1px solid var(--border); background: var(--panel2); color: var(--text2);
  border-radius: 6px; cursor: pointer; font-size: 13px; flex-shrink: 0;
}
.x-btn:hover { border-color: var(--danger-solid); color: var(--danger-solid); }

.explain-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 12px 16px;
  overflow: hidden;
}

.explain-sql { font-family: Consolas, Menlo, monospace; font-size: 12px; color: var(--text2);
  background: var(--panel2); border: 1px solid var(--border); border-radius: 6px;
  padding: 8px; margin-bottom: 10px; white-space: pre-wrap; word-break: break-all;
  max-height: 92px; overflow: auto; flex-shrink: 0; }
.plan-pre { max-height: 60vh; overflow: auto; white-space: pre; font-family: Consolas, Menlo, monospace;
  font-size: 12px; line-height: 1.5; background: var(--panel2); border: 1px solid var(--border);
  border-radius: 6px; padding: 10px; margin: 0; color: var(--text); }

/* ---------- 工具栏 ---------- */
.tbl-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; flex-shrink: 0; }
.tbl-toolbar .search { flex: 1; min-width: 160px; height: 30px; padding: 0 10px;
  border: 1px solid var(--border); border-radius: 6px; background: var(--panel2); color: var(--text); font-size: 13px; }
.tbl-toolbar .search:focus { outline: none; border-color: var(--primary); box-shadow: var(--ring); }
.tbl-toolbar .tbtn { height: 30px; padding: 0 12px; border: 1px solid var(--border); border-radius: 6px;
  background: var(--panel2); color: var(--text); font-size: 13px; cursor: pointer; }
.tbl-toolbar .tbtn:hover { border-color: var(--primary); color: var(--primary); }
.tbl-toolbar .hint { color: var(--text3); font-size: 12px; }
.tbl-toolbar .sort-state { color: var(--primary); font-size: 12px; cursor: pointer; }

/* ---------- 表格(修复竖排/错位/滚动不同步) ---------- */
.tbl-scroll { min-height: 0; overflow: auto; border: 1px solid var(--border); border-radius: 8px;
  width: 100%; box-sizing: border-box; }
.explain-tbl { border-collapse: separate; border-spacing: 0; width: max-content; min-width: 100%; font-size: 12px; }
.explain-tbl th, .explain-tbl td {
  text-align: left; padding: 5px 10px; border-bottom: 1px solid var(--border);
  vertical-align: top; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 420px;
}
.explain-tbl th {
  position: sticky; top: 0; z-index: 2; background: var(--panel2); color: var(--text);
  cursor: pointer; user-select: none; font-weight: 600;
  box-shadow: inset 0 -1px 0 var(--border);
}
.explain-tbl th:hover { color: var(--primary); }
.explain-tbl th.sorted { color: var(--primary); }
.explain-tbl th .th-arrow { margin-left: 3px; font-size: 11px; }
.explain-tbl td { color: var(--text); }
.explain-tbl td.mono { font-family: Consolas, Menlo, monospace; }
.explain-tbl tbody tr:hover td { background: var(--primary-bg, rgba(22, 93, 255, 0.06)); }
.explain-tbl tbody tr.warn td { background: #fff8e6; }
.explain-tbl tbody tr.bad td { background: #fdeceb; }
.explain-tbl tbody tr.warn:hover td { background: #fdf0d2; }
.explain-tbl tbody tr.bad:hover td { background: #fbd9d6; }

.tbl-foot { display: flex; gap: 14px; margin-top: 6px; flex-shrink: 0; }

/* ---------- 表格高度拖拽条 ---------- */
.tbl-resizer { height: 8px; flex-shrink: 0; cursor: row-resize; position: relative;
  display: flex; align-items: center; justify-content: center; }
.tbl-resizer::after { content: ''; display: block; width: 46px; height: 4px; border-radius: 3px;
  background: var(--border); transition: background 0.12s; }
.tbl-resizer:hover::after, .tbl-resizer:active::after { background: var(--primary); }

/* ---------- 代码预览浮层 ---------- */
.code-overlay { position: absolute; inset: 0; background: rgba(0, 0, 0, 0.38);
  display: flex; align-items: center; justify-content: center; padding: 24px; z-index: 5; }
.code-box { width: 92%; height: 82%; background: var(--panel); border-radius: 10px;
  display: flex; flex-direction: column; overflow: hidden; box-shadow: 0 12px 40px rgba(0, 0, 0, 0.3); }
.code-bar { display: flex; justify-content: space-between; align-items: center;
  padding: 10px 14px; border-bottom: 1px solid var(--border); font-weight: 600; flex-shrink: 0; }
.code-pre { flex: 1; margin: 0; overflow: auto; padding: 14px; white-space: pre-wrap; word-break: break-all;
  font-family: Consolas, Menlo, monospace; font-size: 12px; line-height: 1.55;
  color: var(--text); background: var(--panel2); }

/* ---------- 缩放手柄 ---------- */
.resize-h { position: absolute; right: 0; bottom: 0; width: 18px; height: 18px;
  cursor: nwse-resize; z-index: 6;
  background:
    linear-gradient(135deg, transparent 0 50%, var(--text3) 50% 56%, transparent 56% 68%, var(--text3) 68% 74%, transparent 74% 100%);
}

.sql-error { color: var(--danger-solid); white-space: pre-wrap; }
.pad { padding: 20px; }
.empty2 { color: var(--text3); }

/* 树模式工具条 */
.er-tools { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; flex-shrink: 0; }
.er-tools .mini { width: 30px; height: 26px; line-height: 1; padding: 0; font-size: 14px;
  border: 1px solid var(--border); background: var(--panel2); color: var(--text); border-radius: 6px; cursor: pointer; }
.er-tools .mini:hover { border-color: var(--primary); }
.er-tools .hint { color: var(--text3); font-size: 12px; margin-left: 4px; }

.acts { padding: 12px 16px; border-top: 1px solid var(--border); display: flex; justify-content: flex-end; flex-shrink: 0; }
</style>
