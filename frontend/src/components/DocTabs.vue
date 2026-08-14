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
.doc-tabs { display: flex; align-items: center; gap: 6px; padding: 6px 10px; border-bottom: 1px solid var(--border); overflow-x: auto; flex-shrink: 0; background: var(--panel2); }
.doctab { display: flex; align-items: center; gap: 6px; padding: 6px 12px; font-size: 13px; cursor: pointer; border: 1px solid var(--border); border-radius: var(--radius); background: var(--panel3); color: var(--text2); white-space: nowrap; transition: background .15s ease, border-color .15s ease, color .15s ease, box-shadow .15s ease; }
.doctab:hover { background: var(--panel2); border-color: var(--border2); color: var(--text); }
.doctab.active { background: var(--panel); border-color: var(--primary); color: var(--primary); font-weight: 600; box-shadow: var(--ring); }
.x { color: var(--text3); font-size: 14px; line-height: 1; padding: 0 2px; border-radius: 4px; }
.x:hover { color: var(--danger-solid); background: var(--danger-bg); }
</style>
