<script setup lang="ts">
// ER 关系图(取代旧版 ObjectTree.openEr 的 ui.showModal HTML 注入)。
// /api/er -> 中心表 + 外键关联表; 用 Vue 模板渲染 SVG(无 v-html / 无注入), 表名/列名由插值自动转义。
// 由 GenericModal 在共享遮罩内渲染, 本组件只渲染 .g-modal 卡片根。
import { ref, onMounted } from 'vue'
import { useUIStore } from '@/stores/ui'
import { getEr } from '@/api/database'
import { errMsg } from '@/utils/err'

const props = defineProps<{ s: string; t: string }>()
const ui = useUIStore()

const loading = ref(true)
const error = ref('')
const W = ref(600)
const H = ref(400)
const TW = 190, TH = 26, TDH = 18, PAD = 30

interface ErColumn { name: string; type?: string; isPk?: boolean }
interface ErTable { schema: string; name: string; columns: ErColumn[]; pk: string[] }
interface ErRel { from_schema: string; from_table: string; to_schema: string; to_table: string; from_columns: string[]; to_columns: string[] }

interface Box { key: string; x: number; y: number; h: number; name: string; columns: ErColumn[] }
interface Edge { d: string; mx: number; my: number; label: string }

const boxes = ref<Box[]>([])
const edges = ref<Edge[]>([])

onMounted(async () => {
  try {
    const d = await getEr(props.s, props.t) as unknown as { tables: ErTable[]; relations: ErRel[] }
    const tables = d.tables || []
    const rels = d.relations || []
    if (!tables.length) { error.value = '无表数据'; return }
    layout(tables, rels)
  } catch (e) { error.value = 'ER 图加载失败: ' + errMsg(e) }
  finally { loading.value = false }
})

function layout(tables: ErTable[], rels: ErRel[]) {
  const centerKey = props.s + '.' + props.t
  const center = tables.find(t => (t.schema + '.' + t.name) === centerKey) || tables[0]
  const ordered = [center,
    ...tables.filter(t => (t.schema + '.' + t.name) !== centerKey)
      .sort((a, b) => b.columns.length - a.columns.length)]
  const n = ordered.length
  const cols = Math.max(1, Math.ceil(Math.sqrt(n * 1.4)))
  const rowsN = Math.ceil(n / cols)
  const maxCols = Math.max(1, ...ordered.map(t => t.columns.length))
  const cellW = TW + PAD
  const cellH = 90 + maxCols * TDH + PAD
  W.value = Math.max(600, cols * cellW + PAD)
  H.value = Math.max(400, rowsN * cellH + PAD)
  const pos: Record<string, { x: number; y: number }> = {}
  ordered.forEach((t, i) => {
    const cx = i % cols, cy = Math.floor(i / cols)
    pos[t.schema + '.' + t.name] = { x: PAD + cx * cellW, y: PAD + cy * cellH }
  })
  boxes.value = ordered.map(t => {
    const p = pos[t.schema + '.' + t.name]
    return {
      key: t.schema + '.' + t.name,
      x: p.x, y: p.y,
      h: TH + t.columns.length * TDH,
      name: t.name,
      columns: t.columns.map(c => ({ name: c.name, type: c.type, isPk: t.pk.includes(c.name) })),
    }
  })
  edges.value = rels.map(r => {
    const from = pos[r.from_schema + '.' + r.from_table]
    const to = pos[r.to_schema + '.' + r.to_table]
    if (!from || !to) return null
    const x1 = from.x + TW, y1 = from.y + TH + 8
    const x2 = to.x, y2 = to.y + TH + 8
    const mx = (x1 + x2) / 2
    const label = (r.from_columns || []).map((c, i) => c + ' → ' + ((r.to_columns || [])[i] || '')).join(', ')
    return { d: `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`, mx, my: (y1 + y2) / 2 - 4, label }
  }).filter(Boolean) as Edge[]
}
</script>

<template>
  <div class="g-modal" style="width:auto;max-width:94vw">
    <h3>ER 关系图 · {{ s }}.{{ t }}
      <span v-if="!loading && !error" style="color:var(--text3);font-weight:400;font-size:12px">
        ({{ boxes.length }} 表 · {{ edges.length }} 关系)</span>
    </h3>
    <div v-if="loading" class="empty2" style="padding:20px">加载中...</div>
    <div v-else-if="error" class="empty2" style="padding:20px">{{ error }}</div>
    <div v-else style="overflow:auto;max-height:70vh">
      <svg :viewBox="`0 0 ${W} ${H}`"
           :style="{ width: '100%', minWidth: W + 'px', background: 'var(--panel, #fff)', borderRadius: '8px' }">
        <defs>
          <marker id="erArrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7"
                  orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--primary)" />
          </marker>
        </defs>
        <g v-for="b in boxes" :key="b.key">
          <rect :x="b.x" :y="b.y" :width="TW" :height="b.h" rx="6" fill="var(--panel, #fff)" stroke="var(--text3)" />
          <rect :x="b.x" :y="b.y" :width="TW" :height="TH" rx="6" fill="var(--primary)" opacity="0.15" />
          <text :x="b.x + 8" :y="b.y + 17" font-size="12" font-weight="600" fill="var(--text)">{{ b.name }}</text>
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
      </svg>
    </div>
    <div class="acts"><button class="primary" type="button" @click="ui.closeModal()">关闭</button></div>
  </div>
</template>
