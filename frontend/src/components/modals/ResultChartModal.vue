<script setup lang="ts">
// 结果集图表(取代旧版 SqlWorkbench 无图表能力)。
// 读取 sqlStore.activeTab 当前结果: 选数值列作 Y、文本列作 X 轴, 渲染 SVG 柱状图(纯模板, 无注入)。
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

const valRef = ref('')
const catRef = ref('')

// 超过该数量柱体时截断(保证可读), 并提示
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
      <div class="chart-ctrls">
        <label>数值列(Y)
          <select v-model="valRef">
            <option v-for="c in numericCols" :key="c.name" :value="c.name">{{ c.name }}</option>
          </select>
        </label>
        <label>X 轴
          <select v-model="catRef">
            <option value="">行号</option>
            <option v-for="c in catCols" :key="c.name" :value="c.name">{{ c.name }}</option>
          </select>
        </label>
        <span v-if="points.length >= MAX_BARS" class="chart-note">仅显示前 {{ MAX_BARS }} 行</span>
      </div>

      <div v-if="!numericCols.length" class="empty2" style="padding:16px">结果集无数值列, 无法绘图</div>
      <svg v-else :viewBox="`0 0 ${Wc} ${Hc}`"
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
    </template>

    <div class="acts"><button class="primary" type="button" @click="ui.closeModal()">关闭</button></div>
  </div>
</template>

<style scoped>
.chart-ctrls { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; font-size: 12px; color: var(--text2); }
.chart-ctrls select { margin-left: 6px; padding: 3px 6px; border: 1px solid var(--border2, var(--border));
  border-radius: 5px; background: var(--panel, #fff); color: inherit; }
.chart-note { color: var(--warning-solid); font-size: 12px; }
</style>
