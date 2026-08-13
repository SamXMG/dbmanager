<script setup lang="ts">
// 左侧栏(对齐旧版侧边栏): 我的连接(点击切换) + 面包屑 + 对象树
import { computed } from 'vue'
import ObjectTree from '@/components/ObjectTree.vue'
import { useConnectionStore } from '@/stores/connection'
import { useDatabaseStore } from '@/stores/database'
import { syncTablesFromConnection } from '@/stores/database'
import { useTabStore } from '@/stores/tab'
import { useRouter } from 'vue-router'
import Icon from '@/components/Icon.vue'

const connStore = useConnectionStore()
const dbStore = useDatabaseStore()
const tabStore = useTabStore()
const router = useRouter()

/** 面包屑: 当前选中对象完整路径(库›schema›表, 对齐旧版 treeCrumbs) */
const crumb = computed(() => {
  const cur = tabStore.current
  if (!cur) return ''
  const at = tabStore.activeTab
  const db = (at && at.db && at.db !== cur.s) ? at.db : ''
  return [db, cur.s, cur.t].filter(Boolean).join(' › ')
})

/** 切换连接(旧版 switchConn): 按名直连, 切换后树/状态条刷新 */
async function switchConn(name: string) {
  if (connStore.conn?.name === name) return
  try {
    await connStore.connectAndGo({ name })
    syncTablesFromConnection()
    if (router.currentRoute.value.path !== '/main') router.push('/main')
  } catch (e: any) {
    console.warn('切换连接失败:', e.message)
  }
}
</script>

<template>
  <div class="side-panel">
    <!-- 我的连接(树上方, 对齐旧版连接栏) -->
    <div class="side-conns" v-if="connStore.connList.length">
      <div class="sc-title">我的连接</div>
      <div v-for="c in connStore.connList" :key="c.name" class="sc-item"
           :class="{ cur: connStore.conn?.name === c.name }"
           :title="'切换连接: ' + c.name" @click="switchConn(c.name!)">
        <span class="sc-dot" :class="{ on: connStore.conn?.name === c.name }"></span>
        <span class="sc-nm">{{ c.name }}</span>
        <span class="sc-state" v-if="connStore.conn?.name === c.name">✓</span>
      </div>
    </div>
    <div class="side-crumb" v-if="crumb" :title="crumb"><Icon name="pin" :size="13"/> {{ crumb }}</div>
    <ObjectTree />
  </div>
</template>

<style scoped>
.side-panel { display: flex; flex-direction: column; height: 100%; min-height: 0; border-right: 1px solid var(--border, #e4e7ed); }
.side-conns { border-bottom: 1px solid var(--border, #e4e7ed); padding: 4px 0; max-height: 150px; overflow: auto; flex-shrink: 0; }
.sc-title { padding: 3px 10px; font-size: 11px; color: var(--text3, #86909c); }
.side-crumb { padding: 4px 10px; font-size: 12px; color: var(--primary, #165dff); border-bottom: 1px solid var(--border, #e4e7ed); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex-shrink: 0; }
.sc-item { display: flex; align-items: center; gap: 6px; padding: 3px 10px; cursor: pointer; font-size: 13px; }
.sc-item:hover { background: rgba(128,128,128,0.08); }
.sc-item.cur { background: rgba(22,93,255,0.08); font-weight: 600; }
.sc-dot { width: 8px; height: 8px; border-radius: 50%; background: #999; flex-shrink: 0; }
.sc-dot.on { background: #52c41a; }
.sc-nm { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.sc-state { color: #52c41a; font-size: 12px; flex-shrink: 0; }
</style>
