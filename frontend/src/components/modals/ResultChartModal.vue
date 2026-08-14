<script setup lang="ts">
// 结果集图表(取代旧版 SqlWorkbench 无图表能力)。
// 读取 sqlStore.activeTab 当前结果: 选数值列作 Y、文本列作 X/分组轴, 渲染 SVG 柱状/折线/饼图(纯模板, 无注入)。
// 由 GenericModal 在共享遮罩内渲染, 本组件只渲染 .g-modal 卡片根。
import { ref, computed, onMounted } from 'vue'
import { useUIStore } from '@/stores/ui'
import { useSqlStore } from '@/stores/sql'

const ui = useUIStore()
const sqlStore = useSqlStore()

const tab = computed(() => sqlStore.activeTab)
const cols = computed(() => tab.value?.columns || [])
const rows = computed(() => tab.value?.rows || [])

function toNum(v: unknown): number {
  if (typeof v === 'number') return v
  if (typeof v === 'string' && v.trim() !== '' && !isNaN(Number(v))) return Number(v)
  return NaN
}
const numericCols = computed(() =>
  cols.value.filter(c => (rows.value || []).some(r => isFinite(toNum(r[c.name])))))
const catCols = computed(() => cols.value.filter(c => !numericCols.value.includes(c)))

const chartType = ref('bar') // bar | line | pie
const valRef = ref('')
const catRef = ref('')

// 超过该数量柱体/点时截断(保证可读), 并提示
const MAX_BARS = 60
const points = computed(() => {
  const vc = valRef.value
  if (!vc) return []
  const data = (rows.value || []).map((r, i) => ({
    cat: catRef.value ? String(r[catRef.value] ?? '') : '#' + (i + 1),
    v: toNum(r[vc]),
  }))
  const finite = data.filter(p => isFinite(p.v))
  return finite.length > MAX_BARS ? finite.slice(0, MAX_BARS) : finite
})

// 饼图聚合: 按 cat 分组求和(仅计非负值)
const pieData = computed(() => {
  const m = new Map<string, number>()
  for (const p of points.value) {
    if (p.v < 0) continue
    m.set(p.cat, (m.get(p.cat) || 0) + p.v)
  }
  const total = [...m.values()].reduce((a, b) => a + b, 0)
  const arr = [...m.entries()].map(([cat, v]) => ({ cat, v, pct: total ? v / total : 0 }))
  return { arr, total }
})

const Wc = 660, Hc = 340, padL = 52, padR = 16, padT = 16, padB = 56
const plotH = Hc - padT - padB
const maxV = computed(() => Math.max(0, ...points.value.map(p => p.v), 1))
const bars = computed(() => {
  const n = points.value.length
  if (!n) return []
  const plotW = Wc - padL - padR
  const bw = plotW / n
  const max = maxV.value || 1
  return points.value.map((p, i) => {
    const h = (p.v / max) * plotH
    const x = padL + i * bw
    const y = padT + plotH - h
    return { x, y, w: Math.max(1, bw - 6), h, cat: p.cat, v: p.v }
  })
})
const linePoints = computed(() =>
  bars.value.map(b => ({ x: b.x + 3 + b.w / 2, y: b.y, cat: b.cat, v: b.v })))
const linePath = computed(() => linePoints.value.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' '))

