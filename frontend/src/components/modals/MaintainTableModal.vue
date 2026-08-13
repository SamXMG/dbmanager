<script setup lang="ts">
// 维护表(CHECK/OPTIMIZE/ANALYZE/REPAIR): 复刻 tools.ts openMaintainTable。
// 弹窗由 GenericModal 在共享遮罩内渲染, 此处只渲染 .g-modal 卡片根。
// 注意: 执行后不关闭弹窗, 结果保留在滚动区, 另有关闭按钮。
import { ref } from 'vue'
import { useUIStore } from '@/stores/ui'
import { alterTable } from '@/api/schema'
import { errMsg } from '@/utils/err'

const ui = useUIStore()
const props = defineProps<{ s: string; t: string }>()

interface MaintainResult { ok?: boolean; rows?: Record<string, unknown>[] }

const op = ref<'check' | 'optimize' | 'analyze' | 'repair'>('check')
const result = ref('')
const done = ref(false)

async function run() {
  try {
    const d = await alterTable({ s: props.s, t: props.t, action: 'maintain', payload: { op: op.value } }) as unknown as MaintainResult
    const rows = d.rows || []
    result.value = rows.length
      ? JSON.stringify(rows, null, 2)
      : '操作完成(无返回行, 多数 DDL 维护操作无输出)'
    done.value = true
    ui.toast('维护完成')
  } catch (e) { ui.toast('维护失败: ' + errMsg(e), true) }
}
</script>

<template>
  <div class="g-modal">
    <h3>维护表 · {{ s ? s + '.' : '' }}{{ t }}</h3>
    <div class="field"><label>维护操作</label>
      <select v-model="op">
        <option value="check">检查完整性 (CHECK / PRAGMA integrity_check)</option>
        <option value="optimize">优化 (OPTIMIZE / VACUUM)</option>
        <option value="analyze">更新统计 (ANALYZE)</option>
        <option value="repair">修复 (REPAIR / VACUUM FULL)</option>
      </select>
    </div>
    <p style="color:var(--text3);font-size:12px">不同数据库支持的操作不同(根据方言自动映射)</p>
    <pre v-if="done"
         style="max-height:240px;overflow:auto;border:1px solid #eee;border-radius:6px;padding:6px;font-size:12px;white-space:pre-wrap;margin-top:8px">{{ result }}</pre>
    <div class="acts">
      <button @click="ui.closeModal()">关闭</button>
      <button class="primary" @click="run">执行</button>
    </div>
  </div>
</template>
