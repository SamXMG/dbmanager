<script setup lang="ts">
// 表设计器(阶段5): 字段/索引/外键/触发器/SQL预览 5 tab + 同库表切换
// 对齐旧版 js/sql.js openAlter; 操作走 /api/alter, 完成后原地刷新(旧版是关掉重开, 这里更顺)
// 外键/触发器保守策略: 生成 DDL 填入 SQL 工作台由用户确认执行(对齐旧版)
import { computed, ref, watch } from 'vue'
import { useUIStore } from '@/stores/ui'
import { useAuthStore } from '@/stores/auth'
import { useConnectionStore } from '@/stores/connection'
import { useDatabaseStore } from '@/stores/database'
import { useSqlStore } from '@/stores/sql'
import { getColumns, getIndexes, getRelations, type Column } from '@/api/database'
import { alterTable } from '@/api/schema'
import type { RoutineInfo } from '@/api/database'

interface IndexInfo { name?: string; columns?: string; is_unique?: boolean; is_pk?: boolean }
interface RelationInfo {
  name?: string
  columns?: string[]
  referred_schema?: string
  referred_table?: string
  referred_columns?: string[]
  direction?: string
}

const ui = useUIStore()
const auth = useAuthStore()
const connStore = useConnectionStore()
const dbStore = useDatabaseStore()
const sqlStore = useSqlStore()

const tab = ref<'fields' | 'indexes' | 'fks' | 'trigs' | 'preview'>('fields')
const loading = ref(false)
const cols = ref<Column[]>([])
const idxs = ref<IndexInfo[]>([])
const rels = ref<RelationInfo[]>([])
const trigs = ref<RoutineInfo[]>([])

const target = computed(() => ui.designer)
const canWrite = computed(() => auth.canWrite)
const dbType = computed(() => connStore.conn?.db_type || 'mysql')
// SQLite 后端不支持可视化 DDL(alter_table 拒绝), 只读展示 + 提示改用 SQL 控制台
const isSqlite = computed(() => (dbType.value || '').toLowerCase() === 'sqlite')
const canEdit = computed(() => auth.canWrite && !isSqlite.value)

// 方言标识引用
function q(name: string): string {
  const t = dbType.value.toLowerCase()
  if (t === 'mssql') return '[' + name + ']'
  if (t === 'mysql' || t === 'mariadb' || t === 'oceanbase' || t === 'tidb') return '`' + name + '`'
  return '"' + name + '"'
}
function esc(s: unknown): string {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;')
}

// 同库表列表(对象切换下拉)
const dbTables = computed(() => {
  if (!target.value) return []
  const sc = target.value.s
  const names = dbStore.tables.filter(x => x.schema === sc).map(x => x.name)
  return [...new Set([target.value.t, ...names])]
})

// 打开/切换表 -> 加载
watch(() => ui.designer, (d) => { if (d) loadAll() })

async function loadAll() {
  const d = target.value
  if (!d) return
  loading.value = true
  try {
    cols.value = await getColumns(d.s, d.t)
    try { idxs.value = await getIndexes(d.s, d.t) } catch { idxs.value = [] }
    try {
      const r = await getRelations(d.s, d.t) as unknown as RelationInfo[]
      rels.value = (r || []).filter(x => x.direction === 'out')
    } catch { rels.value = [] }
    trigs.value = dbStore.routines.filter(r => r.type === 'Trigger' && (r.schema || '') === d.s)
  } catch (e) {
    ui.toast('加载表结构失败: ' + (e as Error).message, true)
  } finally {
    loading.value = false
  }
}

/** 表切换 */
async function switchTable(name: string) {
  if (!target.value || name === target.value.t) return
  ui.designer = { s: target.value.s, t: name }
}

