<script setup lang="ts">
// EXPLAIN 执行计划可视化(取代旧版 SqlWorkbench 无弹窗/文本态展示)。
// 读取 sqlStore 中 explain:true 的结果 tab: 单列(如 PostgreSQL QUERY PLAN)按原缩进渲染为预格式化树,
// 多列(如 MySQL)渲染为表格; 均走通用弹窗渲染, 无注入。
// 由 GenericModal 在共享遮罩内渲染, 本组件只渲染 .g-modal 卡片根。
import { computed } from 'vue'
import { useUIStore } from '@/stores/ui'
import { useSqlStore } from '@/stores/sql'

const props = defineProps<{ tabId: number }>()
const ui = useUIStore()
const sqlStore = useSqlStore()

const tab = computed(() => sqlStore.tabs.find(t => t.id === props.tabId) || null)
const cols = computed(() => tab.value?.columns || [])
const rows = computed(() => tab.value?.rows || [])

// 单列计划(PostgreSQL / SQLite 的 QUERY PLAN)按原缩进显示; 多列(Mysql)走表格
const singleCol = computed(() => cols.value.length === 1)
const colName = computed(() => cols.value[0]?.name || '')
const planText = computed(() =>
  (rows.value || []).map(r => String(r[colName.value] ?? '')).join('\n'))

function cell(v: unknown): string {
  if (v === null || v === undefined) return ''
  return String(v)
}
</script>

<template>
  <div class="g-modal" style="width:780px;max-width:94vw">
    <h3>执行计划 EXPLAIN</h3>
    <div v-if="tab" class="explain-sql">{{ tab.sql }}</div>

    <div v-if="!tab" class="empty2" style="padding:20px">未找到该执行计划结果</div>
    <div v-else-if="tab.error" class="sql-error">{{ tab.error }}</div>
    <template v-else>
      <pre v-if="singleCol" class="plan-pre">{{ planText }}</pre>
      <table v-else-if="cols.length" class="explain-tbl">
        <thead><tr><th v-for="c in cols" :key="c.name">{{ c.name }}</th></tr></thead>
        <tbody>
          <tr v-for="(r, i) in rows" :key="i">
            <td v-for="c in cols" :key="c.name" :title="cell(r[c.name])">{{ cell(r[c.name]) }}</td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty2">该语句无结果集(可能为非 SELECT)</div>
    </template>

    <div class="acts"><button class="primary" type="button" @click="ui.closeModal()">关闭</button></div>
  </div>
</template>

<style scoped>
.explain-sql { font-family: Consolas, monospace; font-size: 12px; color: var(--text2);
  background: var(--panel2); border: 1px solid var(--border); border-radius: 6px;
  padding: 8px; margin-bottom: 10px; white-space: pre-wrap; word-break: break-all; }
.plan-pre { max-height: 60vh; overflow: auto; white-space: pre; font-family: Consolas, monospace;
  font-size: 12px; line-height: 1.5; background: var(--panel2); border: 1px solid var(--border);
  border-radius: 6px; padding: 10px; margin: 0; color: var(--text); }
.explain-tbl { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 4px;
  max-height: 60vh; overflow: auto; display: block; }
.explain-tbl th, .explain-tbl td { text-align: left; padding: 4px 8px; border-bottom: 1px solid var(--border);
  vertical-align: top; white-space: pre-wrap; word-break: break-all; }
.explain-tbl th { position: sticky; top: 0; background: var(--panel2); color: var(--text); }
.sql-error { color: var(--danger-solid); white-space: pre-wrap; }
</style>
