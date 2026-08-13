<script setup lang="ts">
// 编辑行弹窗(取代旧版 DataGrid openEditRow 的 ui.showModal HTML 注入)。
// 预填当前行各列值, 提交整行 PUT(走 grid.updateRowValues)。
// 由 GenericModal 在共享遮罩内渲染, 本组件只渲染 .g-modal 卡片根。
import { reactive } from 'vue'
import { useUIStore } from '@/stores/ui'
import { useGridStore } from '@/stores/grid'
import { errMsg } from '@/utils/err'
import type { Column } from '@/api/database'

const props = defineProps<{
  s: string
  t: string
  row: Record<string, unknown>
  columns: Column[]
  i: number
}>()

const ui = useUIStore()
const grid = useGridStore()

/** 单元格值 -> 输入框文本(对齐 DataGrid.fmt) */
function fmt(v: unknown): string {
  if (v === null || v === undefined) return ''
  if (v instanceof Date) return v.toISOString().slice(0, 19).replace('T', ' ')
  if (typeof v === 'object') {
    try { return JSON.stringify(v) } catch { return String(v) }
  }
  return String(v)
}

/** PK / 自增列只读, 禁用编辑 */
function readonly(c: Column): boolean {
  return !!(c.is_pk || c.identity)
}

// 预填: 每列一个文本值
const vals = reactive<Record<string, string>>({})
for (const c of props.columns) vals[c.name] = fmt(props.row[c.name])

async function onSave() {
  const values: Record<string, unknown> = {}
  for (const c of props.columns) {
    const v = vals[c.name]
    if (v === '' && c.nullable) values[c.name] = null
    else values[c.name] = v
  }
  try {
    const ok = await grid.updateRowValues(props.i, values)
    ui.closeModal()
    ui.toast(ok ? '已保存' : '保存失败', !ok)
  } catch (e) {
    ui.toast('保存失败: ' + errMsg(e), true)
  }
}
</script>

<template>
  <div class="g-modal">
    <h3>编辑行 · {{ s }}.{{ t }}</h3>

    <div class="edit-body">
      <div v-for="c in columns" :key="c.name" class="row2" style="margin-bottom:6px;align-items:center">
        <label :title="c.name" style="width:120px;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
          {{ c.name }}<span v-if="c.is_pk" style="color:var(--text3)"> *</span>
        </label>
        <input v-model="vals[c.name]" :placeholder="c.type || ''" :disabled="readonly(c)" style="flex:1" />
      </div>
      <div v-if="!columns.length" class="empty2">无列信息</div>
    </div>

    <div class="acts">
      <button type="button" @click="ui.closeModal()">取消</button>
      <button class="primary" type="button" @click="onSave">保存</button>
    </div>
  </div>
</template>

<style scoped>
.edit-body { max-height: 60vh; overflow: auto; padding-right: 4px; }
</style>
