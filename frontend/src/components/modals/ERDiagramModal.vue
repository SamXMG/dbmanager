<script setup lang="ts">
// ER 关系图(取代旧版 ObjectTree.openEr 的 ui.showModal HTML 注入)。
// /api/er -> 中心表 + 外键关联表; 用 Vue 模板渲染 SVG(无 v-html / 无注入), 表名/列名由插值自动转义。
// 布局: 以中心表为源做双向 BFS 定向分层(父表在左、子表在右), 同层按关联度数居中以减少交叉;
// 交互: 滚轮缩放 / 拖拽平移 / 适应按钮。由 GenericModal 在共享遮罩内渲染, 本组件只渲染 .g-modal 卡片根。
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useUIStore } from '@/stores/ui'
import { getEr } from '@/api/database'
import { errMsg } from '@/utils/err'

const props = defineProps<{ s: string; t: string }>()
const ui = useUIStore()

const loading = ref(true)
const error = ref('')
const TW = 200, TH = 28, TDH = 18, PAD = 24, HGAP = 36, VGAP = 40

interface ErColumn { name: string; type?: string; isPk?: boolean }
interface ErTable { schema: string; name: string; columns: ErColumn[]; pk: string[] }
interface ErRel { from_schema: string; from_table: string; to_schema: string; to_table: string; from_columns: string[]; to_columns: string[] }

interface Box { key: string; x: number; y: number; h: number; name: string; schema: string; columns: ErColumn[]; layer: number; deg: number }
interface Edge { d: string; mx: number; my: number; label: string }

const boxes = ref<Box[]>([])
const edges = ref<Edge[]>([])
const W = ref(600)
const H = ref(400)

// ---- pan / zoom ----
const tx = ref(0)
const ty = ref(0)
const scale = ref(1)
let dragging = false
let lastX = 0
let lastY = 0

function keyOf(schema: string, name: string) { return (schema || '') + '.' + name }