// ---- 字段 ----
const newCol = ref({ name: '', type: '', default: '', nullable: true })
async function addColumn() {
  const d = target.value
  if (!d || !newCol.value.name.trim() || !newCol.value.type.trim()) { ui.toast('请填写列名与类型', true); return }
  await doAlter('add_column', {
    name: newCol.value.name.trim(), type: newCol.value.type.trim(),
    nullable: newCol.value.nullable, default: newCol.value.default.trim(),
  })
  if (d) newCol.value = { name: '', type: '', default: '', nullable: true }
}
async function modifyColumn(name: string) {
  const col = cols.value.find(c => c.name === name)
  const nt = window.prompt('输入新类型(如 NVARCHAR(100)):', col?.type || '')
  if (!nt) return
  const nullable = window.confirm('保持可空? 确定=可空, 取消=NOT NULL')
  await doAlter('modify_column', { name, type: nt.trim(), nullable })
}
async function dropColumn(name: string) {
  if (!window.confirm('确认删除字段 ' + name + '? 该操作不可逆!')) return
  await doAlter('drop_column', { name })
}

// ---- 索引 ----
const newIdx = ref({ name: '', columns: '', unique: false })
async function addIndex() {
  const d = target.value
  const cs = newIdx.value.columns.split(',').map(x => x.trim()).filter(Boolean)
  if (!d || !cs.length) { ui.toast('请填写索引列', true); return }
  await doAlter('add_index', { name: newIdx.value.name.trim(), columns: cs, unique: newIdx.value.unique })
  if (d) newIdx.value = { name: '', columns: '', unique: false }
}
async function dropIndex(name: string) {
  if (!window.confirm('确认删除索引 ' + name + '?')) return
  await doAlter('drop_index', { name })
}

/** 调 /api/alter 并原地刷新(旧版 alter: DDL 后清元数据 + 重开设计器) */
async function doAlter(action: string, payload: Record<string, unknown>) {
  const d = target.value
  if (!d) return
  try {
    const r = await alterTable({ s: d.s, t: d.t, action, payload })
    ui.toast('DDL 已执行: ' + (r.ddl || []).join('; ').slice(0, 90))
    // 清 tab store 元数据缓存(结构变了)
    const { useTabStore } = await import('@/stores/tab')
    const ts = useTabStore()
    const at = ts.activeTab
    if (at) at.meta = null
    await loadAll()
  } catch (e) {
    ui.toast('DDL 失败: ' + (e as Error).message, true)
  }
}

// ---- 外键: 保守策略, 生成 ALTER TABLE 填入 SQL 工作台 ----
function toSqlEditor(sql: string) {
  sqlStore.setSqlText(sql)
  ui.switchView('sql')
  ui.toast('SQL 已生成, 检查后按 Ctrl+Enter 执行')
}
const fkForm = ref({ refTable: '', col: '', refCol: '', name: '' })
function addForeignKey() {
  const d = target.value
  if (!d) return
  const { refTable, col, refCol, name } = fkForm.value
  if (!col.trim() || !refTable.trim() || !refCol.trim()) { ui.toast('请填写本表列/引用表/引用列', true); return }
  const refParts = refTable.trim().split('.').map(x => q(x.trim())).join('.')
  const sql = 'ALTER TABLE ' + q(d.s) + '.' + q(d.t) + ' ADD CONSTRAINT ' + (name.trim() ? q(name.trim()) : '') +
    ' FOREIGN KEY (' + q(col.trim()) + ') REFERENCES ' + refParts + ' (' + q(refCol.trim()) + ');'
  toSqlEditor(sql)
}
function dropFk(name: string) {
  const d = target.value
  if (!d) return
  if (!window.confirm('确认删除外键 ' + name + '?')) return
  toSqlEditor('ALTER TABLE ' + q(d.s) + '.' + q(d.t) + ' DROP CONSTRAINT ' + q(name) + ';')
}

