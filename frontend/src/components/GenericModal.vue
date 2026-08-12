<script setup lang="ts">
// 通用弹窗(阶段5): 渲染 ui.modal(innerHTML, showModal 注入)
// 修复: 之前 ui.modal 存了 HTML 但无组件渲染 -> 所有 showModal 弹窗(新增行/统计/看全文/ER图等)都不显示
// 注意: 调用方注入 HTML 时必须自行 esc 用户数据(对齐旧版 showModal 约定)
import { useUIStore } from '@/stores/ui'

const ui = useUIStore()
</script>

<template>
  <Teleport to="body">
    <div v-if="ui.modal" class="g-modal-mask" @click.self="ui.closeModal()">
      <div class="g-modal" v-html="ui.modal"></div>
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
.g-modal :deep(.field label) { font-size: 12px; color: var(--text2, #86909c); }
.g-modal :deep(input[type="text"]),
.g-modal :deep(input:not([type])),
.g-modal :deep(input[type="number"]),
.g-modal :deep(input[type="search"]),
.g-modal :deep(select) {
  padding: 5px 8px; border: 1px solid var(--border2, #e5e6eb); border-radius: 5px;
  font-size: 13px; outline: none; background: var(--panel, #fff); color: inherit;
}
.g-modal :deep(.row2) { display: flex; gap: 8px; }
.g-modal :deep(.row2 .field) { flex: 1; }
.g-modal :deep(.empty2) { color: var(--text3, #999); font-size: 12px; padding: 8px 0; }
.g-modal :deep(pre) { font-family: Consolas, monospace; }
.g-modal :deep(button.sm), .g-modal :deep(button) { padding: 4px 12px; font-size: 12px; }
</style>
