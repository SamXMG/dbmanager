<script setup lang="ts">
// 账号管理弹窗: 用户列表/审批(自助注册)/新建/删除/改角色/细粒度权限(仅 admin)
// 局域网一次性部署定位: 成员自助注册 -> 管理员在此审批放权; 权限按 连接/表 级配置
import { ref, computed, onMounted } from 'vue'
import Icon from '@/components/Icon.vue'
import { errMsg } from '@/utils/err'
import { confirmDanger } from '@/utils/confirm'
import { listUsers, saveUser, deleteUser, approveUser, type UserInfo } from '@/api/account'
import { useUIStore } from '@/stores/ui'
import PermModal from '@/components/PermModal.vue'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ close: [] }>()

const ui = useUIStore()
const users = ref<UserInfo[]>([])
const loading = ref(false)
const msg = ref('')
const msgErr = ref(false)

// 新建用户表单
const newName = ref('')
const newPwd = ref('')
const newRole = ref<'read' | 'write' | 'admin'>('read')

// 每行的审批角色下拉(默认 read)
const pendingRole = ref<Record<string, string>>({})

// 批量权限: 勾选集合 + 权限弹窗
const selected = ref<Record<string, boolean>>({})
const showPerm = ref(false)
const permUsers = ref<string[]>([])
const selectedCount = computed(() => Object.values(selected.value).filter(Boolean).length)

const statusText: Record<string, string> = { pending: '待审批', active: '正常', rejected: '已拒绝' }

async function refresh() {
  loading.value = true
  try {
    const r = await listUsers()
    users.value = r.users || []
    // 清理已删除用户的勾选
    const names = new Set(users.value.map(u => u.username))
    for (const k of Object.keys(selected.value)) if (!names.has(k)) delete selected.value[k]
  } catch (e) { msg.value = errMsg(e); msgErr.value = true }
  loading.value = false
}

function showInfo(m: string, err = false) {
  msg.value = m; msgErr.value = err
  setTimeout(() => { if (msg.value === m) msg.value = '' }, 3000)
}

async function doApprove(username: string) {
  try {
    await approveUser(username, pendingRole.value[username] || 'read', 'approve')
    showInfo('已批准 ' + username)
    refresh()
  } catch (e) { showInfo(errMsg(e), true) }
}

async function doReject(username: string) {
  if (!await confirmDanger('拒绝账号 ' + username + '？拒绝后该账号无法登录。')) return
  try {
    await approveUser(username, 'read', 'reject')
    showInfo('已拒绝 ' + username)
    refresh()
  } catch (e) { showInfo(errMsg(e), true) }
}

async function doSaveNew() {
  if (!newName.value || !newPwd.value) { showInfo('请填写用户名和密码', true); return }
  try {
    await saveUser({ username: newName.value, role: newRole.value, password: newPwd.value })
    showInfo('账号已创建')
    newName.value = ''; newPwd.value = ''
    refresh()
  } catch (e) { showInfo(errMsg(e), true) }
}

async function doChangeRole(username: string, role: string) {
  try {
    await saveUser({ username, role })
    showInfo('已更新 ' + username + ' 角色')
    refresh()
  } catch (e) { showInfo(errMsg(e), true) }
}

async function doDelete(username: string) {
  if (!await confirmDanger('删除账号 ' + username + '？此操作不可撤销。')) return
  try {
    await deleteUser(username)
    showInfo('已删除 ' + username)
    refresh()
  } catch (e) { showInfo(errMsg(e), true) }
}

/** 单用户权限配置入口 */
function openPerm(username: string) {
  permUsers.value = [username]
  showPerm.value = true
}

/** 批量权限配置入口(勾选多个用户) */
function openBatchPerm() {
  const names = users.value.filter(u => selected.value[u.username]).map(u => u.username)
  if (!names.length) { showInfo('请先勾选要配置的用户', true); return }
  if (names.length > 20) { showInfo('批量配置一次最多 20 个用户', true); return }
  permUsers.value = names
  showPerm.value = true
}

function clearSel() { selected.value = {} }

onMounted(refresh)
</script>