// 饼图几何
const pieCx = Wc / 2, pieCy = Hc / 2 - 6, pieR = 124
const piePalette = ['#4f8cff', '#36c2a6', '#f5a623', '#e0566f', '#8b6cf0', '#3fb6e0', '#d9844f', '#6cc24a']
const pieSlices = computed(() => {
  const { arr, total } = pieData.value
  if (!total) return []
  let acc = 0
  return arr.map((d, i) => {
    const a0 = acc * Math.PI * 2
    acc += d.pct
    const a1 = acc * Math.PI * 2
    const x0 = pieCx + pieR * Math.cos(a0 - Math.PI / 2)
    const y0 = pieCy + pieR * Math.sin(a0 - Math.PI / 2)
    const x1 = pieCx + pieR * Math.cos(a1 - Math.PI / 2)
    const y1 = pieCy + pieR * Math.sin(a1 - Math.PI / 2)
    const large = a1 - a0 > Math.PI ? 1 : 0
    const mid = (a0 + a1) / 2 - Math.PI / 2
    const lx = pieCx + (pieR + 16) * Math.cos(mid)
    const ly = pieCy + (pieR + 16) * Math.sin(mid)
    return {
      cat: d.cat, v: d.v, pct: d.pct, color: piePalette[i % piePalette.length],
      x0, y0, x1, y1, large, lx, ly,
    }
  })
})

function fmtNum(v: number): string {
  if (Math.abs(v) >= 1000) return (v / 1000).toFixed(1) + 'k'
  return String(Math.round(v * 100) / 100)
}
function trunc(s: string): string {
  return s.length > 10 ? s.slice(0, 9) + '…' : s
}

onMounted(() => {
  if (numericCols.value.length) valRef.value = numericCols.value[0].name
  if (catCols.value.length) catRef.value = catCols.value[0].name
})
</script>

