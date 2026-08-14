<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { errMsg as toErrMsg } from '@/utils/err'
import { tr } from '@/i18n'
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
  { value: 'sqlite', label: 'conn.sqliteFile' },
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
  aliyun: { name: 'cloud.aliyun', def: 'mysql', ports: { mysql: 3306, postgresql: 5432, mssql: 1433, oracle: 1521, mongodb: 27017 }, tip: 'cloud.aliyun.tip' },
  tencent: { name: 'cloud.tencent', def: 'mysql', ports: { mysql: 3306, postgresql: 5432, mssql: 1433, mongodb: 27017 }, tip: 'cloud.tencent.tip' },
  huawei: { name: 'cloud.huawei', def: 'mysql', ports: { mysql: 3306, postgresql: 5432, mssql: 1433, mongodb: 27017 }, tip: 'cloud.huawei.tip' },
  aws: { name: 'cloud.aws', def: 'postgresql', ports: { mysql: 3306, postgresql: 5432, mssql: 1433, oracle: 1521, mongodb: 27017 }, tip: 'cloud.aws.tip' },
  azure: { name: 'cloud.azure', def: 'mssql', ports: { mysql: 3306, postgresql: 5432, mssql: 1433, mongodb: 27017 }, tip: 'cloud.azure.tip' },
  oracle_cloud: { name: 'cloud.oracle_cloud', def: 'oracle', ports: { oracle: 1521, mysql: 3306, postgresql: 5432 }, tip: 'cloud.oracle_cloud.tip' },
  mongo_cloud: { name: 'cloud.mongo_cloud', def: 'mongodb', ports: { mongodb: 27017 }, tip: 'cloud.mongo_cloud.tip' },
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
    successMsg.value = tr('conn.connectOk')
    setTimeout(() => router.push('/main'), 300)
  } catch (e: unknown) {
    errMsg.value = toErrMsg(e, tr('conn.failConnect'))
  } finally {
    loading.value = false
  }
}

async function doTest() {
  errMsg.value = ''; successMsg.value = ''
  try {
    const r = await testConn(buildPayload())
    if (r.ok) successMsg.value = '✓ ' + (r.message || tr('conn.connectOk'))
    else errMsg.value = '✗ ' + (r.error || tr('conn.failConnect'))
  } catch (e: unknown) {
    errMsg.value = toErrMsg(e, tr('conn.failTest'))
  }
}