<template>
  <Teleport to="body">
    <div v-if="show" class="modal-mask" @click.self="emit('close')">
      <div class="modal-box" style="max-width:640px" v-draggable-modal>
        <div class="modal-header">
          <h3>账号管理</h3>
          <button class="sm" @click="emit('close')"><Icon name="x" :size="14" /></button>
        </div>

        <div v-if="msg" :class="msgErr ? 'err-msg' : 'ok-msg'" style="margin-bottom:8px">{{ msg }}</div>

        <div class="section-title">待审批注册（成员自助注册后需管理员放权）</div>
        <div v-if="users.filter(u => u.status === 'pending').length === 0" class="empty">暂无待审批账号</div>
        <div v-for="u in users.filter(x => x.status === 'pending')" :key="u.username" class="user-row">
          <span class="name">{{ u.username }}</span>
          <select v-model="pendingRole[u.username]" style="width:90px">
            <option value="read">只读</option>
            <option value="write">读写</option>
          </select>
          <button class="sm primary" @click="doApprove(u.username)">批准</button>
          <button class="sm danger" @click="doReject(u.username)">拒绝</button>
        </div>

        <div class="section-title">全部用户</div>
        <div v-if="loading" class="empty">加载中...</div>
        <div v-for="u in users" :key="u.username" class="user-row">
          <label class="chk" @click.stop><input type="checkbox" v-model="selected[u.username]" /> </label>
          <span class="name">{{ u.username }}</span>
          <span class="status" :class="'st-' + (u.status || 'active')">{{ statusText[u.status || 'active'] || u.status }}</span>
          <select v-if="u.status !== 'pending'" :value="u.role" @change="doChangeRole(u.username, ($event.target as HTMLSelectElement).value)" style="width:90px">
            <option value="read">只读</option>
            <option value="write">读写</option>
            <option value="admin">管理</option>
          </select>
          <button v-if="u.status !== 'pending'" class="sm" @click="openPerm(u.username)" title="配置该用户可访问的库/表与读写权限">权限</button>
          <button v-if="u.status !== 'pending'" class="sm danger" @click="doDelete(u.username)">删除</button>
        </div>

        <div v-if="selectedCount" class="batch-bar">
          <span>已勾选 <b>{{ selectedCount }}</b> 个用户</span>
          <button class="sm primary" @click="openBatchPerm" title="对勾选用户批量配置相同的库/表读写权限">批量设置权限</button>
          <button class="sm" @click="clearSel">取消勾选</button>
        </div>

        <div class="section-title">新建用户（管理员直接创建，无需审批）</div>
        <div class="new-row">
          <input v-model="newName" placeholder="用户名" style="width:110px" />
          <input v-model="newPwd" type="password" placeholder="密码(至少6位)" style="width:130px" />
          <select v-model="newRole" style="width:90px">
            <option value="read">只读</option>
            <option value="write">读写</option>
            <option value="admin">管理</option>
          </select>
          <button class="sm primary" @click="doSaveNew">创建</button>
        </div>
      </div>
    </div>
    <PermModal v-if="showPerm" :show="showPerm" :usernames="permUsers" @close="showPerm = false" @saved="clearSel" />
  </Teleport>
</template>

<style scoped>
.modal-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: var(--panel); border-radius: 8px; padding: 20px; width: 92%; max-width: 640px; border: 1px solid var(--border); max-height: 86vh; overflow: auto; }
.modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.modal-header h3 { margin: 0; color: var(--text); }
.section-title { font-size: 13px; font-weight: 500; color: var(--text2); margin: 12px 0 6px; }
.user-row { display: flex; align-items: center; gap: 8px; padding: 5px 0; border-bottom: 1px solid var(--border); }
.user-row .name { flex: 1; font-size: 13px; color: var(--text); }
.chk { display: inline-flex; align-items: center; color: var(--text3); }
.batch-bar { display: flex; align-items: center; gap: 8px; margin-top: 8px; padding: 8px 10px; background: var(--panel3); border: 1px solid var(--border); border-radius: 6px; font-size: 13px; color: var(--text); }
.status { font-size: 12px; padding: 1px 8px; border-radius: 10px; }
.st-pending { background: var(--warning-bg); color: var(--warning); }
.st-active { background: var(--success-bg); color: var(--success); }
.st-rejected { background: var(--danger-bg); color: var(--danger-solid); }
.empty { font-size: 13px; color: var(--text3); padding: 6px 0; }
.new-row { display: flex; align-items: center; gap: 8px; }
input, select { padding: 5px 8px; border: 1px solid var(--border2); border-radius: 4px; background: var(--panel3); color: var(--text); font-size: 13px; }
.err-msg { color: var(--danger); font-size: 13px; }
.ok-msg { color: var(--success); font-size: 13px; }
button { padding: 5px 14px; border: 1px solid var(--border); border-radius: 4px; background: var(--panel2); color: var(--text); cursor: pointer; font-size: 13px; }
button.primary { background: var(--primary); color: #fff; border-color: var(--primary); }
button.sm { padding: 4px 10px; font-size: 12px; }
button.danger { background: var(--danger); color: #fff; border-color: var(--danger); }
</style>
