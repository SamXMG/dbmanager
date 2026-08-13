<script setup lang="ts">
// 新建表(轻量版): 复刻 tools.ts openNewTable。
// 弹窗由 GenericModal 在共享遮罩内渲染, 此处只渲染 .g-modal 卡片根。
import { ref } from 'vue'
import { useUIStore } from '@/stores/ui'
import { alterTable } from '@/api/schema'
import { errMsg } from '@/utils/err'

const ui = useUIStore()
const props = defineProps<{ db: string; s: string }>()

const name = ref('')

async function run() {
  const n = name.value.trim()
  if (!n) { ui.toast('请填写表名', true); return }
  try {
    await alterTable({ s: props.s, t: n, action: 'create_table', payload: {} })
    ui.closeModal()
    ui.toast('已创建表 ' + n)
  } catch (e) { ui.toast('创建失败: ' + errMsg(e), true) }
}
</script>

<template>
  <div class="g-modal">
    <h3>新建表 · {{ db }}{{ s ? '.' + s : '' }}</h3>
    <div class="field"><label>表名</label><input v-model="name" autofocus></div>
    <p style="color:var(--text3);font-size:12px">将创建空表; 字段设计请打开表后右键「设计表」</p>
    <div class="acts">
      <button @click="ui.closeModal()">取消</button>
      <button class="primary" @click="run">创建</button>
    </div>
  </div>
</template>
