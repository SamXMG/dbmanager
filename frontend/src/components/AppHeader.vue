<script setup lang="ts">
// 顶栏: 连接信息/用户/角色/主题切换/事务(真实现: 开关+提交/回滚)/停止服务
import { ref, computed, defineAsyncComponent } from 'vue'
import { errMsg } from '@/utils/err'
import { useRouter } from 'vue-router'
import { useConnectionStore } from '@/stores/connection'
import { useAuthStore } from '@/stores/auth'
import { useUIStore } from '@/stores/ui'
import { useTabStore } from '@/stores/tab'
import { shutdown } from '@/api/connection'
import { txCommit, txRollback } from '@/api/data'
import { confirmDanger } from '@/utils/confirm'
import Icon from '@/components/Icon.vue'
// 复核 P1-9: 低频管理模态懒加载(打开时才拉取); AuthModal 登录弹窗首屏必经, 保持同步
import AuthModal from '@/components/AuthModal.vue'
const ConnMgrModal = defineAsyncComponent(() => import('@/components/ConnMgrModal.vue'))
const UserAdminModal = defineAsyncComponent(() => import('@/components/UserAdminModal.vue'))
const SessionModal = defineAsyncComponent(() => import('@/components/SessionModal.vue'))
const SystemQueryModal = defineAsyncComponent(() => import('@/components/SystemQueryModal.vue'))
const ServerConfigModal = defineAsyncComponent(() => import('@/components/ServerConfigModal.vue'))

const router = useRouter()
const conn = useConnectionStore()
const auth = useAuthStore()
const ui = useUIStore()
const tabStore = useTabStore()

const showConnMgr = ref(false)
const showAuth = ref(false)
const showUserAdmin = ref(false)
const showSessions = ref(false)
const showSysQuery = ref(false)
const showServerConfig = ref(false)

const info = computed(() => {
  if (!conn.conn) return ''
  const c = conn.conn
  return [c.db_type, c.server, c.database].filter(Boolean).join(' · ')
})

function toggleTheme() {
  const dark = document.body.dataset.theme === 'dark'
  document.body.dataset.theme = dark ? '' : 'dark'
  try { localStorage.setItem('dbm_theme', dark ? 'light' : 'dark') } catch { /* */ }
}

/** 事务模式: 开启=ui.toggleTx(); 关闭=先回滚未提交修改(对齐旧版) */
async function toggleTx() {
  if (ui.transactionMode) {
    if (!(await confirmDanger('关闭事务模式将回滚所有未提交的修改，确认？', '关闭事务模式'))) {
      await doRollback()
      ui.toggleTx()
    }
  } else {
    ui.toggleTx()
    ui.toast('事务模式已开启: 增删改进入事务, 可统一提交/回滚')
  }
}

async function doCommit() {
  if (!await confirmDanger('确认提交所有修改？提交后无法撤销。', '提交事务')) return
  try {
    await txCommit(tabStore.activeId ?? 0)
    ui.toast('事务已提交')
  } catch (e) { ui.toast('提交失败: ' + errMsg(e), true) }
}

async function doRollback() {
  try {
    await txRollback(tabStore.activeId ?? 0)
    ui.toast('已回滚所有修改')
  } catch (e) { ui.toast('回滚失败: ' + errMsg(e), true) }
}

// P1-10: 停服改 SPA 内状态遮罩(原 document.body.innerHTML 暴力清空整个 SPA, 破坏路由/状态)
const stopped = ref(false)
async function doShutdown() {
  if (!await confirmDanger('确认停止服务？\n停止后页面将无法使用，需重新启动 app.py 才能再次访问。', '停止服务')) return
  try { await shutdown() } catch { /* 服务已停 */ }
  stopped.value = true
  ui.toast('服务已停止')
}

async function logout() {
  conn.disconnect()
  await auth.logout()   // 清内存令牌 + 调 /api/logout 删会话清 HttpOnly Cookie
  router.push('/')
}
</script>

