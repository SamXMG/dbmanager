<script setup lang="ts">
// 顶栏: 连接信息/用户/角色/主题切换/事务(真实现: 开关+提交/回滚)/停止服务
import { ref, computed, defineAsyncComponent } from 'vue'
import { tr, getLocale, setLocale } from '@/i18n'
import type { Lang } from '@/i18n'
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

// i18n: 语言选择双向绑定(切换即重渲染所有使用 t() 的文案)
const lang = computed<Lang>({
  get: () => getLocale(),
  set: (v) => setLocale(v),
})

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
    <h1><span class="title-grad">DB Manager</span></h1>
    <span class="db" v-if="conn.connected">{{ info }}</span>
    <div class="right">
      <span v-if="conn.connected" style="font-size:13px;color:var(--header-fg2);margin-right:8px">
        {{ auth.name || tr('header.notLoggedIn') }}<span v-if="auth.roleLabel"> ({{ auth.roleLabel }})</span>
      </span>
      <button v-if="!conn.connected" class="sm" @click="showConnMgr = true">{{ tr('header.myConnections') }}</button>
      <button class="sm" @click="toggleTheme" :title="tr('header.theme')"><Icon name="moon" :size="16"/> {{ tr('header.theme') }}</button>
      <select v-model="lang" class="sm" :title="tr('lang.label')" :aria-label="tr('lang.label')">
        <option value="zh-CN">中文</option>
        <option value="en">English</option>
      </select>
      <template v-if="conn.connected">
        <button class="sm" @click="toggleTx" :class="{ 'tx-on': ui.transactionMode }" :title="tr('header.tx')">
          {{ tr('header.tx') }}: {{ ui.transactionMode ? tr('header.txOn') : tr('header.txOff') }}
        </button>
        <template v-if="ui.transactionMode">
          <button class="sm primary" @click="doCommit" :title="tr('header.commit')">{{ tr('header.commit') }}</button>
          <button class="sm danger" @click="doRollback" :title="tr('header.rollback')">{{ tr('header.rollback') }}</button>
        </template>
      </template>
      <button v-if="auth.isAdmin" class="sm" @click="showUserAdmin = true" :title="tr('header.userAdmin')">{{ tr('header.userAdmin') }}</button>
      <button v-if="auth.isAdmin" class="sm" @click="showSessions = true" :title="tr('header.sessions')">{{ tr('header.sessions') }}</button>
      <button v-if="auth.isAdmin" class="sm" @click="showSysQuery = true" :title="tr('header.sysQuery')">{{ tr('header.sysQuery') }}</button>
      <button v-if="auth.isAdmin" class="sm" @click="showServerConfig = true" :title="tr('header.serverConfig')">{{ tr('header.serverConfig') }}</button>
      <button v-if="auth.isLoggedIn" class="sm" @click="showAuth = true">{{ tr('header.changePwd') }}</button>
      <button v-if="!auth.isLoggedIn" class="sm" @click="showAuth = true">{{ tr('header.login') }}</button>
      <button v-if="conn.connected" class="sm" @click="logout">{{ tr('header.logout') }}</button>
      <button v-if="conn.connected" class="sm danger" @click="doShutdown">{{ tr('header.shutdown') }}</button>
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
      <h3>{{ tr('stopped.title') }}</h3>
      <p>{{ tr('stopped.desc') }}</p>
    </div>
  </div>
</template>

<style scoped>
.app-header {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 16px; background: var(--header-grad); color: var(--header-fg); /* 顶栏背景/文字随主题: 浅色柔和浅蓝灰+深字, 深色渐变+白字 */
  font-size: 14px; flex-shrink: 0;
  border-bottom: 1px solid var(--border);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.18);
  position: relative;
}
/* 品牌徽标: 渐变方块 + DB 首字母 */
.app-header h1 {
  font-size: 16px; font-weight: 700; margin: 0; white-space: nowrap;
  display: inline-flex; align-items: center; gap: 9px; letter-spacing: .2px;
}
.app-header h1::before {
  content: "DB";
  display: inline-grid; place-items: center;
  width: 26px; height: 26px; border-radius: 8px;
  background: var(--brand); color: #fff;
  font-size: 12px; font-weight: 800; letter-spacing: .5px;
  box-shadow: 0 2px 10px rgba(99, 102, 241, 0.5);
}
.app-header h1 .title-grad {
  background: linear-gradient(90deg, #cfe0ff, #e8e2ff);
  -webkit-background-clip: text; background-clip: text; color: transparent;
}
/* 顶栏按钮: 浅色主题深字 / 深色主题白字, 边框+hover 自适应, 不刺眼 */
.sm {
  background: color-mix(in srgb, var(--header-fg) 6%, transparent);
  color: var(--header-fg);
  border: 1px solid var(--border2);
  border-radius: var(--radius, 10px);
  padding: 5px 12px;
  font-size: 13px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
  transition: background .15s var(--ease), border-color .15s var(--ease), transform .08s var(--ease), box-shadow .15s var(--ease);
}
.sm:hover {
  background: color-mix(in srgb, var(--header-fg) 14%, transparent);
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
  transform: translateY(-1px);
}
.sm:active { transform: translateY(0); }
.sm.primary { background: var(--primary-grad); color: #fff; border-color: transparent; box-shadow: var(--glow); }
.sm.primary:hover { filter: brightness(1.06); box-shadow: 0 4px 16px rgba(59, 123, 255, 0.5); }
.sm.danger { color: var(--danger-solid); border-color: var(--danger-solid); }
.sm.danger:hover { background: var(--danger-bg); }
.app-header .db { color: var(--header-fg3); font-size: 12px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
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
button.tx-on { background: var(--danger-solid); color: #fff; border-color: var(--danger-solid); }
button.tx-on:hover { filter: brightness(0.95); }
</style>