<script setup lang="ts">
// 通用弹窗(阶段5): 动态渲染 ui.modal.name 对应的注册组件(Vue 原生 <component :is>),
// 取代旧版 ui.showModal(html) 的 HTML 字符串注入模式(无 XSS 面、可维护、主题一致)。
// 遮罩/焦点陷阱/Esc 关闭等 a11y 能力保留; 组件自身负责内容、关闭时调用 ui.closeModal()。
import { computed, onBeforeUnmount, watch, nextTick, ref } from 'vue'
import { useUIStore } from '@/stores/ui'
import { modalRegistry } from './modals'

const ui = useUIStore()
const comp = computed(() => (ui.modal ? modalRegistry[ui.modal.name] || null : null))
const props = computed(() => ui.modal?.props || {})

// ---- 弹窗卡片可拖拽位置 + 可缩放大小(单点作用所有 .g-modal, 排除自带 .explain-card) ----
// 拖拽规则: 命中右下角手柄=缩放; 命中标题/空白等非交互区=移动; 命中 button/input/.tbl-scroll 等仍正常交互。
const maskRef = ref<HTMLElement | null>(null)
let cleanupFns: Array<() => void> = []
function enhanceCard() {
  const mask = maskRef.value
  if (!mask) return
  const card = mask.querySelector<HTMLElement>('.g-modal:not(.explain-card)')
  if (!card || card.dataset.dragEnhanced) return
  card.dataset.dragEnhanced = '1'
  const w = Math.min(card.offsetWidth, window.innerWidth - 24)
  const h = Math.min(card.offsetHeight, window.innerHeight * 0.86)
  card.style.position = 'fixed'
  card.style.width = w + 'px'
  card.style.height = h + 'px'
  card.style.maxHeight = 'none'
  card.style.left = Math.max(12, (window.innerWidth - w) / 2) + 'px'
  card.style.top = Math.max(12, (window.innerHeight - h) / 2) + 'px'

  const hint = document.createElement('div')
  hint.className = 'g-modal-drag-hint'
  hint.title = '拖动移动窗口'
  card.appendChild(hint)
  const rz = document.createElement('div')
  rz.className = 'g-modal-resizer'
  rz.title = '拖动调整大小'
  card.appendChild(rz)

  const el = card
  let mode: 'drag' | 'resize' | null = null
  let sx = 0, sy = 0, ol = 0, ot = 0, ow = 0, oh = 0
  function onDown(e: MouseEvent) {
    const t = e.target as HTMLElement
    if (t.classList.contains('g-modal-resizer')) mode = 'resize'
    else {
      if (t.closest('button,input,textarea,select,a,[contenteditable],.tbl-scroll,.scroll,.no-drag')) return
      mode = 'drag'
    }
    sx = e.clientX; sy = e.clientY
    ol = el.offsetLeft; ot = el.offsetTop; ow = el.offsetWidth; oh = el.offsetHeight
    document.body.style.userSelect = 'none'
    e.preventDefault()
  }
  function onMove(e: MouseEvent) {
    if (!mode) return
    if (mode === 'drag') {
      const nl = Math.max(6, Math.min(ol + e.clientX - sx, window.innerWidth - el.offsetWidth - 6))
      const nt = Math.max(6, Math.min(ot + e.clientY - sy, window.innerHeight - el.offsetHeight - 6))
      el.style.left = nl + 'px'; el.style.top = nt + 'px'
    } else {
      const nw = Math.max(320, Math.min(ow + e.clientX - sx, window.innerWidth - 24))
      const nh = Math.max(180, Math.min(oh + e.clientY - sy, window.innerHeight - 24))
      el.style.width = nw + 'px'; el.style.height = nh + 'px'
    }
  }
  function onUp() { mode = null; document.body.style.userSelect = '' }
  el.addEventListener('mousedown', onDown)
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
  cleanupFns.push(() => {
    el.removeEventListener('mousedown', onDown)
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
    hint.remove(); rz.remove(); delete el.dataset.dragEnhanced
  })
}
function teardownCard() {
  cleanupFns.forEach(fn => fn())
  cleanupFns = []
}

// 焦点陷阱(3.6 a11y): 弹窗打开时 Tab/Shift+Tab 在弹窗内循环, 不溢出到页面背景
function trapFocus(e: KeyboardEvent) {
  if (e.key !== 'Tab') return
  const mask = document.querySelector('.g-modal-mask')
  if (!mask) return
  const focusables = [...mask.querySelectorAll<HTMLElement>(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')]
    .filter(el => !el.hasAttribute('disabled'))
  if (!focusables.length) return
  const first = focusables[0]
  const last = focusables[focusables.length - 1]
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
}
watch(() => ui.modal, async (v) => {
  if (v) {
    document.addEventListener('keydown', trapFocus)
    await nextTick()
    requestAnimationFrame(() => enhanceCard())
  } else {
    document.removeEventListener('keydown', trapFocus)
    teardownCard()
  }
})
onBeforeUnmount(() => { document.removeEventListener('keydown', trapFocus); teardownCard() })
</script>

<template>
  <Teleport to="body">
    <div v-if="comp" class="g-modal-mask" role="dialog" aria-modal="true" ref="maskRef"
         aria-label="对话框" @click.self="ui.closeModal()"
         @keydown.esc="ui.closeModal()">
      <component :is="comp" v-bind="props" />
    </div>
  </Teleport>
</template>

<style scoped>
.g-modal-mask {
  position: fixed;
  inset: 0;
  z-index: 9000;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}
/* 注册组件内部用 .g-modal 作为卡片容器(若组件自带 mask 则用其自身) */
.g-modal-mask :deep(.g-modal) {
  background: var(--panel, #fff);
  border-radius: 10px;
  width: 680px;
  max-width: 92vw;
  max-height: 86vh;
  overflow: auto;
  padding: 18px 20px;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.2);
  color: var(--text);
}
/* 拖拽提示条(顶部居中) + 缩放手柄(右下角): 由 enhanceCard 运行时注入 */
.g-modal-mask :deep(.g-modal-drag-hint) {
  position: absolute;
  top: 3px;
  left: 50%;
  transform: translateX(-50%);
  width: 40px;
  height: 8px;
  border-radius: 4px;
  cursor: move;
  background: var(--border);
  opacity: 0.45;
  z-index: 3;
}
.g-modal-mask :deep(.g-modal-drag-hint:hover) { opacity: 0.8; }
.g-modal-mask :deep(.g-modal-resizer) {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 18px;
  height: 18px;
  cursor: nwse-resize;
  z-index: 3;
  background: linear-gradient(135deg, transparent 0 50%, var(--text3) 50% 56%, transparent 56% 68%, var(--text3) 68% 74%, transparent 74% 100%);
}
</style>
