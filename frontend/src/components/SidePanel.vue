<script setup lang="ts">
// 左侧栏(对齐旧版侧边栏): 我的连接(点击切换) + 面包屑 + 对象树
import { computed } from 'vue'
import { errMsg } from '@/utils/err'
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
  } catch (e: unknown) {
    console.warn('切换连接失败:', errMsg(e))
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
.side-panel { display: flex; flex-direction: column; height: 100%; min-height: 0; border-right: 1px solid var(--border); }
.side-conns { border-bottom: 1px solid var(--border); padding: 8px 0; max-height: 170px; overflow: auto; flex-shrink: 0; }
.sc-title { padding: 2px 12px 6px; font-size: 11px; color: var(--text3); font-weight: 600; letter-spacing: .03em; }
.side-crumb { padding: 5px 10px; margin: 4px 8px 8px; font-size: 12px; color: var(--primary); background: var(--primary-bg); border-radius: var(--radius); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex-shrink: 0; }
.sc-item { display: flex; align-items: center; gap: 8px; margin: 2px 8px; padding: 7px 10px; cursor: pointer; font-size: 13px; border: 1px solid transparent; border-radius: var(--radius); transition: background .15s ease, border-color .15s ease, color .15s ease; }
.sc-item:hover { background: var(--panel2); }
.sc-item.cur { background: var(--primary-bg); border-color: var(--primary); color: var(--primary); font-weight: 600; }
.sc-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text3); flex-shrink: 0; }
.sc-dot.on { background: var(--success); }
.sc-nm { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.sc-state { color: var(--success); font-size: 12px; flex-shrink: 0; }
</style>
