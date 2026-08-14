<script setup lang="ts">
// EXPLAIN 执行计划可视化(取代旧版 SqlWorkbench 无弹窗/文本态展示)。
// mode=tree(PG/MySQL 归一化 plan): 递归渲染 SVG 纵向树, 计算每个节点的
//   独占耗时/代价占比(瓶颈红/次瓶颈橙)与 估算行数 vs 实际行数 偏差标记; 支持滚轮缩放/拖拽平移。
// mode=table(MySQL 旧表/SQLite): 多列表格; mode=text(MSSQL/Oracle/单列): 原缩进文本。
// 由 GenericModal 在共享遮罩内渲染, 本组件只渲染 .g-modal 卡片根。
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useUIStore } from '@/stores/ui'
import { useSqlStore } from '@/stores/sql'
import type { PlanNode } from '@/api/sql'

const props = defineProps<{ tabId: number }>()
const ui = useUIStore()
const sqlStore = useSqlStore()

const tab = computed(() => sqlStore.tabs.find(t => t.id === props.tabId) || null)
const cols = computed(() => tab.value?.columns || [])
const rows = computed(() => tab.value?.rows || [])

// 单列计划(PostgreSQL / SQLite 的 QUERY PLAN)按原缩进显示; 多列(Mysql)走表格
const singleCol = computed(() => cols.value.length === 1)
const colName = computed(() => cols.value[0]?.name || '')
const planText = computed(() =>
  (rows.value || []).map(r => String(r[colName.value] ?? '')).join('\n'))
const isTree = computed(() => tab.value?.mode === 'tree' && !!tab.value?.plan)

function cell(v: unknown): string {
  if (v === null || v === undefined) return ''
  return String(v)
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
function onMove(e: MouseEvent) {
  if (!dragging) return
  tx.value += (e.clientX - lastX) / scale.value
  ty.value += (e.clientY - lastY) / scale.value
  lastX = e.clientX
  lastY = e.clientY
}
function onUp() { dragging = false }
function zoomBy(f: number) {
  const ns = Math.min(3, Math.max(0.2, scale.value * f))
  const cx = (treeView.value?.W ?? 600) / 2
  const cy = (treeView.value?.H ?? 400) / 2
  tx.value = cx - (cx - tx.value) * (ns / scale.value)
  ty.value = cy - (cy - ty.value) * (ns / scale.value)
  scale.value = ns
}
function fit() { tx.value = 0; ty.value = 0; scale.value = 1 }

onMounted(() => {
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
})
onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onMove)
  window.removeEventListener('mouseup', onUp)
})
</script>

<template>
  <div class="g-modal" style="width:820px;max-width:96vw">
    <h3>执行计划 EXPLAIN
      <span v-if="isTree && tab?.dialect" style="color:var(--text3);font-weight:400;font-size:12px">
        · {{ tab.dialect === 'postgresql' ? 'PostgreSQL (ANALYZE 实测)' : 'MySQL (估算)' }}</span>
    </h3>
    <div v-if="tab" class="explain-sql">{{ tab.sql }}</div>

    <div v-if="!tab" class="empty2" style="padding:20px">未找到该执行计划结果</div>
    <div v-else-if="tab.error" class="sql-error">{{ tab.error }}</div>

    <!-- 归一化 plan 树 -->
    <template v-else-if="isTree && treeView">
      <div class="er-tools">
        <button type="button" class="mini" @click="zoomBy(1.2)" title="放大">＋</button>
        <button type="button" class="mini" @click="zoomBy(1/1.2)" title="缩小">－</button>
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
            <!-- 偏差标记 -->
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
    <!-- 多列表格 -->
    <table v-else-if="cols.length" class="explain-tbl">
      <thead><tr><th v-for="c in cols" :key="c.name">{{ c.name }}</th></tr></thead>
      <tbody>
        <tr v-for="(r, i) in rows" :key="i">
          <td v-for="c in cols" :key="c.name" :title="cell(r[c.name])">{{ cell(r[c.name]) }}</td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty2">该语句无结果集(可能为非 SELECT)</div>

    <div class="acts"><button class="primary" type="button" @click="ui.closeModal()">关闭</button></div>
  </div>
</template>

<style scoped>
.explain-sql { font-family: Consolas, monospace; font-size: 12px; color: var(--text2);
  background: var(--panel2); border: 1px solid var(--border); border-radius: 6px;
  padding: 8px; margin-bottom: 10px; white-space: pre-wrap; word-break: break-all; }
.plan-pre { max-height: 60vh; overflow: auto; white-space: pre; font-family: Consolas, monospace;
  font-size: 12px; line-height: 1.5; background: var(--panel2); border: 1px solid var(--border);
  border-radius: 6px; padding: 10px; margin: 0; color: var(--text); }
.explain-tbl { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 4px;
  max-height: 60vh; overflow: auto; display: block; }
.explain-tbl th, .explain-tbl td { text-align: left; padding: 4px 8px; border-bottom: 1px solid var(--border);
  vertical-align: top; white-space: pre-wrap; word-break: break-all; }
.explain-tbl th { position: sticky; top: 0; background: var(--panel2); color: var(--text); }
.sql-error { color: var(--danger-solid); white-space: pre-wrap; }
.er-tools { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; }
.er-tools .mini { width: 30px; height: 26px; line-height: 1; padding: 0; font-size: 14px;
  border: 1px solid var(--border); background: var(--panel2); color: var(--text); border-radius: 6px; cursor: pointer; }
.er-tools .mini:hover { border-color: var(--primary); }
.er-tools .hint { color: var(--text3); font-size: 12px; margin-left: 4px; }
</style>
