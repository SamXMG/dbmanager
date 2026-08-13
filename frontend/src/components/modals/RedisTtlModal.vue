<script setup lang="ts">
// Redis 键 TTL 弹窗(取代旧版 Toolbar.redisTtl 的 ui.showModal HTML 注入)。
// 挂载时 alterTable({ action: 'set_ttl' }) 取当前过期时间; 应用走同一 action 写入新 ttl。
// 由 GenericModal 在共享遮罩内渲染, 本组件只渲染 .g-modal 卡片根。
import { onMounted, ref } from 'vue'
import { useUIStore } from '@/stores/ui'
import { alterTable } from '@/api/schema'
import { errMsg } from '@/utils/err'

const props = defineProps<{
  s: string
  t: string
}>()

const ui = useUIStore()

const current = ref('(获取中…)')
const ttl = ref('')
const busy = ref(false)

onMounted(async () => {
  try {
    const d = await alterTable({ s: props.s, t: props.t, action: 'set_ttl', payload: {} }) as { ttl?: number }
    current.value = d.ttl != null && d.ttl > 0 ? d.ttl + ' 秒' : '永久(-1)'
  } catch {
    current.value = '(获取失败)'
  }
})

async function apply() {
  if (ttl.value === '') { ui.toast('请输入过期秒数(0=永久)', true); return }
  busy.value = true
  try {
    await alterTable({
      s: props.s,
      t: props.t,
      action: 'set_ttl',
      payload: { ttl: parseInt(ttl.value, 10) },
    })
    ui.closeModal()
    ui.toast('TTL 已更新')
  } catch (e) {
    ui.toast('设置失败: ' + errMsg(e), true)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="g-modal">
    <h3>键 {{ t }} 的 TTL</h3>

    <div class="field">
      <label>当前过期时间</label>
      <div style="color:var(--text2)">{{ current }}</div>
    </div>
    <div class="field">
      <label>新过期秒数(0=永久)</label>
      <input v-model="ttl" type="number" placeholder="如 3600" />
    </div>

    <div class="acts">
      <button type="button" @click="ui.closeModal()">取消</button>
      <button class="primary" type="button" :disabled="busy" @click="apply">应用</button>
    </div>
  </div>
</template>
