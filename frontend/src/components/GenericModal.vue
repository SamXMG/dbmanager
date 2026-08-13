<script setup lang="ts">
// 通用弹窗(阶段5): 动态渲染 ui.modal.name 对应的注册组件(Vue 原生 <component :is>),
// 取代旧版 ui.showModal(html) 的 HTML 字符串注入模式(无 XSS 面、可维护、主题一致)。
// 遮罩/焦点陷阱/Esc 关闭等 a11y 能力保留; 组件自身负责内容、关闭时调用 ui.closeModal()。
import { computed, onBeforeUnmount, watch } from 'vue'
import { useUIStore } from '@/stores/ui'
import { modalRegistry } from './modals'

const ui = useUIStore()
const comp = computed(() => (ui.modal ? modalRegistry[ui.modal.name] || null : null))
const props = computed(() => ui.modal?.props || {})

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
watch(() => ui.modal, (v) => {
  if (v) document.addEventListener('keydown', trapFocus)
  else document.removeEventListener('keydown', trapFocus)
})
onBeforeUnmount(() => document.removeEventListener('keydown', trapFocus))
</script>

<template>
  <Teleport to="body">
    <div v-if="comp" class="g-modal-mask" role="dialog" aria-modal="true"
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
</style>
