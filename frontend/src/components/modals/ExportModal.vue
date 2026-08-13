<script setup lang="ts">
// 数据导出弹窗(功能深度①): 格式选择(CSV/JSON/XML/SQL-INSERT/XLSX) + WHERE 过滤 + 下载。
// 由 GenericModal 在共享遮罩内渲染, 本组件只渲染 .g-modal 卡片根, 不自带 Teleport/遮罩。
// 后端 export_data 已支持各 fmt; WHERE 透传当前网格筛选(可清空改为全表)。
import { ref } from 'vue'
import { useUIStore } from '@/stores/ui'
import { API_BASE, authHeaders } from '@/api/client'
import { useGridStore } from '@/stores/grid'

const props = defineProps<{ s: string; t: string }>()
const ui = useUIStore()
const grid = useGridStore()

const FORMATS = [
  { v: 'csv', label: 'CSV (Excel 兼容)', ext: 'csv', mime: 'text/csv' },
  { v: 'json', label: 'JSON (行数组)', ext: 'json', mime: 'application/json' },
  { v: 'xml', label: 'XML (行式)', ext: 'xml', mime: 'application/xml' },
  { v: 'sql', label: 'SQL-INSERT (可回放)', ext: 'sql', mime: 'application/sql' },
  { v: 'xlsx', label: 'Excel XLSX', ext: 'xlsx', mime: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' },
]
const fmt = ref('csv')
// 默认继承当前网格筛选; 提供"是否带筛选"开关与 where 输入(只读展示, 可清空)
const useFilter = ref(true)
const wherePreview = ref('')

function refreshPreview() {
  const w = grid.buildWhere()
  wherePreview.value = w
}
function toggleFilter(v: boolean) {
  useFilter.value = v
  if (v) refreshPreview()
  else wherePreview.value = ''
}

async function doExport() {
  const where = useFilter.value ? grid.buildWhere() : ''
  const f = FORMATS.find(x => x.v === fmt.value) || FORMATS[0]
  const params = new URLSearchParams({
    s: props.s, t: props.t, fmt: f.v,
    ...(where ? { where } : {}),
  })
  // 带鉴权头下载(会话/手动连接), 与 sql.ts exportSqlXlsx 同模式
  const headers: Record<string, string> = { ...(await authHeaders()) }
  const r = await fetch(API_BASE + '/api/export?' + params.toString(), { headers })
  if (!r.ok) {
    const d = (await r.json().catch(() => ({}))) as { error?: string }
    ui.toast(d.error || '导出失败(' + r.status + ')', true)
    return
  }
  const blob = await r.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = props.t + '.' + f.ext
  document.body.appendChild(a); a.click(); a.remove()
  URL.revokeObjectURL(a.href)
  ui.toast('已导出 ' + props.t + '.' + f.ext)
  ui.closeModal()
}
</script>

<template>
  <div class="g-modal">
    <h3 style="margin:0 0 14px">导出数据</h3>
    <div class="exp-field">
      <label style="display:block;margin-bottom:6px;font-size:13px">表：{{ s }}.{{ t }}</label>
      <label style="display:block;margin-bottom:6px;font-size:13px">格式</label>
      <select v-model="fmt" class="exp-sel" style="width:100%;padding:6px 8px;border:1px solid var(--border2);border-radius:6px;background:var(--panel);color:var(--text)">
        <option v-for="f in FORMATS" :key="f.v" :value="f.v">{{ f.label }}</option>
      </select>
    </div>
    <div style="margin-top:12px">
      <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer">
        <input type="checkbox" :checked="useFilter" @change="toggleFilter(($event.target as HTMLInputElement).checked)">
        带当前筛选条件 (WHERE)
      </label>
      <div v-if="useFilter" class="exp-where" style="margin-top:6px;padding:8px;background:var(--panel2);border:1px solid var(--border);border-radius:6px;font-family:var(--font-mono, monospace);font-size:12px;color:var(--text2);word-break:break-all">
        {{ wherePreview || '（无筛选条件，将导出全表）' }}
      </div>
      <div style="margin-top:6px;font-size:12px;color:var(--text3)">上限 {{ 5000 }} 行（EXPORT_LIMIT），如需全量请用 SQL 工作台分段导出</div>
    </div>
    <div class="acts" style="display:flex;justify-content:flex-end;gap:8px;margin-top:18px">
      <button class="sm" type="button" @click="ui.closeModal()">取消</button>
      <button class="sm primary" type="button" @click="doExport">导出下载</button>
    </div>
  </div>
</template>

<style scoped>
.exp-field select:focus { outline: none; border-color: var(--primary); }
</style>
