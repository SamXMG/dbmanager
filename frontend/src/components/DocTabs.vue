<script setup lang="ts">
// 多文档标签栏(阶段 2): 显示打开的库.表 标签, 点击切换/×关闭
import { useTabStore, type Tab } from '@/stores/tab'

const tabStore = useTabStore()

function tabLabel(t: Tab): string {
  if (t.db && t.db !== t.s) return t.db + '.' + (t.s ? t.s + '.' : '') + t.t
  return (t.s ? t.s + '.' : '') + t.t
}
</script>

<template>
  <div class="doc-tabs" v-if="tabStore.tabs.length">
    <div v-for="t in tabStore.tabs" :key="t.id"
         class="doctab" :class="{ active: t.id === tabStore.activeId }"
         @click="tabStore.activateTab(t.id)">
      <span class="nm">{{ tabLabel(t) }}</span>
      <span class="x" @click.stop="tabStore.closeTab(t.id)">×</span>
    </div>
  </div>
</template>

<style scoped>
.doc-tabs { display: flex; align-items: center; gap: 2px; padding: 0 8px; border-bottom: 1px solid var(--border, var(--border)); overflow-x: auto; flex-shrink: 0; }
.doctab { display: flex; align-items: center; gap: 6px; padding: 6px 12px; font-size: 13px; cursor: pointer; border: 1px solid transparent; border-radius: 6px 6px 0 0; white-space: nowrap; }
.doctab:hover { background: rgba(128,128,128,0.08); }
.doctab.active { background: var(--panel, #fff); border-color: var(--border, var(--border)); border-bottom-color: transparent; font-weight: 600; }
.x { color: var(--text3); font-size: 14px; line-height: 1; padding: 0 2px; }
.x:hover { color: #f5222d; }
</style>
