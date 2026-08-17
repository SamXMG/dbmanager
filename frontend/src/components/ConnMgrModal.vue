<script setup lang="ts">
import { ref, onMounted } from 'vue'
import Icon from '@/components/Icon.vue'
import { errMsg } from '@/utils/err'
import { confirmDanger } from '@/utils/confirm'
import { useRouter } from 'vue-router'
import { useConnectionStore } from '@/stores/connection'
import { useAuthStore } from '@/stores/auth'
import { saveConnection, testConn, deleteConnection } from '@/api/connection'
import { syncTablesFromConnection } from '@/stores/database'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ close: [] }>()

const router = useRouter()
const connStore = useConnectionStore()
const authStore = useAuthStore()

// 表单状态
const editingName = ref<string | null>(null)
const formVisible = ref(false)
const mName = ref('')
const mType = ref('mysql')
const mServer = ref('')
const mPort = ref('')
const mDb = ref('')
const mUid = ref('')
const mPwd = ref('')
const mSqlitePath = ref('')
const mSsh = ref(false)
const mSshHost = ref('')
const mSshPort = ref('22')
const mSshUser = ref('')
const mSshPwd = ref('')
const mSshKey = ref('')
const mVisibleTo = ref('')
const mReadOnly = ref(false)
const msg = ref('')
const msgErr = ref(false)
const loading = ref(false)

const DB_TYPES = [
  { value: 'sqlite', label: 'SQLite' },
  { value: 'mysql', label: 'MySQL' },
  { value: 'postgresql', label: 'PostgreSQL' },
  { value: 'mssql', label: 'SQL Server' },
  { value: 'oracle', label: 'Oracle' },
  { value: 'oceanbase', label: 'OceanBase' },
  { value: 'tidb', label: 'TiDB' },
  { value: 'kingbase', label: 'KingbaseES' },
  { value: 'mongodb', label: 'MongoDB' },
  { value: 'redis', label: 'Redis' },
]

const DEF_PORTS: Record<string, number> = { mysql: 3306, postgresql: 5432, mssql: 1433, oracle: 1521, mongodb: 27017, redis: 6379, oceanbase: 2881, tidb: 4000, kingbase: 54321 }

function resetForm() {
  editingName.value = null; formVisible.value = false
  mName.value = ''; mType.value = 'mysql'; mServer.value = ''; mPort.value = ''
  mDb.value = ''; mUid.value = ''; mPwd.value = ''; mSqlitePath.value = ''
  mSsh.value = false; mSshHost.value = ''; mSshPort.value = '22'
  mSshUser.value = ''; mSshPwd.value = ''; mSshKey.value = ''
  mVisibleTo.value = ''; mReadOnly.value = false
}

function showNew() { resetForm(); editingName.value = null; formVisible.value = true }

function editConn(name: string) {
  const c = connStore.connList.find(x => x.name === name)
  if (!c) return
  resetForm()
  editingName.value = name; formVisible.value = true
  mName.value = c.name || ''; mType.value = c.db_type || 'mysql'
  mServer.value = c.server || ''; mPort.value = c.port ? String(c.port) : ''
  mDb.value = c.database || ''; mUid.value = c.uid || ''; mPwd.value = ''
  mSqlitePath.value = c.database || ''
  mVisibleTo.value = (c.visible_to || []).join(', ')
  mReadOnly.value = c.mode === 'read_only'
  msg.value = '已载入连接信息，密码需重新输入（留空则保持不变）'; msgErr.value = false
}