<template>
  <div class="g-modal" style="width:760px;max-width:94vw">
    <h3>结果图表</h3>

    <div v-if="!cols.length" class="empty2" style="padding:20px">当前没有可绘制的结果集</div>
    <template v-else>
      <div v-if="!numericCols.length" class="empty2" style="padding:16px">结果集无数值列, 无法绘图</div>
      <template v-else>
        <div class="chart-ctrls">
          <label>图表类型
            <select v-model="chartType">
              <option value="bar">柱状图</option>
              <option value="line">折线图</option>
              <option value="pie">饼图</option>
            </select>
          </label>
          <label>数值列(Y)
            <select v-model="valRef">
              <option v-for="c in numericCols" :key="c.name" :value="c.name">{{ c.name }}</option>
            </select>
          </label>
          <label>{{ chartType === 'pie' ? '分组' : 'X 轴' }}
            <select v-model="catRef">
              <option value="">行号</option>
              <option v-for="c in catCols" :key="c.name" :value="c.name">{{ c.name }}</option>
            </select>
          </label>
          <span v-if="points.length >= MAX_BARS" class="chart-note">仅显示前 {{ MAX_BARS }} 行</span>
        </div>

        <!-- 柱状图 -->
        <svg v-if="chartType === 'bar'" :viewBox="`0 0 ${Wc} ${Hc}`"
             :style="{ width: '100%', minWidth: '640px', background: 'var(--panel, #fff)', borderRadius: '8px', marginTop: '8px' }">
          <line :x1="padL" :y1="padT" :x2="padL" :y2="Hc - padB" stroke="var(--border2, var(--border))" />
          <line :x1="padL" :y1="Hc - padB" :x2="Wc - padR" :y2="Hc - padB" stroke="var(--border2, var(--border))" />
          <text :x="padL - 6" :y="padT + plotH + 3" text-anchor="end" font-size="10" fill="var(--text3)">0</text>
          <text :x="padL - 6" :y="padT + 4" text-anchor="end" font-size="10" fill="var(--text3)">{{ Math.round(maxV) }}</text>
          <g v-for="(b, i) in bars" :key="i">
            <rect :x="b.x + 3" :y="b.y" :width="b.w" :height="b.h" fill="var(--primary)" rx="2" />
            <text :x="b.x + 3 + b.w / 2" :y="b.y - 4" text-anchor="middle" font-size="10" fill="var(--text2)">{{ fmtNum(b.v) }}</text>
            <text :x="b.x + 3 + b.w / 2" :y="Hc - padB + 14" text-anchor="middle" font-size="9" fill="var(--text3)">{{ trunc(b.cat) }}</text>
          </g>
        </svg>

        <!-- 折线图 -->
        <svg v-else-if="chartType === 'line'" :viewBox="`0 0 ${Wc} ${Hc}`"
             :style="{ width: '100%', minWidth: '640px', background: 'var(--panel, #fff)', borderRadius: '8px', marginTop: '8px' }">
          <line :x1="padL" :y1="padT" :x2="padL" :y2="Hc - padB" stroke="var(--border2, var(--border))" />
          <line :x1="padL" :y1="Hc - padB" :x2="Wc - padR" :y2="Hc - padB" stroke="var(--border2, var(--border))" />
          <text :x="padL - 6" :y="padT + plotH + 3" text-anchor="end" font-size="10" fill="var(--text3)">0</text>
          <text :x="padL - 6" :y="padT + 4" text-anchor="end" font-size="10" fill="var(--text3)">{{ Math.round(maxV) }}</text>
          <polyline :points="linePath" fill="none" stroke="var(--primary)" stroke-width="2" />
          <g v-for="(p, i) in linePoints" :key="i">
            <circle :cx="p.x" :cy="p.y" r="3" fill="var(--primary)" />
            <text :x="p.x" :y="p.y - 6" text-anchor="middle" font-size="10" fill="var(--text2)">{{ fmtNum(p.v) }}</text>
            <text :x="p.x" :y="Hc - padB + 14" text-anchor="middle" font-size="9" fill="var(--text3)">{{ trunc(p.cat) }}</text>
          </g>
        </svg>

        <!-- 饼图 -->
        <svg v-else :viewBox="`0 0 ${Wc} ${Hc}`"
             :style="{ width: '100%', minWidth: '640px', background: 'var(--panel, #fff)', borderRadius: '8px', marginTop: '8px' }">
          <template v-if="pieSlices.length">
            <path v-for="(s, i) in pieSlices" :key="i"
                  :d="`M ${pieCx} ${pieCy} L ${s.x0.toFixed(1)} ${s.y0.toFixed(1)} A ${pieR} ${pieR} 0 ${s.large} 1 ${s.x1.toFixed(1)} ${s.y1.toFixed(1)} Z`"
                  :fill="s.color" stroke="var(--panel, #fff)" stroke-width="1" />
            <text v-for="(s, i) in pieSlices" :key="'l' + i"
                  :x="s.lx.toFixed(1)" :y="s.ly.toFixed(1)" text-anchor="middle" font-size="10"
                  :fill="i < 4 ? 'var(--text)' : 'var(--text2)'">{{ (s.pct * 100).toFixed(1) }}%</text>
          </template>
          <text v-else :x="pieCx" :y="pieCy" text-anchor="middle" font-size="12" fill="var(--text3)">无可汇总的非负数值</text>
        </svg>

        <!-- 饼图图例 -->
        <div v-if="chartType === 'pie' && pieSlices.length" class="pie-legend">
          <span v-for="(s, i) in pieSlices" :key="'leg' + i" class="pie-leg-item">
            <i :style="{ background: s.color }"></i>{{ trunc(s.cat) }} · {{ fmtNum(s.v) }}
          </span>
        </div>
      </template>
    </template>

    <div class="acts"><button class="primary" type="button" @click="ui.closeModal()">关闭</button></div>
  </div>
</template>

<style scoped>
.chart-ctrls { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; font-size: 12px; color: var(--text2); }
.chart-ctrls select { margin-left: 6px; padding: 3px 6px; border: 1px solid var(--border2, var(--border));
  border-radius: 5px; background: var(--panel, #fff); color: inherit; }
.chart-note { color: var(--warning-solid); font-size: 12px; }
.pie-legend { display: flex; flex-wrap: wrap; gap: 10px 18px; margin-top: 10px; font-size: 12px; color: var(--text2); }
.pie-leg-item { display: inline-flex; align-items: center; gap: 5px; }
.pie-leg-item i { width: 11px; height: 11px; border-radius: 3px; display: inline-block; }
</style>
