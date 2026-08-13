<script setup lang="ts">
// 查询构建器(升级为独立 Vue 组件):
// 取代旧版 tools.ts 中的 openQueryBuilder(动态 innerHTML + window.__qbAdd/__qbBuild 全局函数)。
// 修复点(对齐需求①~⑤):
//  ① 列选择: checkbox 勾选参与查询的列; 选中列在条件中被引用时高亮, 点击条件行高亮其引用列。
//  ② 事件绑定: 全部走 Vue 原生 @click/@change, 不再依赖 data-call/window 全局委托(旧版点击无响应的根源)。
//  ③ 对比度: 全程使用主题语义变量(--text/--text2/--panel/--border2 等), 浅色主题下文字清晰可读。
//  ④ 样式统一: .field/.row2 一致布局, 间距/边框统一, 去除硬编码浅色。
//  ⑤ 响应式: flex 自适应 + 窄屏媒体查询, 桌面/移动端均正常显示与交互; 含 Esc 关闭与焦点陷阱(a11y)。
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { useUIStore } from '@/stores/ui'
import { useConnectionStore } from '@/stores/connection'
import { useDatabaseStore } from '@/stores/database'
import { useSqlStore } from '@/stores/sql'
import { getColumns, type Column } from '@/api/database'
import { qident } from '@/utils/sqlIdent'

const ui = useUIStore()
const connStore = useConnectionStore()
const dbStore = useDatabaseStore()
const sqlStore = useSqlStore()

const open = computed(() => ui.queryBuilder)
const dbType = computed(() => connStore.conn?.db_type || 'mysql')
function q(name: string) { return qident(dbType.value, name) }

const tables = computed(() => dbStore.tables.filter(x => x.type !== 'View'))

const tableValue = ref('')
function splitTable(): { s: string; t: string } {
  const [s, t] = tableValue.value.split('\u0001')
  return { s: s || '', t: t || '' }
}

const columns = ref<Column[]>([])
const checked = ref<Record<string, boolean>>({})
const conditions = ref<{ col: string; op: string; val: string }[]>([])
const sortCol = ref('')
const sortDir = ref<'ASC' | 'DESC'>('ASC')
const limitN = ref(100)
const loading = ref(false)
const highlightedCol = ref('')   // 点击条件行时高亮的目标列(需求①)

const selectedColumns = computed(() =>
  columns.value.filter(c => checked.value[c.name]).map(c => c.name))

// 列是否被任一条件引用(用于常驻高亮标记)
function isReferenced(name: string) {
  return conditions.value.some(c => c.col === name)
}

async function loadCols() {
  const { s, t } = splitTable()
  if (!s || !t) return
  loading.value = true
  try {
    const cols = await getColumns(s, t)
    columns.value = cols
    const m: Record<string, boolean> = {}
    cols.forEach(c => { m[c.name] = true })
    checked.value = m
  } catch {
    columns.value = []
    ui.toast('加载列失败', true)
  } finally {
    loading.value = false
  }
}

function onTableChange(e: Event) {
  const v = (e.target as HTMLSelectElement).value
  if (v) tableValue.value = v
  conditions.value = []
  sortCol.value = ''
  highlightedCol.value = ''
  loadCols()
}

function addCondition() {
  const cols = selectedColumns.value
  if (!cols.length) { ui.toast('请先选择列', true); return }
  conditions.value.push({ col: cols[0], op: '=', val: '' })
}
function removeCondition(i: number) {
  const removed = conditions.value[i]?.col
  conditions.value.splice(i, 1)
  if (removed && !conditions.value.some(c => c.col === removed) && highlightedCol.value === removed) {
    highlightedCol.value = ''
  }
}
// 点击条件行 -> 高亮其引用列(需求①: 点击条件区域触发响应并高亮选中列)
function onCondRowClick(col: string) { highlightedCol.value = col }

