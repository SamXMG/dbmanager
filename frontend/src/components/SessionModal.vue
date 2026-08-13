<script setup lang="ts">
// 在线用户管理弹窗(仅 admin): 实时列表 + 一键踢下线(二次确认)
// 显示: 用户名/角色/登录时间/来源IP/最后活跃/当前操作/会话数; 每 5s 自动刷新
import { ref, onMounted, onUnmounted } from 'vue'
import Icon from '@/components/Icon.vue'
import { errMsg } from '@/utils/err'
import { confirmDanger } from '@/utils/confirm'
import { listSessions, kickSession, type SessionInfo } from '@/api/account'

const emit = defineEmits<{ close: [] }>()
const sessions = ref<SessionInfo[]>([])
const msg = ref('')
const msgErr = ref(false)
const kicking = ref('')

function showInfo(m: string, err = false) {
  msg.value = m; msgErr.value = err
  setTimeout(() => { if (msg.value === m) msg.value = '' }, 3000)
}

async function refresh() {
  try {
    const r = await listSessions()
    sessions.value = r.sessions || []
  } catch (e) { /* 弹窗关闭后轮询报错静默 */ }
}

function fmtTime(ts: number): string {
  if (!ts) return '-'
  const d = new Date(ts * 1000)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getMonth() + 1}-${d.getDate()} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

function relTime(ts: number): string {
  if (!ts) return '-'
  const s = Math.max(0, Math.floor(Date.now() / 1000 - ts))
  if (s < 60) return s + ' 秒前'
  if (s < 3600) return Math.floor(s / 60) + ' 分钟前'
  return Math.floor(s / 3600) + ' 小时前'
}

async function doKick(u: SessionInfo) {
  // 二次确认: 踢下线不可撤销
  if (!await confirmDanger(`确认将用户「${u.user}」强制下线？\n其当前所有会话（${u.sessions} 个）将被立即断开，重新登录前无法使用。`)) return
  kicking.value = u.user
  try {
    const r = await kickSession(u.user)
    showInfo(r.message || '已踢下线')
    refresh()
  } catch (e) { showInfo(errMsg(e), true) }
  kicking.value = ''
}

let timer: number | undefined
onMounted(() => { refresh(); timer = window.setInterval(refresh, 5000) })
onUnmounted(() => { if (timer) window.clearInterval(timer) })
</script>

<template>
  <Teleport to="body">
    <div class="modal-mask" @click.self="emit('close')">
      <div class="modal-box" style="max-width:720px">
        <div class="modal-header">
          <h3>在线用户（{{ sessions.length }}）</h3>
          <button class="sm" @click="emit('close')"><Icon name="x" :size="14" /></button>
        </div>
        <div v-if="msg" :class="msgErr ? 'err-msg' : 'ok-msg'" style="margin-bottom:8px">{{ msg }}</div>
        <div class="hint">每 5 秒自动刷新。踢下线立即断开该用户所有会话（不可撤销，需二次确认）。</div>

        <div v-if="sessions.length === 0" class="empty">当前无在线用户</div>
        <table v-else class="sess-table">
          <thead>
            <tr><th>用户</th><th>角色</th><th>登录时间</th><th>来源 IP</th><th>最后活跃</th><th>当前操作</th><th>会话</th><th></th></tr>
          </thead>
          <tbody>
            <tr v-for="s in sessions" :key="s.user">
              <td class="u">{{ s.user }}</td>
              <td><span class="role" :class="'r-' + s.role">{{ s.role === 'admin' ? '管理员' : s.role === 'write' ? '读写' : '只读' }}</span></td>
              <td :title="fmtTime(s.login_time)">{{ fmtTime(s.login_time) }}</td>
              <td>{{ s.ip || '-' }}</td>
              <td :title="fmtTime(s.last_active)">{{ relTime(s.last_active) }}</td>
              <td class="path" :title="s.last_path || ''">{{ s.last_path || '-' }}</td>
              <td>{{ s.sessions }}</td>
              <td><button class="sm danger" :disabled="kicking === s.user" @click="doKick(s)">{{ kicking === s.user ? '踢出中...' : '踢下线' }}</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 1001; padding: 16px; box-sizing: border-box; }
.modal-box { background: var(--panel); border-radius: 8px; padding: 20px; width: 94%; max-width: 720px; border: 1px solid var(--border); max-height: 86vh; overflow-y: auto; box-sizing: border-box; }
.modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.modal-header h3 { margin: 0; color: var(--text); }
.hint { font-size: 12px; color: var(--text2); background: var(--panel3); border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; margin-bottom: 10px; }
.empty { font-size: 13px; color: var(--text3); padding: 10px 0; }
.sess-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.sess-table th { text-align: left; color: var(--text2); font-weight: 500; padding: 6px 8px; border-bottom: 1px solid var(--border); white-space: nowrap; }
.sess-table td { padding: 7px 8px; border-bottom: 1px solid var(--border); color: var(--text); white-space: nowrap; }
.sess-table .u { font-weight: 600; }
.sess-table .path { max-width: 180px; overflow: hidden; text-overflow: ellipsis; }
.role { font-size: 11px; padding: 1px 8px; border-radius: 10px; }
.r-admin { background: var(--danger-bg); color: var(--danger-solid); }
.r-write { background: var(--success-bg); color: var(--success); }
.r-read { background: var(--success-bg); color: var(--primary); }
button { padding: 5px 14px; border: 1px solid var(--border); border-radius: 4px; background: var(--panel2); color: var(--text); cursor: pointer; font-size: 13px; }
button.sm { padding: 3px 10px; font-size: 12px; }
button.danger { background: var(--danger); color: #fff; border-color: var(--danger); }
.err-msg { color: var(--danger); font-size: 13px; }
.ok-msg { color: var(--success); font-size: 13px; }
</style>
