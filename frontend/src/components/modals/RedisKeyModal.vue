<script setup lang="ts">
// 新建 Redis 键弹窗(取代旧版 Toolbar.redisNewKey 的 ui.showModal HTML 注入)。
// 走 alterTable({ action: 'create' })。
// 由 GenericModal 在共享遮罩内渲染, 本组件只渲染 .g-modal 卡片根。
import { ref } from 'vue'
import { useUIStore } from '@/stores/ui'
import { alterTable } from '@/api/schema'
import { errMsg } from '@/utils/err'

const props = defineProps<{
  s: string
  t: string
}>()

const ui = useUIStore()

const name = ref('')
const type = ref('string')
const value = ref('')
const ttl = ref('')
const busy = ref(false)

async function onCreate() {
  const key = name.value.trim()
  if (!key) { ui.toast('请填写键名', true); return }
  busy.value = true
  try {
    await alterTable({
      s: props.s,
      t: props.t,
      action: 'create',
      payload: {
        type: type.value,
        value: value.value,
        ttl: ttl.value ? parseInt(ttl.value, 10) : 0,
      },
    })
    ui.closeModal()
    ui.toast('已创建键 ' + key)
  } catch (e) {
    ui.toast('创建失败: ' + errMsg(e), true)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="g-modal">
    <h3>新建 Redis 键</h3>

    <div class="field">
      <label>键名</label>
      <input v-model="name" placeholder="如 user:1001" />
    </div>
    <div class="field">
      <label>类型</label>
      <select v-model="type">
        <option value="string">String</option>
        <option value="hash">Hash</option>
        <option value="list">List</option>
        <option value="set">Set</option>
        <option value="zset">ZSet</option>
      </select>
    </div>
    <div class="field">
      <label>初始值</label>
      <input v-model="value" placeholder="String 为值; Hash/List/Set 为单个元素; ZSet 为成员(score=0)" />
    </div>
    <div class="field">
      <label>过期秒数(留空=永久)</label>
      <input v-model="ttl" type="number" placeholder="如 3600" />
    </div>

    <div class="acts">
      <button type="button" @click="ui.closeModal()">取消</button>
      <button class="primary" type="button" :disabled="busy" @click="onCreate">创建</button>
    </div>
  </div>
</template>
