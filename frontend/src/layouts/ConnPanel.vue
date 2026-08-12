<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useConnectionStore } from '@/stores/connection'
import { useAuthStore } from '@/stores/auth'
import { syncTablesFromConnection } from '@/stores/database'
import { testConn, listDatabases, saveConnection } from '@/api/connection'

const router = useRouter()
const connStore = useConnectionStore()
const authStore = useAuthStore()

// ---- 表单状态 ----
const dbType = ref('mysql')
const server = ref('localhost')
const port = ref('')
const database = ref('')
const uid = ref('')
const pwd = ref('')
const sqlitePath = ref('')
const quickConn = ref('')
const loading = ref(false)
const errMsg = ref('')
const successMsg = ref('')
const dbList = ref<string[]>([])
const saveAsMyConn = ref(false)
const connName = ref('')

// SSH 隧道
const sshEnabled = ref(false)
const sshHost = ref('')
const sshPort = ref('22')
const sshUser = ref('')
const sshPwd = ref('')
const sshKey = ref('')

// 云厂商
const cloudVendor = ref('')

const isSqlite = computed(() => dbType.value === 'sqlite')

const DB_TYPES = [
  { value: 'sqlite', label: 'SQLite（文件）' },
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

const CLOUD_VENDORS: Record<string, { name: string; def: string; ports: Record<string, number>; tip: string }> = {
  aliyun: { name: '阿里云', def: 'mysql', ports: { mysql: 3306, postgresql: 5432, mssql: 1433, oracle: 1521, mongodb: 27017 }, tip: '需在云控制台开启公网访问并配置白名单；生产环境建议用内网地址 + SSH 隧道' },
  tencent: { name: '腾讯云', def: 'mysql', ports: { mysql: 3306, postgresql: 5432, mssql: 1433, mongodb: 27017 }, tip: '需在控制台开通外网地址并放行安全组；内网建议 SSH 隧道' },
  huawei: { name: '华为云', def: 'mysql', ports: { mysql: 3306, postgresql: 5432, mssql: 1433, mongodb: 27017 }, tip: '需绑定弹性IP/开启公网，并配置安全组放行来源IP' },
  aws: { name: 'Amazon AWS', def: 'postgresql', ports: { mysql: 3306, postgresql: 5432, mssql: 1433, oracle: 1521, mongodb: 27017 }, tip: '需在安全组(Security Group)放行来源IP；VPC 内建议 SSH 隧道' },
  azure: { name: 'Microsoft Azure', def: 'mssql', ports: { mysql: 3306, postgresql: 5432, mssql: 1433, mongodb: 27017 }, tip: '需在防火墙规则中添加客户端IP；内网可用 SSH 隧道' },
  oracle_cloud: { name: 'Oracle Cloud', def: 'oracle', ports: { oracle: 1521, mysql: 3306, postgresql: 5432 }, tip: '需在 OCI 网络安全组放行端口；Autonomous DB 建议公网端点 + 隧道' },
  mongo_cloud: { name: 'MongoDB Atlas', def: 'mongodb', ports: { mongodb: 27017 }, tip: '需在 Atlas Network Access 白名单中加入来源 IP' },
}

const DEF_PORTS: Record<string, number> = { mysql: 3306, postgresql: 5432, mssql: 1433, oracle: 1521, mongodb: 27017, redis: 6379, oceanbase: 2881, tidb: 4000, kingbase: 54321 }

function defPort(type: string): number { return DEF_PORTS[type] || 3306 }

function onCloudChange() {
  const v = cloudVendor.value
  if (!v) return
  const c = CLOUD_VENDORS[v]
  if (c && c.def) {
    dbType.value = c.def
    const p = c.ports[c.def]
    if (p) port.value = String(p)
  }
}

function buildPayload(): Record<string, unknown> {
  if (isSqlite.value) {
    return { db_type: 'sqlite', database: sqlitePath.value.trim(), pwd: pwd.value }
  }
  const payload: Record<string, unknown> = {
    db_type: dbType.value,
    server: server.value.trim(),
    port: port.value ? parseInt(port.value, 10) : defPort(dbType.value),
    database: database.value.trim(),
    uid: uid.value.trim(),
    pwd: pwd.value,
  }
  if (sshEnabled.value && sshHost.value.trim()) {
    payload.tunnel = {
      host: sshHost.value.trim(),
      port: parseInt(sshPort.value, 10) || 22,
      user: sshUser.value.trim(),
      password: sshPwd.value,
      key: sshKey.value.trim(),
    }
  }
  return payload
}

async function doConnect() {
  errMsg.value = ''; successMsg.value = ''
  if (loading.value) return
  loading.value = true
  try {
    const payload = buildPayload()
    if (saveAsMyConn.value && connName.value.trim()) {
      payload.name = connName.value.trim()
    }
    await connStore.connectAndGo(payload)
    syncTablesFromConnection() // 表数据同步到树 store
    successMsg.value = '连接成功'
    setTimeout(() => router.push('/main'), 300)
  } catch (e: any) {
    errMsg.value = e.message || '连接失败'
  } finally {
    loading.value = false
  }
}

async function doTest() {
  errMsg.value = ''; successMsg.value = ''
  try {
    const r = await testConn(buildPayload())
    if (r.ok) successMsg.value = '✓ ' + (r.message || '连接成功')
    else errMsg.value = '✗ ' + (r.error || '连接失败')
  } catch (e: any) {
    errMsg.value = e.message || '测试失败'
  }
}

async function loadDbs() {
  errMsg.value = ''; successMsg.value = ''
  if (isSqlite.value) { errMsg.value = 'SQLite 无需加载库列表'; return }
  if (!server.value.trim() || !uid.value.trim()) { errMsg.value = '请先填服务器与账号'; return }
  try {
    const payload = buildPayload()
    delete (payload as any).database
    dbList.value = await listDatabases(payload)
    successMsg.value = `已加载 ${dbList.value.length} 个数据库`
  } catch (e: any) {
    errMsg.value = e.message || '加载失败'
  }
}

function applyQuick() {
  if (!quickConn.value) return
  const c = connStore.connList.find(x => x.name === quickConn.value)
  if (!c) return
  dbType.value = c.db_type || 'mysql'
  server.value = c.server || ''
  port.value = c.port ? String(c.port) : ''
  database.value = c.database || ''
  uid.value = c.uid || ''
  pwd.value = ''
}

/** 我的连接: 按名直连(后端解密密码, 无需手动输入) */
async function doQuickConnect(name: string) {
  if (loading.value) return
  errMsg.value = ''; successMsg.value = ''
  loading.value = true
  try {
    await connStore.connectAndGo({ name })
    syncTablesFromConnection() // 表数据同步到树 store
    successMsg.value = '连接成功: ' + name
    setTimeout(() => router.push('/main'), 300)
  } catch (e: any) {
    errMsg.value = e.message || '连接失败'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await connStore.initConfig()
  if (connStore.defaultConn) {
    quickConn.value = connStore.defaultConn
    applyQuick()
  }
})
</script>

<template>
  <div class="conn-panel">
    <h2>连接数据库</h2>
    <div class="sub">支持 SQLite / MySQL / PostgreSQL / SQL Server / Oracle / MongoDB / Redis。</div>

    <!-- 我的连接: 点击直接连接(无需密码) -->
    <div class="field" v-if="connStore.connList.length">
      <label>我的连接（点击直接连接，无需输入密码）</label>
      <div class="conn-list">
        <div v-for="c in connStore.connList" :key="c.name" class="conn-row" @click="doQuickConnect(c.name!)" :title="'连接 ' + c.name">
          <span class="dot" :class="{ on: connStore.conn?.name === c.name }"></span>
          <span class="nm">{{ c.name }}</span>
          <span class="det">{{ [c.db_type, c.server, c.database].filter(Boolean).join(' · ') }}</span>
          <span class="go">连接 →</span>
        </div>
      </div>
    </div>

    <!-- Navicat 快速连接(填入表单) -->
    <div class="field" v-if="connStore.connList.length">
      <label>快速填入表单</label>
      <div class="row2">
        <select v-model="quickConn" @change="applyQuick">
          <option value="">— 选择连接填入表单 —</option>
          <option v-for="c in connStore.connList" :key="c.name" :value="c.name!">{{ c.name }}</option>
        </select>
        <button type="button" @click="applyQuick">填入</button>
      </div>
    </div>

    <!-- 云厂商模板 -->
    <div class="field">
      <label>云厂商快速模板</label>
      <select v-model="cloudVendor" @change="onCloudChange">
        <option value="">— 不使用 —</option>
        <option v-for="(v, k) in CLOUD_VENDORS" :key="k" :value="k">{{ v.name }}</option>
      </select>
      <div v-if="cloudVendor && CLOUD_VENDORS[cloudVendor]" class="tip">{{ CLOUD_VENDORS[cloudVendor].tip }}</div>
    </div>

    <!-- 数据库类型 -->
    <div class="field">
      <label>数据库类型</label>
      <select v-model="dbType">
        <option v-for="t in DB_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
      </select>
    </div>

    <!-- SQLite 字段 -->
    <div v-if="isSqlite" class="field">
      <label>数据库文件路径</label>
      <input v-model="sqlitePath" placeholder="如 C:\data\mydb.sqlite 或 :memory:" />
    </div>

    <!-- 非 SQLite 字段 -->
    <template v-else>
      <div class="field">
        <label>服务器 (SERVER)</label>
        <input v-model="server" placeholder="如 localhost 或 192.168.1.10\sql2019" />
      </div>
      <div class="field">
        <label>端口 (PORT，可选)</label>
        <input v-model="port" placeholder="默认按类型自动填充" />
      </div>
      <div class="field">
        <label>数据库 (DATABASE)</label>
        <div class="row2">
          <input v-model="database" list="dbListDl" placeholder="数据库名" />
          <datalist id="dbListDl"><option v-for="d in dbList" :key="d" :value="d" /></datalist>
          <button type="button" @click="loadDbs">加载</button>
        </div>
      </div>
      <div class="field">
        <label>用户名 (UID)</label>
        <input v-model="uid" placeholder="数据库登录账号" />
      </div>
    </template>

    <div class="field">
      <label>密码 (PASSWORD)</label>
      <input v-model="pwd" type="password" placeholder="数据库密码" @keyup.enter="doConnect" />
    </div>

    <!-- SSH 隧道 -->
    <div class="field">
      <label><input type="checkbox" v-model="sshEnabled" /> 使用 SSH 隧道</label>
      <template v-if="sshEnabled">
        <div class="field"><label>SSH 主机</label><input v-model="sshHost" placeholder="跳板机地址" /></div>
        <div class="field"><label>SSH 端口</label><input v-model="sshPort" placeholder="22" /></div>
        <div class="field"><label>SSH 用户</label><input v-model="sshUser" placeholder="SSH 用户名" /></div>
        <div class="field"><label>SSH 密码</label><input v-model="sshPwd" type="password" placeholder="SSH 密码（与密钥二选一）" /></div>
        <div class="field"><label>SSH 密钥文件</label><input v-model="sshKey" placeholder="私钥文件路径（可选）" /></div>
      </template>
    </div>

    <!-- 保存为我的连接 -->
    <div class="field">
      <label><input type="checkbox" v-model="saveAsMyConn" /> 保存为我的连接</label>
      <input v-if="saveAsMyConn" v-model="connName" placeholder="连接名称" style="margin-top:4px" />
    </div>

    <!-- 操作按钮 -->
    <div class="row2" style="margin-top:12px">
      <button class="primary" :disabled="loading" @click="doConnect">{{ loading ? '连接中...' : '连接' }}</button>
      <button @click="doTest">测试连接</button>
    </div>

    <!-- 消息 -->
    <div v-if="errMsg" class="err-msg">{{ errMsg }}</div>
    <div v-if="successMsg" class="ok-msg">{{ successMsg }}</div>
  </div>
</template>

<style scoped>
.conn-panel { max-width: 600px; margin: 40px auto; padding: 24px; background: var(--panel); border-radius: 8px; border: 1px solid var(--border); }
.conn-panel h2 { margin: 0 0 4px; color: var(--text); }
.sub { color: var(--text2); font-size: 13px; margin-bottom: 16px; }
.field { margin-bottom: 10px; }
.field label { display: block; font-size: 13px; color: var(--text2); margin-bottom: 3px; }
.field input, .field select { width: 100%; padding: 6px 8px; border: 1px solid var(--border2); border-radius: 4px; background: var(--panel3); color: var(--text); font-size: 14px; box-sizing: border-box; }
.row2 { display: flex; gap: 6px; align-items: center; }
.row2 input, .row2 select { flex: 1; }
.row2 button { white-space: nowrap; }
.conn-list { display: flex; flex-direction: column; gap: 4px; max-height: 220px; overflow: auto; }
.conn-row { display: flex; align-items: center; gap: 8px; padding: 7px 10px; border: 1px solid var(--border); border-radius: 6px; cursor: pointer; font-size: 13px; }
.conn-row:hover { background: var(--panel2); border-color: var(--primary); }
.dot { width: 8px; height: 8px; border-radius: 50%; background: #999; flex-shrink: 0; }
.dot.on { background: #52c41a; }
.nm { font-weight: 600; white-space: nowrap; }
.det { color: var(--text3); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.go { color: var(--primary); font-size: 12px; flex-shrink: 0; }
.tip { font-size: 12px; color: var(--text3); margin-top: 4px; line-height: 1.5; }
.err-msg { color: #e54d42; margin-top: 8px; font-size: 13px; }
.ok-msg { color: #00b42a; margin-top: 8px; font-size: 13px; }
button { padding: 6px 16px; border: 1px solid var(--border); border-radius: 4px; background: var(--panel2); color: var(--text); cursor: pointer; font-size: 13px; }
button.primary { background: var(--primary); color: #fff; border-color: var(--primary); }
button:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
