<script setup lang="ts">
// 列统计弹窗(取代旧版 Toolbar.showStats 的 ui.showModal HTML 注入)。
// 选列后调 statsColumn(带当前筛选 WHERE), 结果在同组件内以 <table class="p-tbl"> 展示(不再二次 openModal)。
// 由 GenericModal 在共享遮罩内渲染, 本组件只渲染 .g-modal 卡片根。
import { ref } from 'vue'
import { useUIStore } from '@/stores/ui'
import { useGridStore } from '@/stores/grid'
import { statsColumn } from '@/api/data'
import { errMsg } from '@/utils/err'
import type { Column } from '@/api/database'

const props = defineProps<{
  s: string
  t: string
  columns: Column[]
}>()

const ui = useUIStore()
const grid = useGridStore()

const col = ref(props.columns.length ? props.columns[0].name : '')
const loading = ref(false)
const result = ref<{ count: number; min?: unknown; max?: unknown; sum?: unknown; avg?: unknown } | null>(null)

/** 值 -> 展示文本 */
function fmtV(v: unknown): string {
  if (v === null || v === undefined) return '-'
  return String(v)
}

async function run() {
  if (!col.value) { ui.toast('请选择列', true); return }
  loading.value = true
  result.value = null
  try {
    const d = await statsColumn({ s: props.s, t: props.t, col: col.value, where: grid.buildWhere() })
    result.value = d
  } catch (e) {
    ui.toast('统计失败: ' + errMsg(e), true)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="g-modal">
    <h3>列统计 · {{ s }}.{{ t }}</h3>

    <div class="field">
      <label>列</label>
      <select v-model="col">
        <option v-for="c in columns" :key="c.name" :value="c.name">{{ c.name }}</option>
      </select>
    </div>

    <div class="acts">
      <button type="button" @click="ui.closeModal()">关闭</button>
      <button class="primary" type="button" :disabled="loading" @click="run">统计</button>
    </div>

    <div v-if="loading" class="empty2" style="margin-top:10px">统计中…</div>

    <table v-else-if="result" class="p-tbl" style="margin-top:10px">
      <tbody>
        <tr><td>COUNT</td><td>{{ result.count }}</td></tr>
        <tr><td>MIN</td><td>{{ fmtV(result.min) }}</td></tr>
        <tr><td>MAX</td><td>{{ fmtV(result.max) }}</td></tr>
        <tr v-if="'sum' in result"><td>SUM</td><td>{{ fmtV(result.sum) }}</td></tr>
        <tr v-if="'avg' in result"><td>AVG</td><td>{{ fmtV(result.avg) }}</td></tr>
      </tbody>
    </table>
  </div>
</template>
