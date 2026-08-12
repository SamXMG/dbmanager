<script setup lang="ts">
// 主界面布局: 侧栏(树) + 文档标签 + 内容区(数据浏览 / SQL 工作台) + 右侧属性面板 + 状态条
// 顶栏已提到 App.vue 全局(连接页/主界面共用); 视图切换走 ui.view(状态条「表|SQL」按钮)
// 全局快捷键(阶段5): F5/Ctrl+R 刷新, Ctrl+W 关 tab, Ctrl+Tab 切 tab, Ctrl+D 复制选中行
import { onBeforeUnmount, onMounted } from 'vue'
import SidePanel from '@/components/SidePanel.vue'
import DocTabs from '@/components/DocTabs.vue'
import Toolbar from '@/components/Toolbar.vue'
import DataGrid from '@/components/DataGrid.vue'
import PropsPanel from '@/components/PropsPanel.vue'
import StatusBar from '@/components/StatusBar.vue'
import SqlWorkbench from '@/components/SqlWorkbench.vue'
import { useUIStore } from '@/stores/ui'
import { useTabStore } from '@/stores/tab'
import { useGridStore } from '@/stores/grid'

const ui = useUIStore()
const tabStore = useTabStore()
const grid = useGridStore()

function onKey(e: KeyboardEvent) {
  const tag = (e.target as HTMLElement)?.tagName?.toLowerCase() || ''
  const inInput = tag === 'input' || tag === 'textarea' || tag === 'select'
  // 编辑器/输入框内快捷键由各组件处理, 这里只拦截未在输入态的组合键
  if (e.key === 'F5' && !inInput) {
    e.preventDefault()
    if (ui.view === 'browse' && tabStore.current) grid.loadData(1)
    return
  }
  const ctrl = e.ctrlKey || e.metaKey
  if (!ctrl) return
  if (e.key === 'r' && !inInput) {
    e.preventDefault()
    if (ui.view === 'browse' && tabStore.current) grid.loadData(1)
  } else if (e.key.toLowerCase() === 'w' && !inInput && !e.shiftKey) {
    e.preventDefault()
    if (tabStore.activeId != null) tabStore.closeTab(tabStore.activeId)
  } else if (e.key === 'Tab') {
    e.preventDefault()
    tabStore.switchNextTab()
  } else if (e.key.toLowerCase() === 'd' && !inInput && ui.view === 'browse') {
    e.preventDefault()
    copySelectedRows()
  }
}
async function copySelectedRows() {
  const idxs = [...grid.selectedRows].sort((a, b) => a - b)
  if (!idxs.length) { ui.toast('请先选中行', true); return }
  const rows = idxs.map(i => grid.rows[i]).filter(Boolean)
  const lines = [grid.columns.map(c => c.name).join('\t'),
    ...rows.map(r => grid.columns.map(c => String(r[c.name] ?? '')).join('\t'))]
  try { await navigator.clipboard.writeText(lines.join('\n')); ui.toast('已复制 ' + rows.length + ' 行') }
  catch { ui.toast('复制失败', true) }
}

onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="main-layout">
    <div class="main">
      <SidePanel class="side" />
      <div class="content">
        <!-- 数据浏览: 文档标签 + 工具栏 + 数据网格 + 属性面板 -->
        <template v-if="ui.view === 'browse'">
          <DocTabs />
          <Toolbar />
          <div class="browse-body">
            <DataGrid class="grid-area" />
            <PropsPanel />
          </div>
        </template>
        <!-- SQL 工作台(阶段 4 完整) -->
        <SqlWorkbench v-else />
      </div>
    </div>
    <StatusBar />
  </div>
</template>

<style scoped>
.main-layout { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.main { display: flex; flex: 1; min-height: 0; }
.side { width: 260px; flex-shrink: 0; }
.content { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.browse-body { flex: 1; display: flex; min-height: 0; }
.grid-area { flex: 1; min-width: 0; }
</style>