function layout(tables: ErTable[], rels: ErRel[]) {
  const centerKey = keyOf(props.s, props.t)
  const nodes = new Map<string, { table: ErTable; layer: number; deg: number }>()
  for (const t of tables) {
    const k = keyOf(t.schema, t.name)
    nodes.set(k, { table: t, layer: 0, deg: 0 })
  }
  const edgesKV: { u: string; v: string }[] = []
  for (const r of rels) {
    const u = keyOf(r.from_schema, r.from_table)
    const v = keyOf(r.to_schema, r.to_table)
    if (nodes.has(u) && nodes.has(v)) {
      edgesKV.push({ u, v })
      nodes.get(u)!.deg++
      nodes.get(v)!.deg++
    }
  }
  // 双向 BFS 定向分层: u(外键引用方=子) 层 > v(被引用方=父) 层
  const outAdj = new Map<string, string[]>()
  const inAdj = new Map<string, string[]>()
  for (const e of edgesKV) {
    if (!outAdj.has(e.u)) outAdj.set(e.u, [])
    outAdj.get(e.u)!.push(e.v)
    if (!inAdj.has(e.v)) inAdj.set(e.v, [])
    inAdj.get(e.v)!.push(e.u)
  }
  const layer = new Map<string, number>()
  const seen = new Set<string>()
  const start = nodes.has(centerKey) ? centerKey
    : (tables[0] ? keyOf(tables[0].schema, tables[0].name) : '')
  if (!start) return
  layer.set(start, 0)
  seen.add(start)
  const q: string[] = [start]
  while (q.length) {
    const x = q.shift()!
    const lx = layer.get(x)!
    for (const v of (outAdj.get(x) || [])) {        // x 是子, v 是父 -> 父层更小
      if (!seen.has(v)) { seen.add(v); layer.set(v, lx - 1); q.push(v) }
    }
    for (const u of (inAdj.get(x) || [])) {          // x 是父, u 是子 -> 子层更大
      if (!seen.has(u)) { seen.add(u); layer.set(u, lx + 1); q.push(u) }
    }
  }
  // 孤立节点兜底(ER 邻接图理论上不会触发): 顺延到新层
  let maxL = 0
  for (const [k, info] of nodes) {
    if (!seen.has(k)) { maxL++; layer.set(k, maxL + 1) }
    else maxL = Math.max(maxL, layer.get(k)!)
  }

  // 按层分组, 同层按关联度数降序(重要表居中) + key 升序稳定排序
  const byLayer = new Map<number, string[]>()
  for (const [k] of nodes) {
    const l = layer.get(k)!
    if (!byLayer.has(l)) byLayer.set(l, [])
    byLayer.get(l)!.push(k)
  }
  for (const [, ks] of byLayer) {
    ks.sort((a, b) => (nodes.get(b)!.deg - nodes.get(a)!.deg) || (a < b ? -1 : a > b ? 1 : 0))
  }
  const layers = [...byLayer.keys()].sort((a, b) => a - b)

  // 每层高度取该层最高 box; 每层宽度用于水平居中
  const layerH = new Map<number, number>()
  const layerWidth = new Map<number, number>()
  let maxWidth = TW
  for (const l of layers) {
    let mh = TH
    for (const k of byLayer.get(l)!) {
      const tb = nodes.get(k)!.table
      mh = Math.max(mh, TH + tb.columns.length * TDH)
    }
    layerH.set(l, mh)
    const n = byLayer.get(l)!.length
    const w = n * TW + (n - 1) * HGAP
    layerWidth.set(l, w)
    maxWidth = Math.max(maxWidth, w)
  }

  const boxMap = new Map<string, Box>()
  let cumY = PAD
  for (const l of layers) {
    const ks = byLayer.get(l)!
    const lw = layerWidth.get(l)!
    const startX = PAD + (maxWidth - lw) / 2
    const lh = layerH.get(l)!
    ks.forEach((k, i) => {
      const tb = nodes.get(k)!.table
      const bx = startX + i * (TW + HGAP)
      const bh = TH + tb.columns.length * TDH
      boxMap.set(k, {
        key: k, x: bx, y: cumY, h: bh, name: tb.name, schema: tb.schema,
        columns: tb.columns.map(c => ({ name: c.name, type: c.type, isPk: tb.pk.includes(c.name) })),
        layer: l, deg: nodes.get(k)!.deg,
      })
    })
    cumY += lh + VGAP
  }
  W.value = maxWidth + PAD * 2
  H.value = Math.max(400, cumY - VGAP + PAD)

  boxes.value = [...boxMap.values()]
  edges.value = edgesKV.map(e => {
    const u = boxMap.get(e.u), v = boxMap.get(e.v)
    if (!u || !v) return null
    const x1 = u.x + TW, y1 = u.y + TH / 2
    const x2 = v.x, y2 = v.y + TH / 2
    const mx = (x1 + x2) / 2
    const rel = rels.find(r =>
      keyOf(r.from_schema, r.from_table) === e.u && keyOf(r.to_schema, r.to_table) === e.v)
    const label = rel
      ? (rel.from_columns || []).map((c, i) => c + ' → ' + ((rel.to_columns || [])[i] || '')).join(', ')
      : ''
    return { d: `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`, mx, my: (y1 + y2) / 2 - 4, label }
  }).filter(Boolean) as Edge[]
}

function onWheel(e: WheelEvent) {
  e.preventDefault()
  const delta = e.deltaY < 0 ? 1.12 : 1 / 1.12
  const ns = Math.min(3, Math.max(0.2, scale.value * delta))
  const cx = W.value / 2, cy = H.value / 2
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
  const cx = W.value / 2, cy = H.value / 2
  tx.value = cx - (cx - tx.value) * (ns / scale.value)
  ty.value = cy - (cy - ty.value) * (ns / scale.value)
  scale.value = ns
}
function fit() { tx.value = 0; ty.value = 0; scale.value = 1 }

