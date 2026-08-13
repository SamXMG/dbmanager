<script setup lang="ts">
// 复制表(可带数据 / 仅结构): 复刻 tools.ts openCopyTable。
// 弹窗由 GenericModal 在共享遮罩内渲染, 此处只渲染 .g-modal 卡片根。
import { ref } from 'vue'
import { useUIStore } from '@/stores/ui'
import { alterTable } from '@/api/schema'
import { errMsg } from '@/utils/err'

const ui = useUIStore()
const props = defineProps<{ s: string; t: string }>()

const newName = ref(props.t + '_copy')
const mode = ref<'with' | 'only'>('with')

interface CopyResult { ok?: boolean; new_table?: string }

async function run() {
  const name = newName.value.trim()
  if (!name || name === props.t) { ui.toast('请输入不同的新表名', true); return }
  const with_data = mode.value === 'with'
  try {
    const d = await alterTable({ s: props.s, t: props.t, action: 'copy_table', payload: { new_name: name, with_data } }) as unknown as CopyResult
    ui.closeModal()
    const tbl = d.new_table || name
    ui.toast('已复制 → ' + tbl + (with_data ? '(含数据)' : '(仅结构)'))
  } catch (e) { ui.toast('复制失败: ' + errMsg(e), true) }
}
</script>

<template>
  <div class="g-modal">
    <h3>复制表</h3>
    <div class="field"><label>原表</label><div>{{ s ? s + '.' : '' }}{{ t }}</div></div>
    <div class="field"><label>新表名</label><input v-model="newName" autofocus></div>
    <div class="field"><label>复制选项</label>
      <select v-model="mode">
        <option value="with">复制结构 + 数据</option>
        <option value="only">仅复制结构</option>
      </select>
    </div>
    <div class="acts">
      <button @click="ui.closeModal()">取消</button>
      <button class="primary" @click="run">复制</button>
    </div>
  </div>
</template>
