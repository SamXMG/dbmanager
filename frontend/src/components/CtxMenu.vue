<script setup lang="ts">
// 全局右键菜单(阶段4 完善): 渲染 ui.ctxMenu
// 对齐旧版 js/grid.js showCtxMenu: 贴边翻转 / 分隔线 / danger 红字 / 点击外部·右键·滚动·Esc 关闭
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useUIStore } from '@/stores/ui'

const ui = useUIStore()
const menuEl = ref<HTMLDivElement | null>(null)
const pos = ref({ x: 0, y: 0 })

// 菜单出现后: 计算实际尺寸, 贴边翻转避免溢出视口
watch(() => ui.ctxMenu, async () => {
  if (!ui.ctxMenu) return
  await nextTick()
  const el = menuEl.value
  if (!el) return
  const r = el.getBoundingClientRect()
  pos.value = {
    x: Math.max(4, Math.min(ui.ctxMenu.x, window.innerWidth - r.width - 8)),
    y: Math.max(4, Math.min(ui.ctxMenu.y, window.innerHeight - r.height - 8)),
  }
})

function onItem(it: { fn?: () => void }) {
  ui.closeCtxMenu()
  if (it.fn) it.fn()
}

// ---- 全局关闭: 点击菜单外 / 右键别处 / 滚动 / Esc ----
function onDocMouse(e: MouseEvent) {
  if (menuEl.value && !menuEl.value.contains(e.target as Node)) ui.closeCtxMenu()
}
function onScroll() { ui.closeCtxMenu() }
function onKey(e: KeyboardEvent) { if (e.key === 'Escape') ui.closeCtxMenu() }
function onResize() { ui.closeCtxMenu() }

onMounted(() => {
  document.addEventListener('click', onDocMouse)
  document.addEventListener('contextmenu', onDocMouse)
  window.addEventListener('scroll', onScroll, true)
  window.addEventListener('keydown', onKey)
  window.addEventListener('resize', onResize)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocMouse)
  document.removeEventListener('contextmenu', onDocMouse)
  window.removeEventListener('scroll', onScroll, true)
  window.removeEventListener('keydown', onKey)
  window.removeEventListener('resize', onResize)
})
</script>

<template>
  <Teleport to="body">
    <div v-if="ui.ctxMenu" ref="menuEl" class="ctx-menu" :style="{ left: pos.x + 'px', top: pos.y + 'px' }">
      <template v-for="(it, i) in ui.ctxMenu.items" :key="i">
        <div v-if="it.sep" class="cm-sep"></div>
        <div v-else class="cm-item" :class="{ danger: it.danger }" @click="onItem(it)">{{ it.label }}</div>
      </template>
    </div>
  </Teleport>
</template>

<style scoped>
.ctx-menu {
  position: fixed;
  z-index: 9999;
  min-width: 160px;
  max-width: 260px;
  padding: 4px;
  background: var(--panel, #fff);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.14);
  font-size: 13px;
  color: var(--text);
  user-select: none;
}
.cm-item {
  padding: 6px 12px;
  border-radius: 5px;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cm-item:hover { background: var(--primary-bg, rgba(22, 93, 255, 0.08)); color: var(--primary); }
.cm-item.danger { color: var(--danger-solid); }
.cm-item.danger:hover { background: var(--danger-bg); color: var(--danger-solid); }
.cm-sep { height: 1px; margin: 4px 8px; background: var(--border); }
</style>
