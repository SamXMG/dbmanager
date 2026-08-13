<script setup lang="ts">
// 批量粘贴插入弹窗(取代旧版 Toolbar.pasteInsert 的 ui.showModal HTML 注入)。
// 粘贴 Excel/CSV 文本 -> parsePaste 解析 TSV/CSV -> 按列顺序映射 -> importData。
// 由 GenericModal 在共享遮罩内渲染, 本组件只渲染 .g-modal 卡片根。
import { ref } from 'vue'
import { useUIStore } from '@/stores/ui'
import { useGridStore } from '@/stores/grid'
import { confirmDanger } from '@/utils/confirm'
import { importData } from '@/api/schema'
import { errMsg } from '@/utils/err'
import type { Column } from '@/api/database'

const props = defineProps<{
  s: string
  t: string
  columns: Column[]
}>()

const ui = useUIStore()
const grid = useGridStore()

const raw = ref('')
const busy = ref(false)

/** 解析粘贴文本: TSV / CSV(引号包裹的逗号值), 对齐旧 Toolbar.parsePaste */
function parsePaste(text: string): string[][] {
  const lines = text.replace(/\r\n/g, '\n').split('\n').filter(l => l.trim() !== '')
  if (!lines.length) return []
  const isTsv = lines[0].includes('\t')
  return lines.map(l => {
    if (isTsv) return l.split('\t')
    const out: string[] = []
    let cur = ''
    let inQ = false
    for (let i = 0; i < l.length; i++) {
      const ch = l[i]
      if (inQ) {
        if (ch === '"' && l[i + 1] === '"') { cur += '"'; i++ }
        else if (ch === '"') inQ = false
        else cur += ch
      } else if (ch === '"') inQ = true
      else if (ch === ',') { out.push(cur); cur = '' }
      else cur += ch
    }
    out.push(cur)
    return out
  })
}

async function onImport() {
  if (!raw.value.trim()) { ui.toast('请先粘贴数据', true); return }
  const rows = parsePaste(raw.value)
  if (!rows.length) { ui.toast('未解析到数据', true); return }
  const cols = props.columns.map(c => c.name)
  const mapped = rows.map(r => {
    const o: Record<string, unknown> = {}
    cols.forEach((c, i) => { if (r[i] !== undefined && r[i] !== '') o[c] = r[i] })
    return o
  })
  if (!await confirmDanger(`确认插入 ${mapped.length} 行到 ${props.s}.${props.t}？`)) return
  busy.value = true
  try {
    const payload: Record<string, unknown> = { s: props.s, t: props.t, columns: cols, rows: mapped }
    if (ui.transactionMode) payload.transaction = true
    const d = await importData(payload) as { affected?: number }
    ui.closeModal()
    ui.toast('已导入 ' + (d.affected ?? mapped.length) + ' 行')
    grid.loadData(1)
  } catch (e) {
    ui.toast('导入失败: ' + errMsg(e), true)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="g-modal">
    <h3>批量粘贴插入 · {{ s }}.{{ t }}</h3>
    <p style="color:var(--text3);font-size:12px;margin:4px 0 8px">
      从 Excel/表格复制数据后粘贴到下方(第一行为列名, 或直接数据), 按列顺序映射
    </p>
    <textarea v-model="raw" class="pi-area"
      placeholder="粘贴 Excel 复制的单元格..."></textarea>

    <div class="acts">
      <button type="button" @click="ui.closeModal()">取消</button>
      <button class="primary" type="button" :disabled="busy" @click="onImport">
        导入 {{ columns.length }} 列
      </button>
    </div>
  </div>
</template>

<style scoped>
.pi-area {
  width: 100%; height: 160px; box-sizing: border-box; padding: 8px;
  font-family: Consolas, monospace; font-size: 12px; resize: vertical;
  border: 1px solid var(--border); border-radius: 6px;
  background: var(--panel, #fff); color: var(--text);
}
</style>
