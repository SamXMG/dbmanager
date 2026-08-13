<script setup lang="ts">
// 新增行弹窗(取代旧版 Toolbar.addRow 的 ui.showModal HTML 注入)。
// 收集列值, 非空才入 values, 走 grid.insert。
// 由 GenericModal 在共享遮罩内渲染, 本组件只渲染 .g-modal 卡片根。
import { reactive } from 'vue'
import { useUIStore } from '@/stores/ui'
import { useGridStore } from '@/stores/grid'
import type { Column } from '@/api/database'

const props = defineProps<{
  s: string
  t: string
  columns: Column[]
}>()

const ui = useUIStore()
const grid = useGridStore()

const vals = reactive<Record<string, string>>({})
for (const c of props.columns) vals[c.name] = ''

async function onAdd() {
  const values: Record<string, unknown> = {}
  for (const c of props.columns) {
    const v = vals[c.name]
    if (v !== '') values[c.name] = v
  }
  try {
    const ok = await grid.insert(values)
    ui.closeModal()
    ui.toast(ok ? '已插入' : '插入失败', !ok)
  } catch {
    ui.toast('插入失败', true)
  }
}
</script>

<template>
  <div class="g-modal">
    <h3>新增行 · {{ s }}.{{ t }}</h3>

    <div class="add-body">
      <div v-for="c in columns" :key="c.name" class="row2" style="margin-bottom:6px;align-items:center">
        <label :title="c.name" style="width:120px;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
          {{ c.name }}<span v-if="c.is_pk" style="color:var(--text3)"> *</span>
        </label>
        <input v-model="vals[c.name]" :placeholder="c.type || ''" style="flex:1" />
      </div>
      <div v-if="!columns.length" class="empty2">无列信息</div>
    </div>

    <div class="acts">
      <button type="button" @click="ui.closeModal()">取消</button>
      <button class="primary" type="button" @click="onAdd">插入</button>
    </div>
  </div>
</template>

<style scoped>
.add-body { max-height: 60vh; overflow: auto; padding-right: 4px; }
</style>