async function loadDbs() {
  errMsg.value = ''; successMsg.value = ''
  if (isSqlite.value) { errMsg.value = tr('conn.sqliteNoDbList'); return }
  if (!server.value.trim() || !uid.value.trim()) { errMsg.value = tr('conn.fillServerUid'); return }
  try {
    const payload = buildPayload()
    delete (payload as { database?: unknown }).database
    dbList.value = await listDatabases(payload)
    successMsg.value = tr('conn.loadedDbs', { n: dbList.value.length })
  } catch (e: unknown) {
    errMsg.value = toErrMsg(e, tr('conn.failLoad'))
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
    successMsg.value = tr('conn.connectOkName', { name })
    setTimeout(() => router.push('/main'), 300)
  } catch (e: unknown) {
    errMsg.value = toErrMsg(e, tr('conn.failConnect'))
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
    <header class="conn-head">
      <h2>{{ tr('conn.title') }}</h2>
      <p class="sub">{{ tr('conn.sub') }}</p>
    </header>

    <div class="conn-body">
      <!-- 我的连接: 点击直接连接(无需密码) -->
      <div class="field" v-if="connStore.connList.length">
        <label>{{ tr('conn.myConnLabel') }}</label>
        <div class="conn-list">
          <div v-for="c in connStore.connList" :key="c.name" class="conn-row" @click="doQuickConnect(c.name!)" :title="tr('conn.connectTitle') + ' ' + c.name">
            <span class="dot" :class="{ on: connStore.conn?.name === c.name }"></span>
            <span class="nm">{{ c.name }}</span>
            <span class="det">{{ [c.db_type, c.server, c.database].filter(Boolean).join(' · ') }}</span>
            <span class="go">{{ tr('conn.connect') }}</span>
          </div>
        </div>
      </div>

      <!-- Navicat 快速连接(填入表单) -->
      <div class="field" v-if="connStore.connList.length">
        <label>{{ tr('conn.quickFill') }}</label>
        <div class="row2">
          <select v-model="quickConn" @change="applyQuick">
            <option value="">{{ tr('conn.chooseConn') }}</option>
            <option v-for="c in connStore.connList" :key="c.name" :value="c.name!">{{ c.name }}</option>
          </select>
          <button type="button" @click="applyQuick">{{ tr('conn.fill') }}</button>
        </div>
      </div>

      <!-- 云厂商模板 -->
      <div class="field">
        <label>{{ tr('conn.cloudTemplate') }}</label>
        <select v-model="cloudVendor" @change="onCloudChange">
          <option value="">{{ tr('conn.noCloud') }}</option>
          <option v-for="(v, k) in CLOUD_VENDORS" :key="k" :value="k">{{ tr(v.name) }}</option>
        </select>
        <div v-if="cloudVendor && CLOUD_VENDORS[cloudVendor]" class="tip">{{ tr(CLOUD_VENDORS[cloudVendor].tip) }}</div>
      </div>

      <!-- 数据库类型 -->
      <div class="field">
        <label>{{ tr('conn.dbType') }}</label>
        <select v-model="dbType">
          <option v-for="t in DB_TYPES" :key="t.value" :value="t.value">{{ tr(t.label) }}</option>
        </select>
      </div>

      <!-- SQLite 字段 -->
      <div v-if="isSqlite" class="field">
        <label>{{ tr('conn.sqlitePath') }}</label>
        <input v-model="sqlitePath" :placeholder="tr('conn.sqlitePlaceholder')" />
      </div>

      <!-- 非 SQLite 字段 -->
      <template v-else>
        <div class="field">
          <label>{{ tr('conn.server') }}</label>
          <input v-model="server" :placeholder="tr('conn.serverPlaceholder')" />
        </div>
        <div class="field">
          <label>{{ tr('conn.port') }}</label>
          <input v-model="port" :placeholder="tr('conn.portPlaceholder')" />
        </div>
        <div class="field">
          <label>{{ tr('conn.database') }}</label>
          <div class="row2">
            <input v-model="database" list="dbListDl" :placeholder="tr('conn.database')" />
            <datalist id="dbListDl"><option v-for="d in dbList" :key="d" :value="d" /></datalist>
            <button type="button" @click="loadDbs">{{ tr('conn.load') }}</button>
          </div>
        </div>
        <div class="field">
          <label>{{ tr('conn.uid') }}</label>
          <input v-model="uid" :placeholder="tr('conn.uidPlaceholder')" />
        </div>
      </template>

      <div class="field">
        <label>{{ tr('conn.password') }}</label>
        <input v-model="pwd" type="password" :placeholder="tr('conn.pwdPlaceholder')" @keyup.enter="doConnect" />
      </div>

      <!-- SSH 隧道 -->
      <div class="field">
        <label><input type="checkbox" v-model="sshEnabled" /> {{ tr('conn.useSsh') }}</label>
        <template v-if="sshEnabled">
          <div class="field"><label>{{ tr('conn.sshHost') }}</label><input v-model="sshHost" :placeholder="tr('conn.sshHostPlaceholder')" /></div>
          <div class="field"><label>{{ tr('conn.sshPort') }}</label><input v-model="sshPort" :placeholder="tr('conn.sshPortPlaceholder')" /></div>
          <div class="field"><label>{{ tr('conn.sshUser') }}</label><input v-model="sshUser" :placeholder="tr('conn.sshUserPlaceholder')" /></div>
          <div class="field"><label>{{ tr('conn.sshPwd') }}</label><input v-model="sshPwd" type="password" :placeholder="tr('conn.sshPwdPlaceholder')" /></div>
          <div class="field"><label>{{ tr('conn.sshKey') }}</label><input v-model="sshKey" :placeholder="tr('conn.sshKeyPlaceholder')" /></div>
        </template>
      </div>

      <!-- 保存为我的连接 -->
      <div class="field">
        <label><input type="checkbox" v-model="saveAsMyConn" /> {{ tr('conn.saveAsMy') }}</label>
        <input v-if="saveAsMyConn" v-model="connName" :placeholder="tr('conn.connNamePlaceholder')" style="margin-top:6px" />
      </div>
    </div>

    <!-- 固定底部操作区: 始终可见(内容过长时仅中间表单区滚动) -->
    <footer class="conn-foot">
      <div v-if="errMsg" class="err-msg">{{ errMsg }}</div>
      <div v-if="successMsg" class="ok-msg">{{ successMsg }}</div>
      <div class="conn-actions">
        <button class="primary" :disabled="loading" @click="doConnect">{{ loading ? tr('conn.connecting') : tr('conn.connectBtn') }}</button>
        <button @click="doTest">{{ tr('conn.testConn') }}</button>
      </div>
    </footer>
  </div>
</template>

<style scoped>
/* 卡片容器: 垂直 flex, 竖向空间受父级(#app)约束, 中间表单滚动、底部按钮固定 */
.conn-panel {
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 460px;
  margin: 28px auto;
  max-height: calc(100% - 56px);
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg, 16px);
  box-shadow: var(--shadow-card, 0 12px 40px rgba(0, 0, 0, 0.1));
  overflow: hidden;
}
.conn-head {
  padding: 24px 26px 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  display: block; /* 覆盖全局 header 的 flex, 还原 h2/sub 堆叠; 背景跟随白底, 不再被染黑 */
}
.conn-head h2 {
  margin: 0;
  font-size: 19px;
  font-weight: 650;
  letter-spacing: 0.2px;
  color: var(--text);
}
.conn-head .sub {
  margin: 6px 0 0;
  color: var(--text3);
  font-size: 13px;
  line-height: 1.5;
}
.conn-body {
  padding: 18px 26px;
  overflow-y: auto;
  flex: 1 1 auto;
  min-height: 0;
  scrollbar-width: thin;
  scrollbar-color: var(--border2) transparent;
}
.conn-body::-webkit-scrollbar { width: 8px; }
.conn-body::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 8px; }
.conn-body::-webkit-scrollbar-track { background: transparent; }

