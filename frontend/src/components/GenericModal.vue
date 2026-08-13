<script setup lang="ts">
// 通用弹窗(阶段5): 渲染 ui.modal(innerHTML, showModal 注入)
// 修复: 之前 ui.modal 存了 HTML 但无组件渲染 -> 所有 showModal 弹窗(新增行/统计/看全文/ER图等)都不显示
// P0-5 加固: v-html 前过 DOMPurify 白名单净化(script/事件属性/外链一律剔除)。
// CSP 兼容(修复): 后端 script-src 'self' 禁内联事件处理器 -> 弹窗按钮不再用 onclick,
//   改用声明式 data-action / data-call, 由本组件统一事件委托分发:
//   - data-action="close"   -> 关闭弹窗
//   - data-action="remove"  -> 删除最近的行容器(.row2, 查询构建器条件行)
//   - data-call="__xxx"     -> 调用 window.__xxx()(调用方自行挂载)
import { computed, onBeforeUnmount, watch } from 'vue'
import DOMPurify from 'dompurify'
import { useUIStore } from '@/stores/ui'

const ui = useUIStore()
// 默认白名单净化: 内联事件(onclick 等)一律剔除, XSS 面最小化
const safeHtml = computed(() => (ui.modal ? DOMPurify.sanitize(ui.modal) : ''))

// 焦点陷阱(3.6 a11y): 弹窗打开时 Tab/Shift+Tab 在弹窗内循环, 不溢出到页面背景;
// 不自动移入焦点(避免破坏弹窗内 autofocus 意图)
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

function onModalClick(e: MouseEvent) {
  const target = e.target as HTMLElement | null
  const el = target?.closest?.('[data-action], [data-call]') as HTMLElement | null
  if (!el) return
  const action = el.getAttribute('data-action')
  if (action === 'close') { ui.closeModal(); return }
  if (action === 'remove') {
    const row = el.closest('.row2')
    if (row) row.remove()
    else el.remove()
    return
  }
  const call = el.getAttribute('data-call')
  if (call) {
    const fn = (window as unknown as Record<string, unknown>)[call]
    if (typeof fn === 'function') (fn as () => void)()
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="ui.modal" class="g-modal-mask" role="dialog" aria-modal="true"
         aria-label="对话框" @click.self="ui.closeModal()"
         @keydown.esc="ui.closeModal()">
      <div class="g-modal" v-html="safeHtml" @click="onModalClick"></div>
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
.g-modal {
  background: var(--panel, #fff);
  border-radius: 10px;
  width: 680px;
  max-width: 92vw;
  max-height: 86vh;
  overflow: auto;
  padding: 18px 20px;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.2);
}
.g-modal :deep(h3) { margin: 0 0 12px; font-size: 16px; }
.g-modal :deep(.acts) { display: flex; gap: 10px; justify-content: flex-end; margin-top: 16px; }
.g-modal :deep(.field) { margin-bottom: 8px; display: flex; flex-direction: column; gap: 4px; }
.g-modal :deep(.field label) { font-size: 12px; color: var(--text2, var(--text3)); }
.g-modal :deep(input[type="text"]),
.g-modal :deep(input:not([type])),
.g-modal :deep(input[type="number"]),
.g-modal :deep(input[type="search"]),
.g-modal :deep(select) {
  padding: 5px 8px; border: 1px solid var(--border2, var(--border)); border-radius: 5px;
  font-size: 13px; outline: none; background: var(--panel, #fff); color: inherit;
}
.g-modal :deep(.row2) { display: flex; gap: 8px; }
.g-modal :deep(.row2 .field) { flex: 1; }
.g-modal :deep(.empty2) { color: var(--text3, var(--text3)); font-size: 12px; padding: 8px 0; }
.g-modal :deep(pre) { font-family: Consolas, monospace; }
.g-modal :deep(button.sm), .g-modal :deep(button) { padding: 4px 12px; font-size: 12px; }
</style>