async function doSave() {
  msg.value = ''; msgErr.value = false
  const name = mName.value.trim()
  if (!name) { msg.value = '请填写连接名称'; msgErr.value = true; return }
  const isSql = mType.value === 'sqlite'
  let payload: Record<string, unknown>
  if (isSql) {
    if (!mSqlitePath.value.trim()) { msg.value = '请填写数据库文件路径'; msgErr.value = true; return }
    payload = { name, db_type: 'sqlite', database: mSqlitePath.value.trim(), pwd: mPwd.value }
  } else {
    if (!mServer.value.trim() || !mUid.value.trim()) { msg.value = '请填写服务器与账号'; msgErr.value = true; return }
    payload = {
      name, db_type: mType.value, server: mServer.value.trim(),
      port: mPort.value ? parseInt(mPort.value, 10) : (DEF_PORTS[mType.value] || 3306),
      database: mDb.value.trim(), uid: mUid.value.trim(), pwd: mPwd.value,
    }
    if (mSsh.value && mSshHost.value.trim()) {
      payload.tunnel = { host: mSshHost.value.trim(), port: parseInt(mSshPort.value, 10) || 22, user: mSshUser.value.trim(), password: mSshPwd.value, key: mSshKey.value.trim() }
    }
  }
  if (authStore.isAdmin) {
    const vt = mVisibleTo.value.split(/[,，\s]+/).map(s => s.trim()).filter(Boolean)
    if (vt.length) payload.visible_to = vt
    if (mReadOnly.value) payload.mode = 'read_only'
  }
  loading.value = true
  try {
    await saveConnection(payload)
    await connStore.refreshConnList()
    formVisible.value = false
    msg.value = '已保存连接 ' + name; msgErr.value = false
  } catch (e: unknown) {
    msg.value = errMsg(e, '保存失败'); msgErr.value = true
  } finally { loading.value = false }
}

async function doDelete(name: string) {
  if (!await confirmDanger(`确认删除连接「${name}」？`)) return
  try {
    await connStore.deleteConn(name)
    msg.value = '已删除 ' + name; msgErr.value = false
  } catch (e: unknown) {
    msg.value = errMsg(e, '删除失败'); msgErr.value = true
  }
}

async function doConnect(name: string) {
  loading.value = true
  try {
    await connStore.connectAndGo({ name })
    syncTablesFromConnection() // 表数据同步到树 store
    emit('close')
    setTimeout(() => router.push('/main'), 200)
  } catch (e: unknown) {
    msg.value = errMsg(e, '连接失败'); msgErr.value = true
  } finally { loading.value = false }
}

async function doTest(name: string) {
  try {
    const r = await testConn({ name })
    msg.value = r.ok ? `✓ ${r.message || '连接成功'}` : `✗ ${r.error || '连接失败'}`
    msgErr.value = !r.ok
  } catch (e: unknown) {
    msg.value = errMsg(e, '测试失败'); msgErr.value = true
  }
}

onMounted(() => { connStore.refreshConnList() })
</script>