/* 固定底部操作区 */
.conn-foot {
  padding: 16px 26px 20px;
  border-top: 1px solid var(--border);
  background: var(--panel);
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex-shrink: 0;
}
.conn-actions {
  display: flex;
  gap: 12px;
}
.conn-actions button {
  flex: 1;
  justify-content: center;
}

.field { margin-bottom: 14px; }
.field label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--text2);
  margin-bottom: 6px;
}
/* 复选框行: 行内排列 */
.field label:has(input[type="checkbox"]) {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
  cursor: pointer;
}
.field input[type="checkbox"] {
  width: auto;
  margin: 0;
  accent-color: var(--primary);
}
.field input, .field select {
  width: 100%;
  padding: 9px 11px;
  border: 1px solid var(--border2);
  border-radius: var(--radius, 10px);
  background: var(--panel);
  color: var(--text);
  font-size: 14px;
  box-sizing: border-box;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.field input:focus, .field select:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: var(--ring, 0 0 0 3px var(--primary-bg));
}
.row2 { display: flex; gap: 8px; align-items: center; }
.row2 input, .row2 select { flex: 1; }
.row2 button { white-space: nowrap; }

.conn-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 200px;
  overflow: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--border2) transparent;
}
.conn-list::-webkit-scrollbar { width: 8px; }
.conn-list::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 8px; }
.conn-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  cursor: pointer;
  font-size: 13px;
  transition: background 0.15s ease, border-color 0.15s ease, transform 0.05s ease;
}
.conn-row:hover { background: var(--panel2); border-color: var(--primary); }
.conn-row:active { transform: scale(0.995); }
.dot { width: 9px; height: 9px; border-radius: 50%; background: var(--text3); flex-shrink: 0; }
.dot.on { background: var(--success); }
.nm { font-weight: 600; white-space: nowrap; }
.det { color: var(--text3); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.go { color: var(--primary); font-size: 12px; font-weight: 600; flex-shrink: 0; }
.tip { font-size: 12px; color: var(--text3); margin-top: 6px; line-height: 1.5; }

.err-msg {
  color: var(--danger);
  background: var(--danger-bg);
  border-left: 3px solid var(--danger);
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 13px;
}
.ok-msg {
  color: var(--success);
  background: var(--success-bg);
  border-left: 3px solid var(--success);
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 13px;
}

button {
  padding: 9px 18px;
  border: 1px solid var(--border2);
  border-radius: var(--radius, 10px);
  background: var(--panel);
  color: var(--text);
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: background 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease, transform 0.05s ease;
}
button:hover { background: var(--panel2); }
button:active { transform: scale(0.99); }
button.primary {
  background: var(--primary);
  color: #fff;
  border-color: var(--primary);
  box-shadow: 0 2px 8px color-mix(in srgb, var(--primary) 35%, transparent);
}
button.primary:hover {
  background: var(--primary);
  filter: brightness(0.94);
  box-shadow: 0 4px 14px color-mix(in srgb, var(--primary) 45%, transparent);
}
button:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
</style>