// ---- SQL 预览(renderDgPreview 翻译) ----
const previewSql = computed(() => {
  const d = target.value
  if (!d) return ''
  const lines: string[] = []
  lines.push('CREATE TABLE ' + q(d.s) + '.' + q(d.t) + ' (')
  const trailing: string[] = []
  cols.value.forEach((c, i) => {
    let ln = '  ' + q(c.name) + ' ' + (c.type || '')
    if (!c.nullable) ln += ' NOT NULL'
    if (c.default != null && c.default !== '') ln += ' DEFAULT ' + c.default
    lines.push(ln + ',')
  })
  ;(idxs.value || []).forEach(i => {
    const cs = (i.columns || '').split(',').map(x => q(x.trim())).join(', ')
    if (i.is_pk) { trailing.push('  PRIMARY KEY (' + cs + ')'); return }
    lines.push('  ' + (i.is_unique ? 'UNIQUE ' : '') + 'INDEX ' + q(i.name || 'idx') + ' (' + cs + '),')
  })
  ;(rels.value || []).forEach(r => {
    trailing.push('  CONSTRAINT ' + q(r.name || 'fk') + ' FOREIGN KEY (' + (r.columns || []).map(q).join(', ') + ') REFERENCES ' +
      q(r.referred_schema || d.s) + '.' + q(r.referred_table || '') + ' (' + (r.referred_columns || []).map(q).join(', ') + ')')
  })
  if (trailing.length) {
    lines[lines.length - 1] = lines[lines.length - 1].replace(/,$/, '')
    trailing.forEach((t, i) => lines.push(t + (i < trailing.length - 1 ? ',' : '')))
  } else {
    lines[lines.length - 1] = lines[lines.length - 1].replace(/,$/, '')
  }
  lines.push(');')
  return lines.join('\n')
})
</script>