<template>
  <Teleport to="body">
    <div v-if="show" class="modal-mask" @click.self="emit('close')">
      <div class="modal-box" style="max-width:700px" v-draggable-modal>
        <div class="modal-header">
          <h3>我的连接</h3>
          <button class="sm" @click="emit('close')"><Icon name="x" :size="14" /></button>
        </div>

        <!-- 消息 -->
        <div v-if="msg" :class="msgErr ? 'err-msg' : 'ok-msg'" style="margin-bottom:8px">{{ msg }}</div>

        <!-- 连接列表 -->
        <div v-if="!formVisible">
          <button class="primary sm" style="margin-bottom:10px" @click="showNew">+ 新建连接</button>
          <div v-if="!connStore.connList.length" class="empty2">还没有保存的连接，点上方「+ 新建连接」添加一个。</div>
          <div v-for="c in connStore.connList" :key="c.name" class="conn-row">
            <div class="meta" @dblclick="doConnect(c.name!)">
              <b>{{ c.name }}<template v-if="c.visible_to && c.visible_to.length"><Icon name="lock" :size="13"/></template><template v-if="c.mode === 'read_only'"><Icon name="shield" :size="13"/></template></b>
              <div class="det">{{ [c.db_type, (c.server||'')+(c.port?':'+c.port:''), c.database, c.uid].filter(Boolean).join(' · ') }}</div>
            </div>
            <div class="acts">
              <button class="sm primary" @click="doConnect(c.name!)">连接</button>
              <button class="sm" @click="doTest(c.name!)">测试</button>
              <button class="sm" @click="editConn(c.name!)">编辑</button>
              <button class="sm danger" @click="doDelete(c.name!)">删除</button>
            </div>
          </div>
        </div>

        <!-- 连接表单 -->
        <div v-else>
          <h4 style="margin:0 0 10px">{{ editingName ? '编辑连接 · ' + editingName : '新建连接' }}</h4>
          <div class="field"><label>连接名称</label><input v-model="mName" /></div>
          <div class="field"><label>数据库类型</label>
            <select v-model="mType"><option v-for="t in DB_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option></select>
          </div>
          <template v-if="mType !== 'sqlite'">
            <div class="field"><label>服务器</label><input v-model="mServer" /></div>
            <div class="field"><label>端口</label><input v-model="mPort" /></div>
            <div class="field"><label>数据库</label><input v-model="mDb" /></div>
            <div class="field"><label>用户名</label><input v-model="mUid" /></div>
          </template>
          <div v-else class="field"><label>数据库文件路径</label><input v-model="mSqlitePath" /></div>
          <div class="field"><label>密码</label><input v-model="mPwd" type="password" placeholder="留空则保持不变" /></div>

          <!-- SSH 隧道 -->
          <div class="field"><label><input type="checkbox" v-model="mSsh" /> 使用 SSH 隧道</label>
            <template v-if="mSsh">
              <div class="field"><label>SSH 主机</label><input v-model="mSshHost" /></div>
              <div class="field"><label>SSH 端口</label><input v-model="mSshPort" /></div>
              <div class="field"><label>SSH 用户</label><input v-model="mSshUser" /></div>
              <div class="field"><label>SSH 密码</label><input v-model="mSshPwd" type="password" /></div>
              <div class="field"><label>SSH 密钥文件</label><input v-model="mSshKey" /></div>
            </template>
          </div>

          <!-- ACL 字段(仅 admin) -->
          <template v-if="authStore.isAdmin">
            <div class="field"><label>可见用户（逗号分隔，空=所有人可见）</label><input v-model="mVisibleTo" placeholder="如 alice,bob" /></div>
            <div class="field"><label><input type="checkbox" v-model="mReadOnly" /> 只读模式（禁止所有写操作）</label></div>
          </template>

          <div class="row2" style="margin-top:12px">
            <button class="primary" :disabled="loading" @click="doSave">{{ loading ? '保存中...' : '保存' }}</button>
            <button @click="formVisible = false">取消</button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 1000; padding: 16px; box-sizing: border-box; }
.modal-box { background: var(--panel); border-radius: 8px; padding: 20px; width: 90%; max-width: 700px; border: 1px solid var(--border); max-height: calc(100vh - 32px); overflow-y: auto; box-sizing: border-box; }
.modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.modal-header h3 { margin: 0; color: var(--text); }
.conn-row { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--border); }
.meta b { color: var(--text); }
.det { font-size: 12px; color: var(--text2); margin-top: 2px; }
.acts { display: flex; gap: 4px; }
.field { margin-bottom: 8px; }
.field label { display: block; font-size: 13px; color: var(--text2); margin-bottom: 3px; }
.field input, .field select { width: 100%; padding: 6px 8px; border: 1px solid var(--border2); border-radius: 4px; background: var(--panel3); color: var(--text); font-size: 14px; box-sizing: border-box; }
.row2 { display: flex; gap: 6px; }
.err-msg { color: var(--danger); font-size: 13px; }
.ok-msg { color: var(--success); font-size: 13px; }
.empty2 { color: var(--text3); font-size: 13px; padding: 16px 0; text-align: center; }
button { padding: 6px 16px; border: 1px solid var(--border); border-radius: 4px; background: var(--panel2); color: var(--text); cursor: pointer; font-size: 13px; }
button.primary { background: var(--primary); color: #fff; border-color: var(--primary); }
button.sm { padding: 4px 10px; font-size: 12px; }
button.danger { color: var(--danger); border-color: var(--danger); }
button:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
