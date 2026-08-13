<script setup lang="ts">
// 测试数据生成器(取代旧版 tools.ts openGenData 的 ui.showModal HTML 注入)。
// 走 genData({ s, t, rows }); 危险操作 confirmDanger 二次确认。
// 由 GenericModal 在共享遮罩内渲染, 本组件只渲染 .g-modal 卡片根。
import { ref } from 'vue'
import { useUIStore } from '@/stores/ui'
import { genData } from '@/api/schema'
import { confirmDanger } from '@/utils/confirm'
import { errMsg } from '@/utils/err'

const props = defineProps<{ s: string; t: string }>()
const ui = useUIStore()

const rows = ref(100)
const busy = ref(false)

async function onGen() {
  const n = Math.max(1, Math.min(50000, Math.floor(rows.value) || 100))
  if (!(await confirmDanger(`确认生成 ${n} 行测试数据到 ${props.s}.${props.t}？`, '生成测试数据'))) return
  busy.value = true
  try {
    const d = await genData({ s: props.s, t: props.t, rows: n }) as { inserted?: number }
    ui.closeModal()
    ui.toast('已生成 ' + (d.inserted ?? 0) + ' 行')
  } catch (e) {
    ui.toast('生成失败: ' + errMsg(e), true)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="g-modal">
    <h3>生成测试数据 · {{ s }}.{{ t }}</h3>
    <div class="field">
      <label>生成行数(上限 50000)</label>
      <input id="gdRows" type="number" v-model.number="rows" min="1" max="50000" />
    </div>
    <p style="color:var(--text3);font-size:12px">按列类型智能生成(自增主键/只读列跳过)</p>
    <div v-if="busy" class="empty2">生成中…</div>
    <div class="acts">
      <button type="button" @click="ui.closeModal()">取消</button>
      <button class="primary" type="button" :disabled="busy" @click="onGen">生成</button>
    </div>
  </div>
</template>
