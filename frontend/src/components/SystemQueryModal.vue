<script setup lang="ts">
// 系统查询弹窗(仅 admin): 在程序内置 SQLite 上执行只读 SELECT
// 可查系统用户 / 权限 / 连接 / 审计 / 调度任务; 白名单只读, 服务端强制 SELECT
import { ref, onMounted } from 'vue'
import { sysQuery } from '@/api/account'

const emit = defineEmits<{ close: [] }>()
const sql = ref('')
const rows = ref<Record<string, unknown>[]>([])
const cols = ref<string[]>([])
const loading = ref(false)
const msg = ref('')
const msgErr = ref(false)

const SAMPLE = [
  { label: '用户列表', sql: 'SELECT username, role, status FROM users ORDER BY username' },
  { label: '连接权限', sql: 'SELECT username, conn_name, can_read, can_write FROM user_perms' },
  { label: '表级权限', sql: "SELECT username, conn_name, table_name, CASE is_deny WHEN 1 THEN '禁止' ELSE '允许' END AS scope FROM user_perm_tables" },
  { label: '连接配置', sql: 'SELECT name, db_type, server, port, database, uid, mode FROM connections' },
  { label: '审计(最近50)', sql: 'SELECT ts, username, ip, action, detail FROM audit_log ORDER BY id DESC LIMIT 50' },
  { label: '调度任务', sql: 'SELECT id, name, action, conn_name, interval_min, enabled FROM tasks' },
]

function showInfo(m: string, err = false) {
  msg.value = m; msgErr.value = err
  setTimeout(() => { if (msg.value === m) msg.value = '' }, 4000)
}

async function run() {
  if (!sql.value.trim()) { showInfo('请输入 SQL', true); return }
  loading.value = true; msg.value = ''
  try {
    const r = await sysQuery(sql.value)
    rows.value = r.rows || []
    cols.value = rows.value.length ? Object.keys(rows.value[0]) : []
    showInfo(`查询完成：${rows.value.length} 行`)
  } catch (e) { showInfo((e as Error).message, true); rows.value = []; cols.value = [] }
  loading.value = false
}

function fmt(v: unknown): string {
  if (v === null || v === undefined) return ''
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

onMounted(() => { sql.value = SAMPLE[0].sql; run() })
</script>

<template>
  <Teleport to="body">
    <div class="modal-mask" @click.self="emit('close')">
      <div class="modal-box" style="max-width:860px">
        <div class="modal-header">
          <h3>系统查询（内置 SQLite 只读）</h3>
          <button class="sm" @click="emit('close')">✕</button>
        </div>
        <div class="hint">对程序自身的 <code>dbmanager.db</code> 执行只读 SELECT，可查系统用户、连接权限、连接配置、审计日志、调度任务。仅管理员可用。</div>
        <div class="samples">
          <button v-for="s in SAMPLE" :key="s.label" class="sm" @click="sql = s.sql; run()">{{ s.label }}</button>
        </div>
        <textarea v-model="sql" rows="4" class="sql-input" spellcheck="false"
          placeholder="SELECT username, role, status FROM users" @keydown.ctrl.enter="run"></textarea>
        <div class="toolbar">
          <button class="sm primary" :disabled="loading" @click="run">{{ loading ? '执行中...' : '执行 (Ctrl+Enter)' }}</button>
        </div>
        <div v-if="msg" :class="msgErr ? 'err-msg' : 'ok-msg'" style="margin:6px 0">{{ msg }}</div>
        <div class="result-wrap">
          <table v-if="cols.length" class="res-table">
            <thead><tr><th v-for="c in cols" :key="c">{{ c }}</th></tr></thead>
            <tbody>
              <tr v-for="(r, i) in rows" :key="i">
                <td v-for="c in cols" :key="c" :title="fmt(r[c])">{{ fmt(r[c]) }}</td>
              </tr>
            </tbody>
          </table>
          <div v-else-if="!loading" class="empty">（空结果集）</div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 1001; padding: 16px; box-sizing: border-box; }
.modal-box { background: var(--panel); border-radius: 8px; padding: 20px; width: 96%; max-width: 860px; border: 1px solid var(--border); max-height: 88vh; overflow-y: auto; box-sizing: border-box; display: flex; flex-direction: column; }
.modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.modal-header h3 { margin: 0; color: var(--text); }
.hint { font-size: 12px; color: var(--text2); background: var(--panel3); border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; margin-bottom: 10px; }
.hint code { background: var(--panel2); padding: 1px 5px; border-radius: 3px; }
.samples { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
.sql-input { width: 100%; padding: 8px 10px; border: 1px solid var(--border2); border-radius: 6px; background: var(--panel3); color: var(--text); font-size: 13px; font-family: Consolas, Monaco, monospace; box-sizing: border-box; resize: vertical; }
.toolbar { display: flex; justify-content: flex-end; margin: 8px 0; }
.result-wrap { flex: 1; overflow: auto; border: 1px solid var(--border); border-radius: 6px; background: var(--panel3); }
.res-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.res-table th { position: sticky; top: 0; background: var(--panel2); color: var(--text2); text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--border); white-space: nowrap; font-weight: 500; }
.res-table td { padding: 5px 8px; border-bottom: 1px solid var(--border); color: var(--text); max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.empty { color: var(--text3); font-size: 13px; padding: 12px; }
button { padding: 5px 14px; border: 1px solid var(--border); border-radius: 4px; background: var(--panel2); color: var(--text); cursor: pointer; font-size: 13px; }
button.sm { padding: 3px 10px; font-size: 12px; }
button.primary { background: var(--primary); color: #fff; border-color: var(--primary); }
.err-msg { color: #e54d42; font-size: 13px; }
.ok-msg { color: #00b42a; font-size: 13px; }
</style>