<template>
  <Teleport to="body">
    <div v-if="ui.designer" class="td-mask" @click.self="ui.closeDesigner()">
      <div class="td-modal">
        <!-- 头部: 标题 + 表切换 + 完成 -->
        <div class="td-head">
          <h3>表设计器 · {{ target?.s }}.{{ target?.t }}</h3>
          <div class="td-switch">
            <label>表:</label>
            <select :value="target?.t" @change="switchTable(($event.target as HTMLSelectElement).value)">
              <option v-for="n in dbTables" :key="n" :value="n">{{ n }}</option>
            </select>
          </div>
          <button class="primary sm" @click="ui.closeDesigner()">完成</button>
        </div>

        <!-- tabs -->
        <div class="td-tabs">
          <div v-for="tb in (['fields', 'indexes', 'fks', 'trigs', 'preview'] as const)" :key="tb"
               class="td-tab" :class="{ active: tab === tb }" @click="tab = tb">
            {{ { fields: '字段', indexes: '索引', fks: '外键', trigs: '触发器', preview: 'SQL 预览' }[tb] }}
          </div>
        </div>
        <div v-if="isSqlite" class="td-warn">⚠ SQLite 不支持可视化 DDL 编辑, 当前为只读展示; 请用 SQL 控制台执行 ALTER TABLE</div>

        <div v-if="loading" class="empty2" style="padding:20px;text-align:center">加载中...</div>

        <!-- 字段 -->
        <div v-else-if="tab === 'fields'" class="td-body">
          <div class="td-list">
            <div v-for="c in cols" :key="c.name" class="td-row">
              <span class="td-main"><b>{{ c.name }}</b>
                <span class="td-sub">{{ c.type }}{{ c.nullable ? ' NULL' : ' NOT NULL' }}{{ c.is_pk ? ' · 主键' : '' }}</span>
              </span>
              <template v-if="canEdit">
                <button class="sm" @click="modifyColumn(c.name)">改</button>
                <button class="sm danger" @click="dropColumn(c.name)">删</button>
              </template>
            </div>
            <div v-if="!cols.length" class="empty2">无字段</div>
          </div>
          <h4 class="td-h4" v-if="canEdit">添加字段</h4>
          <div v-if="canEdit" class="td-form">
            <div class="row2">
              <div class="field"><label>列名</label><input v-model="newCol.name" placeholder="如 remark" /></div>
              <div class="field"><label>类型</label><input v-model="newCol.type" placeholder="如 NVARCHAR(50) / INT" /></div>
            </div>
            <div class="row2">
              <div class="field"><label>默认值(可空)</label><input v-model="newCol.default" placeholder="如 0 或 'x' 或 CURRENT_TIMESTAMP" /></div>
              <div class="field chk"><label><input type="checkbox" v-model="newCol.nullable" /> 可空</label></div>
            </div>
            <button class="sm primary" @click="addColumn">添加字段</button>
          </div>
        </div>

        <!-- 索引 -->
        <div v-else-if="tab === 'indexes'" class="td-body">
          <div class="td-list">
            <div v-for="i in idxs" :key="i.name || i.columns" class="td-row">
              <span class="td-main"><b>{{ i.name || '(未命名)' }}</b>
                <span class="td-sub">{{ i.columns }}{{ i.is_unique ? ' · 唯一' : '' }}{{ i.is_pk ? ' · 主键' : '' }}</span>
              </span>
              <button v-if="canEdit && !i.is_pk" class="sm danger" @click="dropIndex(i.name || '')">删</button>
            </div>
            <div v-if="!idxs.length" class="empty2">暂无索引</div>
          </div>
          <h4 class="td-h4" v-if="canEdit">添加索引</h4>
          <div v-if="canEdit" class="td-form">
            <div class="row2">
              <div class="field"><label>索引名</label><input v-model="newIdx.name" placeholder="如 idx_remark" /></div>
              <div class="field"><label>列(逗号分隔)</label><input v-model="newIdx.columns" placeholder="如 remark, status" /></div>
            </div>
            <div class="field chk"><label><input type="checkbox" v-model="newIdx.unique" /> 唯一索引</label></div>
            <button class="sm primary" @click="addIndex">添加索引</button>
          </div>
        </div>

        <!-- 外键 -->
        <div v-else-if="tab === 'fks'" class="td-body">
          <div class="td-list">
            <div v-for="r in rels" :key="r.name || r.columns?.join(',')" class="td-row">
              <span class="td-main"><b>{{ r.name || '(未命名)' }}</b>
                <span class="td-sub">{{ (r.columns || []).join(', ') }} → {{ r.referred_table }}({{ (r.referred_columns || []).join(', ') }})</span>
              </span>
              <button v-if="canEdit" class="sm danger" @click="dropFk(r.name || '')">删</button>
            </div>
            <div v-if="!rels.length" class="empty2">暂无外键</div>
          </div>
          <h4 class="td-h4" v-if="canEdit">添加外键(生成 SQL 到工作台)</h4>
          <div v-if="canEdit" class="td-form">
            <div class="field"><label>引用表(支持 库.schema.表 / schema.表 / 表)</label>
              <input v-model="fkForm.refTable" placeholder="如 Customer 或 dbo.Customer" /></div>
            <div class="row2">
              <div class="field"><label>本表列</label><input v-model="fkForm.col" placeholder="如 CustomerId" /></div>
              <div class="field"><label>引用列</label><input v-model="fkForm.refCol" placeholder="如 Id" /></div>
            </div>
            <div class="field"><label>约束名(可空, 自动命名)</label><input v-model="fkForm.name" :placeholder="'如 FK_' + (target?.t || '') + '_CustomerId'" /></div>
            <button class="sm primary" @click="addForeignKey">添加外键</button>
          </div>
        </div>

        <!-- 触发器 -->
        <div v-else-if="tab === 'trigs'" class="td-body">
          <div class="td-list">
            <div v-for="r in trigs" :key="r.name" class="td-row">
              <span class="td-main"><b>🔔 {{ r.name }}</b></span>
              <button class="sm" @click="sqlStore.newTrigger(target?.s || '', target?.t || '')">新建</button>
            </div>
            <div v-if="!trigs.length" class="empty2">该表暂无触发器</div>
          </div>
          <div style="margin-top:10px" v-if="canEdit">
            <button class="sm primary" @click="sqlStore.newTrigger(target?.s || '', target?.t || '')">新建触发器(生成模板到 SQL 台)</button>
          </div>
        </div>

        <!-- SQL 预览 -->
        <div v-else class="td-body">
          <pre class="td-preview">{{ previewSql }}</pre>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.td-mask {
  position: fixed; inset: 0; z-index: 9100;
  background: rgba(0, 0, 0, 0.45);
  display: flex; align-items: center; justify-content: center; padding: 16px;
}
.td-modal {
  background: var(--panel, #fff); border-radius: 10px;
  width: 720px; max-width: 94vw; max-height: 88vh;
  display: flex; flex-direction: column;
  padding: 16px 20px 20px; box-shadow: 0 8px 30px rgba(0, 0, 0, 0.2);
}
.td-head { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; margin-bottom: 10px; }
.td-head h3 { margin: 0; font-size: 15px; flex-shrink: 0; }
.td-switch { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text2, #86909c); }
.td-switch select { padding: 4px 8px; border: 1px solid var(--border2, #e5e6eb); border-radius: 5px; font-size: 13px; background: var(--panel, #fff); color: inherit; max-width: 220px; }
.td-head button { margin-left: auto; }
.td-tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--border, #e4e7ed); flex-shrink: 0; }
.td-tab { padding: 7px 16px; font-size: 13px; cursor: pointer; border-radius: 6px 6px 0 0; border: 1px solid transparent; border-bottom: none; color: var(--text2, #86909c); }
.td-tab:hover { background: rgba(128, 128, 128, 0.06); }
.td-tab.active { background: var(--panel, #fff); border-color: var(--border, #e4e7ed); color: var(--primary, #165dff); font-weight: 600; }
.td-warn { padding: 6px 10px; margin: 8px 0 0; font-size: 12px; color: #d4660a; background: #fff7e6; border: 1px solid #ffd591; border-radius: 6px; flex-shrink: 0; }
.td-body { flex: 1; min-height: 0; overflow: auto; padding: 10px 2px; }
.td-list { max-height: 200px; overflow: auto; border: 1px solid var(--border, #eee); border-radius: 6px; }
.td-row { display: flex; align-items: center; gap: 8px; padding: 5px 8px; border-bottom: 1px solid var(--border, #f5f6f8); }
.td-row:last-child { border-bottom: none; }
.td-main { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.td-sub { color: var(--text2, #86909c); font-size: 12px; margin-left: 6px; }
.td-h4 { margin: 10px 0 6px; font-size: 13px; }
.td-form { display: flex; flex-direction: column; gap: 8px; max-width: 560px; }
.td-form .row2 { display: flex; gap: 8px; }
.td-form .row2 .field { flex: 1; }
.field { display: flex; flex-direction: column; gap: 4px; }
.field label { font-size: 12px; color: var(--text2, #86909c); }
.field.chk { justify-content: center; }
.field input, .field select { padding: 5px 8px; border: 1px solid var(--border2, #e5e6eb); border-radius: 5px; font-size: 13px; outline: none; background: var(--panel, #fff); color: inherit; }
.empty2 { color: var(--text3, #999); font-size: 12px; padding: 8px; }
.td-preview { margin: 0; font-family: Consolas, monospace; font-size: 12px; color: var(--text, #1d2129); white-space: pre-wrap; background: var(--panel2, #f7f8fa); padding: 10px; border-radius: 6px; }
button.sm { padding: 4px 10px; font-size: 12px; }
button.sm.danger { background: #fcebeb; color: #a32d2d; border-color: #f7c1c1; }
</style>
