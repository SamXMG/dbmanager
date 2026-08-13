<script setup lang="ts">
// 重命名表(支持 schema): 复刻 tools.ts openRenameTable。
// 弹窗由 GenericModal 在共享遮罩内渲染, 此处只渲染 .g-modal 卡片根。
import { ref } from 'vue'
import { useUIStore } from '@/stores/ui'
import { alterTable } from '@/api/schema'
import { errMsg } from '@/utils/err'

const ui = useUIStore()
const props = defineProps<{ s: string; t: string }>()

const newName = ref(props.t)

async function run() {
  const name = newName.value.trim()
  if (!name || name === props.t) { ui.toast('请输入不同的新表名', true); return }
  try {
    await alterTable({ s: props.s, t: props.t, action: 'rename_table', payload: { new_name: name } })
    ui.closeModal()
    ui.toast('已重命名: ' + props.t + ' → ' + name)
  } catch (e) { ui.toast('重命名失败: ' + errMsg(e), true) }
}
</script>

<template>
  <div class="g-modal">
    <h3>重命名表</h3>
    <div class="field"><label>原表名</label><div>{{ s ? s + '.' : '' }}{{ t }}</div></div>
    <div class="field"><label>新表名</label><input v-model="newName" autofocus></div>
    <div class="acts">
      <button @click="ui.closeModal()">取消</button>
      <button class="primary" @click="run">重命名</button>
    </div>
  </div>
</template>
