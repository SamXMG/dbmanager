<script setup lang="ts">
// 结构对比(跨连接): 复刻 tools.ts openSchemaDiff。
// 弹窗由 GenericModal 在共享遮罩内渲染, 此处只渲染 .g-modal 卡片根。
import { ref, onMounted } from 'vue'
import { useUIStore } from '@/stores/ui'
import { useConnectionStore } from '@/stores/connection'
import { listConnections, type ConnMeta } from '@/api/connection'
import { schemaDiff } from '@/api/schema'
import { errMsg } from '@/utils/err'

const ui = useUIStore()
const connStore = useConnectionStore()
const props = defineProps<{ s: string; t: string }>()

const conns = ref<ConnMeta[]>([])
const dstName = ref('')
const diff = ref<string[] | null>(null)

onMounted(async () => {
  try {
    conns.value = await listConnections()
    if (conns.value.length) dstName.value = conns.value[0].name || ''
  } catch { /* 未登录 / 无连接列表时静默, 下拉为空 */ }
})

interface DiffResult { diff?: string[] }

async function run() {
  const src = connStore.conn?.name ? { name: connStore.conn.name } : (connStore.conn || {})
  try {
    const d = await schemaDiff({ src, dst: { name: dstName.value }, schema: props.s, table: props.t }) as unknown as DiffResult
    diff.value = d.diff || []
  } catch (e) { ui.toast('对比失败: ' + errMsg(e), true) }
}
</script>

<template>
  <div class="g-modal">
    <h3>结构对比 · {{ s }}.{{ t }}</h3>
    <div class="field"><label>目标连接</label>
      <select v-model="dstName">
        <option v-for="c in conns" :key="c.name" :value="c.name">{{ c.name }} ({{ c.db_type }})</option>
      </select>
    </div>
    <div style="max-height:240px;overflow:auto;border:1px solid #eee;border-radius:6px;padding:8px;margin-top:8px;font-size:12px">
      <span v-if="diff === null" style="color:var(--text3)">对比结果将显示在这里</span>
      <template v-else-if="diff.length">
        <div v-for="(x, i) in diff" :key="i"
             style="padding:3px 0;border-bottom:1px solid #f5f6f8">{{ x }}</div>
      </template>
      <div v-else class="empty2">无差异(结构一致)</div>
    </div>
    <div class="acts">
      <button @click="ui.closeModal()">关闭</button>
      <button class="primary" @click="run">对比</button>
    </div>
  </div>
</template>