<template>
  <header class="app-header">
    <h1>DB Manager</h1>
    <span class="db" v-if="conn.connected">{{ info }}</span>
    <div class="right">
      <span v-if="conn.connected" style="font-size:13px;color:var(--text2);margin-right:8px">
        {{ auth.name || '未登录' }}<span v-if="auth.roleLabel"> ({{ auth.roleLabel }})</span>
      </span>
      <button v-if="!conn.connected" class="sm" @click="showConnMgr = true">我的连接</button>
      <button class="sm" @click="toggleTheme" title="切换深浅色主题"><Icon name="moon" :size="16"/> 主题</button>
      <template v-if="conn.connected">
        <button class="sm" @click="toggleTx" :class="{ 'tx-on': ui.transactionMode }" title="事务模式: 开启后增删改进入事务, 可统一提交/回滚">
          事务: {{ ui.transactionMode ? '开' : '关' }}
        </button>
        <template v-if="ui.transactionMode">
          <button class="sm primary" @click="doCommit" title="提交当前标签页所有未提交修改">提交</button>
          <button class="sm danger" @click="doRollback" title="回滚当前标签页所有未提交修改">回滚</button>
        </template>
      </template>
      <button v-if="auth.isAdmin" class="sm" @click="showUserAdmin = true" title="用户列表/审批自助注册/新建账号/细粒度权限">账号管理</button>
      <button v-if="auth.isAdmin" class="sm" @click="showSessions = true" title="在线用户列表与强制踢下线">在线用户</button>
      <button v-if="auth.isAdmin" class="sm" @click="showSysQuery = true" title="对内置 SQLite 执行只读查询: 系统用户/权限/连接/审计/任务">系统查询</button>
      <button v-if="auth.isAdmin" class="sm" @click="showServerConfig = true" title="编辑 dbmanager.conf: 监听地址/端口/HTTPS/注册/LDAP 等(重启生效)">服务器配置</button>
      <button v-if="auth.isLoggedIn" class="sm" @click="showAuth = true">改密</button>
      <button v-if="!auth.isLoggedIn" class="sm" @click="showAuth = true">登录</button>
      <button v-if="conn.connected" class="sm" @click="logout">断开</button>
      <button v-if="conn.connected" class="sm danger" @click="doShutdown">停止服务</button>
    </div>
  </header>
  <ConnMgrModal v-if="showConnMgr" :show="showConnMgr" @close="showConnMgr = false" />
  <AuthModal v-if="showAuth" :show="showAuth" @done="showAuth = false" />
  <UserAdminModal v-if="showUserAdmin" :show="showUserAdmin" @close="showUserAdmin = false" />
  <SessionModal v-if="showSessions" @close="showSessions = false" />
  <SystemQueryModal v-if="showSysQuery" @close="showSysQuery = false" />
  <ServerConfigModal v-if="showServerConfig" @close="showServerConfig = false" />
  <!-- P1-10: 停服状态遮罩(SPA 内状态, 不清空 DOM) -->
  <div v-if="stopped" class="stopped-mask">
    <div class="stopped-card">
      <h3>服务已停止</h3>
      <p>如要再次使用，请重新运行本程序（python app.py）。</p>
    </div>
  </div>
</template>

<style scoped>
.app-header {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 16px; background: var(--header-bg); color: var(--header-text);
  font-size: 14px; flex-shrink: 0;
}
.app-header h1 { font-size: 16px; font-weight: 600; margin: 0; white-space: nowrap; }
.app-header .db { color: var(--text3); font-size: 12px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* P1-10: 停服状态遮罩 */
.stopped-mask {
  position: fixed; inset: 0; z-index: 9999;
  background: var(--panel, #fff); color: inherit;
  display: flex; align-items: center; justify-content: center;
}
.stopped-card { text-align: center; }
.stopped-card h3 { margin: 0 0 8px; }
.stopped-card p { margin: 0; color: var(--text2, var(--text3)); }
.right { display: flex; align-items: center; gap: 6px; }
button.tx-on { background: #a32d2d; color: #fff; border-color: #a32d2d; }
</style>