onMounted(async () => {
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
  try {
    const d = await getEr(props.s, props.t) as unknown as { tables: ErTable[]; relations: ErRel[] }
    const tables = d.tables || []
    const rels = d.relations || []
    if (!tables.length) { error.value = '无表数据'; return }
    layout(tables, rels)
  } catch (e) { error.value = 'ER 图加载失败: ' + errMsg(e) }
  finally { loading.value = false }
})
onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onMove)
  window.removeEventListener('mouseup', onUp)
})
</script>

<template>
  <div class="g-modal" style="width:auto;max-width:94vw">
    <h3>ER 关系图 · {{ s }}.{{ t }}
      <span v-if="!loading && !error" style="color:var(--text3);font-weight:400;font-size:12px">
        ({{ boxes.length }} 表 · {{ edges.length }} 关系)</span>
    </h3>
    <div v-if="loading" class="empty2" style="padding:20px">加载中...</div>
    <div v-else-if="error" class="empty2" style="padding:20px">{{ error }}</div>
    <div v-else>
      <div class="er-tools">
        <button type="button" class="mini" @click="zoomBy(1.2)" title="放大">＋</button>
        <button type="button" class="mini" @click="zoomBy(1/1.2)" title="缩小">－</button>
        <button type="button" class="mini" @click="fit" title="适应">适应</button>
        <span class="hint">滚轮缩放 · 拖拽平移</span>
      </div>
      <svg :viewBox="`0 0 ${W} ${H}`"
           @wheel.stop.prevent="onWheel" @mousedown.prevent="onDown"
           :style="{ width: '100%', height: '66vh', display: 'block',
                     background: 'var(--panel, #fff)', borderRadius: '8px',
                     cursor: dragging ? 'grabbing' : 'grab', touchAction: 'none' }">
        <defs>
          <marker id="erArrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7"
                  orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--primary)" />
          </marker>
        </defs>
        <g :transform="`translate(${tx},${ty}) scale(${scale})`">
          <g v-for="b in boxes" :key="b.key">
            <rect :x="b.x" :y="b.y" :width="TW" :height="b.h" rx="6"
                  fill="var(--panel, #fff)" stroke="var(--text3)" />
            <rect :x="b.x" :y="b.y" :width="TW" :height="TH" rx="6" fill="var(--primary)" opacity="0.15" />
            <text :x="b.x + 8" :y="b.y + 18" font-size="12" font-weight="600" fill="var(--text)">{{ b.name }}</text>
            <template v-for="(c, ci) in b.columns" :key="c.name">
              <text :x="b.x + 8" :y="b.y + TH + 14 + ci * TDH" font-size="11"
                    :fill="c.isPk ? 'var(--warning-solid)' : 'var(--text2, var(--text3))'">{{ c.name }}</text>
              <text :x="b.x + TW - 8" :y="b.y + TH + 14 + ci * TDH" font-size="10" text-anchor="end"
                    fill="var(--text3)">{{ (c.type || '').split('(')[0] }}</text>
            </template>
          </g>
          <path v-for="(e, ei) in edges" :key="'e' + ei" :d="e.d" fill="none"
                stroke="var(--primary)" stroke-width="1.2" marker-end="url(#erArrow)" />
          <text v-for="(e, ei) in edges" :key="'el' + ei" :x="e.mx" :y="e.my"
                font-size="10" fill="var(--primary)" text-anchor="middle">{{ e.label }}</text>
        </g>
      </svg>
    </div>
    <div class="acts"><button class="primary" type="button" @click="ui.closeModal()">关闭</button></div>
  </div>
</template>

<style scoped>
.er-tools { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; }
.er-tools .mini { width: 30px; height: 26px; line-height: 1; padding: 0; font-size: 14px;
  border: 1px solid var(--border); background: var(--panel2); color: var(--text); border-radius: 6px; cursor: pointer; }
.er-tools .mini:hover { border-color: var(--primary); }
.er-tools .hint { color: var(--text3); font-size: 12px; margin-left: 4px; }
</style>