function buildSql() {
  const { s, t } = splitTable()
  if (!s || !t) { ui.toast('请选择表', true); return }
  const cols = selectedColumns.value
  const colSql = cols.length ? cols.map(q).join(', ') : '*'
  let sql = 'SELECT ' + colSql + ' FROM ' + q(s) + '.' + q(t)
  const conds = conditions.value.map(c => {
    if (c.op === 'IS NULL') return q(c.col) + ' IS NULL'
    const v = c.val.trim()
    if (v === '') return null
    const val = (c.op === 'LIKE' || c.op === 'IN')
      ? v
      : (isNaN(Number(v)) ? "'" + v.replace(/'/g, "''") + "'" : v)
    return q(c.col) + ' ' + c.op + ' ' + val
  }).filter(Boolean) as string[]
  if (conds.length) sql += ' WHERE ' + conds.join(' AND ')
  if (sortCol.value) sql += ' ORDER BY ' + q(sortCol.value) + ' ' + sortDir.value
  if (limitN.value > 0) sql += ' LIMIT ' + limitN.value
  sqlStore.setSqlText(sql)
  ui.closeQueryBuilder()
  ui.switchView('sql')
  ui.toast('SQL 已生成, 检查后按 Ctrl+Enter 执行')
}

// 打开时初始化(默认选第一张表)
watch(open, (v) => {
  if (v) {
    conditions.value = []
    sortCol.value = ''
    sortDir.value = 'ASC'
    limitN.value = 100
    highlightedCol.value = ''
    if (tables.value.length) {
      const f = tables.value[0]
      tableValue.value = (f.schema || '') + '\u0001' + f.name
      loadCols()
    } else {
      columns.value = []
    }
  }
})

// a11y: Esc 关闭 + 焦点陷阱(对齐 GenericModal)
function onKeydown(e: KeyboardEvent) {
  if (!open.value) return
  if (e.key === 'Escape') { ui.closeQueryBuilder(); return }
  if (e.key !== 'Tab') return
  const mask = document.querySelector('.qb-mask')
  if (!mask) return
  const f = [...mask.querySelectorAll<HTMLElement>(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')]
    .filter(el => !el.hasAttribute('disabled'))
  if (!f.length) return
  const first = f[0], last = f[f.length - 1]
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
}
watch(open, (v) => {
  if (v) document.addEventListener('keydown', onKeydown)
  else document.removeEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown))
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="qb-mask" role="dialog" aria-modal="true" aria-label="查询构建器"
         @click.self="ui.closeQueryBuilder()">
      <div class="qb-modal" tabindex="-1">
        <div class="qb-head">
          <h3>查询构建器</h3>
          <button class="sm" type="button" @click="ui.closeQueryBuilder()">关闭</button>
        </div>

        <div class="qb-body">
          <!-- 表 -->
          <div class="field">
            <label>表</label>
            <select v-model="tableValue" @change="onTableChange">
              <option v-for="t in tables" :key="(t.schema || '') + '\u0001' + t.name"
                      :value="(t.schema || '') + '\u0001' + t.name">
                {{ t.schema ? t.schema + '.' : '' }}{{ t.name }}
              </option>
            </select>
          </div>

          <!-- 列选择 -->
          <div class="field">
            <label>选择列（勾选参与查询）</label>
            <div class="qb-cols">
              <label v-for="c in columns" :key="c.name" class="qb-col"
                     :class="{ 'qb-col-hi': highlightedCol === c.name, 'qb-col-ref': isReferenced(c.name) }">
                <input type="checkbox" :value="c.name" v-model="checked[c.name]" />
                <span class="qb-col-name">{{ c.name }}</span>
                <span class="qb-col-type">{{ c.type || '' }}</span>
              </label>
              <div v-if="!columns.length" class="empty2">{{ loading ? '加载中...' : '无列' }}</div>
            </div>
          </div>

          <!-- 条件 -->
          <div class="qb-conds">
            <div class="qb-conds-head">
              <label>条件（WHERE，AND 连接）</label>
              <button class="sm primary" type="button" @click="addCondition">+ 条件</button>
            </div>
            <div v-for="(cond, i) in conditions" :key="i" class="qb-cond-row"
                 @click="onCondRowClick(cond.col)">
              <select v-model="cond.col" class="qb-c">
                <option v-for="c in columns" :key="c.name" :value="c.name">{{ c.name }}</option>
              </select>
              <select v-model="cond.op" class="qb-op">
                <option value="=">=</option>
                <option value="!=">!=</option>
                <option value=">">&gt;</option>
                <option value=">=">&gt;=</option>
                <option value="<">&lt;</option>
                <option value="<=">&lt;=</option>
                <option value="LIKE">LIKE</option>
                <option value="IN">IN</option>
                <option value="IS NULL">IS NULL</option>
              </select>
              <input v-if="cond.op !== 'IS NULL'" v-model="cond.val" class="qb-v"
                     placeholder="值（IS NULL 可空）" />
              <button class="sm danger" type="button" @click.stop="removeCondition(i)"
                      title="删除条件" aria-label="删除条件">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                     stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M18 6 6 18M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div v-if="!conditions.length" class="empty2">暂无条件，点击「+ 条件」添加</div>
          </div>

          <!-- 排序 -->
          <div class="row2">
            <div class="field">
              <label>排序字段</label>
              <select v-model="sortCol">
                <option value="">无</option>
                <option v-for="c in columns" :key="c.name" :value="c.name">{{ c.name }}</option>
              </select>
            </div>
            <div class="field">
              <label>方向</label>
              <select v-model="sortDir">
                <option value="ASC">升序</option>
                <option value="DESC">降序</option>
              </select>
            </div>
          </div>

          <!-- LIMIT -->
          <div class="field">
            <label>LIMIT</label>
            <input type="number" v-model.number="limitN" min="1" class="qb-limit" />
          </div>
        </div>

        <div class="qb-acts">
          <button class="sm" type="button" @click="ui.closeQueryBuilder()">取消</button>
          <button class="sm primary" type="button" @click="buildSql">生成 SQL</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.qb-mask {
  position: fixed; inset: 0; z-index: 9100;
  background: rgba(0, 0, 0, 0.45);
  display: flex; align-items: center; justify-content: center; padding: 16px;
}
.qb-modal {
  background: var(--panel); color: var(--text);
  border-radius: 10px; width: 680px; max-width: 94vw; max-height: 88vh;
  display: flex; flex-direction: column;
  padding: 16px 20px 18px; box-shadow: 0 8px 30px rgba(0, 0, 0, 0.2);
}
.qb-head { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.qb-head h3 { margin: 0; font-size: 15px; flex: 1; }
.qb-body {
  flex: 1; min-height: 0; overflow: auto;
  display: flex; flex-direction: column; gap: 12px; padding: 2px;
}
.field { display: flex; flex-direction: column; gap: 4px; }
.field label { font-size: 12px; color: var(--text2); }
.qb-modal select, .qb-modal input[type="number"], .qb-modal input:not([type]) {
  padding: 5px 8px; border: 1px solid var(--border2); border-radius: 5px;
  font-size: 13px; outline: none; background: var(--panel); color: var(--text); width: 100%;
}
.qb-modal select:focus, .qb-modal input:focus { border-color: var(--primary); }

/* 列选择 */
.qb-cols {
  max-height: 168px; overflow: auto; border: 1px solid var(--border);
  border-radius: 6px; padding: 4px; display: flex; flex-direction: column; gap: 2px;
  background: var(--panel2);
}
.qb-col {
  display: flex; align-items: center; gap: 8px; padding: 5px 8px;
  border-radius: 5px; cursor: pointer; font-size: 13px; border-left: 3px solid transparent;
  color: var(--text);
}
.qb-col:hover { background: var(--panel3); }
.qb-col-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text); }
.qb-col-type { color: var(--text3); font-size: 11px; flex-shrink: 0; }
/* 被条件引用的列: 常驻浅标识 */
.qb-col-ref { background: var(--primary-bg); }
/* 点击条件行后高亮的列: 强高亮 */
.qb-col-hi { background: var(--primary-bg); border-left-color: var(--primary); font-weight: 600; }

/* 条件 */
.qb-conds-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.qb-conds-head label { font-size: 12px; color: var(--text2); }
.qb-cond-row {
  display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
  padding: 6px; border: 1px solid var(--border); border-radius: 6px;
  margin-bottom: 6px; cursor: pointer; background: var(--panel2);
}
.qb-cond-row:hover { border-color: var(--border2); }
.qb-c { min-width: 110px; flex: 1 1 120px; }
.qb-op { width: 84px; flex: 0 0 auto; }
.qb-v { flex: 2 1 140px; min-width: 100px; }

/* 排序 / LIMIT 行 */
.row2 { display: flex; gap: 12px; }
.row2 .field { flex: 1; }
.qb-limit { max-width: 140px; }

/* 按钮(作用域限定, 不污染全局) */
.qb-modal button {
  font-size: 13px; padding: 5px 14px; border-radius: 5px; cursor: pointer;
  border: 1px solid var(--border2); background: var(--panel); color: var(--text);
}
.qb-modal button.sm { font-size: 12px; padding: 4px 12px; }
.qb-modal button.primary { background: var(--primary); border-color: var(--primary); color: #fff; }
.qb-modal button.primary:hover { filter: brightness(1.06); }
.qb-modal button.danger {
  flex: 0 0 auto; display: inline-flex; align-items: center; justify-content: center;
  background: var(--danger-bg); color: var(--danger-solid); border-color: var(--danger-bg);
}

/* 底部操作 */
.qb-acts {
  display: flex; gap: 10px; justify-content: flex-end; margin-top: 14px;
  padding-top: 12px; border-top: 1px solid var(--border);
}
.empty2 { color: var(--text3); font-size: 12px; padding: 6px 0; }

/* 响应式: 窄屏堆叠, 保证移动端可用(需求⑤) */
@media (max-width: 560px) {
  .qb-modal { padding: 14px; }
  .qb-cond-row { gap: 6px; }
  .qb-c { flex-basis: 100%; }
  .qb-v { flex-basis: 100%; }
  .row2 { flex-direction: column; gap: 10px; }
  .qb-acts { flex-direction: column-reverse; }
  .qb-acts button { width: 100%; }
}
</style>
