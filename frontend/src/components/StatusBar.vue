<script setup lang="ts">
// 底部状态条(阶段 2): 连接/库/对象计数/用户 + 视图切换(表/SQL)
import { computed } from 'vue'
import { useConnectionStore } from '@/stores/connection'
import { useDatabaseStore } from '@/stores/database'
import { useTabStore } from '@/stores/tab'
import { useAuthStore } from '@/stores/auth'
import { useUIStore } from '@/stores/ui'
import Icon from '@/components/Icon.vue'

const connStore = useConnectionStore()
const dbStore = useDatabaseStore()
const tabStore = useTabStore()
const authStore = useAuthStore()
const ui = useUIStore()

const curTableLabel = computed(() => {
  const cur = tabStore.current
  if (!cur) return ''
  const tab = tabStore.activeTab
  return (tab && tab.db && tab.db !== cur.s ? tab.db + '.' : '') + (cur.s ? cur.s + '.' : '') + cur.t
})

const counts = computed(() => {
  let t = 0, v = 0
  dbStore.tables.forEach(x => x.type === 'View' ? v++ : t++)
  return `表 ${t} · 视图 ${v} · 函数 ${dbStore.routines.length || 0}`
})
</script>

<template>
  <div class="status-bar" v-if="connStore.connected">
    <span class="st-item"><Icon name="link" :size="13"/> {{ connStore.conn?.name || connStore.conn?.server || '-' }}</span>
    <span class="st-item"><Icon name="database" :size="13"/> {{ dbStore.curDb || connStore.conn?.database || '全部库' }}</span>
    <span class="st-item obj">{{ curTableLabel || counts }}</span>
    <span class="st-spacer"></span>
    <span class="st-item"><Icon name="user" :size="13"/> {{ authStore.isLoggedIn ? authStore.name + (authStore.roleLabel ? ' · ' + authStore.roleLabel : '') : '未登录' }}</span>
    <button class="st-btn" :class="{ active: ui.view === 'browse' }" @click="ui.switchView('browse')" title="数据浏览">表</button>
    <button class="st-btn" :class="{ active: ui.view === 'sql' }" @click="ui.switchView('sql')" title="SQL 工作台">SQL</button>
  </div>
</template>

<style scoped>
.status-bar { display: flex; align-items: center; gap: 14px; padding: 5px 12px; border-top: 1px solid var(--border); font-size: 12px; color: var(--text2, var(--text3)); flex-shrink: 0; }
.st-item.obj { font-weight: 500; }
.st-spacer { flex: 1; }
.st-btn { padding: 3px 12px; font-size: 12px; border: 1px solid var(--border); background: var(--panel3); border-radius: var(--radius); cursor: pointer; color: var(--text2, var(--text3)); transition: background .15s ease, border-color .15s ease, color .15s ease; }
.st-btn:hover { border-color: var(--primary); color: var(--primary); }
.st-btn.active { background: var(--primary); border-color: var(--primary); color: #fff; }
</style>
