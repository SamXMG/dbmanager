<script setup lang="ts">
// 确认弹窗(危险操作二次确认): 取代旧 confirm.ts 的 ui.showModal 注入。
// 由 confirmDanger() 通过 ui.openModal('ConfirmModal', { resolve }) 打开, resolve 返回用户选择。
import { useUIStore } from '@/stores/ui'

const ui = useUIStore()
const props = defineProps<{
  title?: string
  message: string
  danger?: boolean
  resolve: (ok: boolean) => void
}>()

function ok() { props.resolve(true); ui.closeModal() }
function cancel() { props.resolve(false); ui.closeModal() }
</script>

<template>
  <div class="g-modal" style="width: 460px">
    <h3>{{ title || '请确认' }}</h3>
    <p class="cf-msg">{{ message }}</p>
    <div class="acts">
      <button @click="cancel">取消</button>
      <button :class="danger ? 'primary danger' : 'primary'" @click="ok">{{ danger ? '确认执行' : '确定' }}</button>
    </div>
  </div>
</template>

<style scoped>
.cf-msg { white-space: pre-wrap; line-height: 1.6; color: var(--text); font-size: 13px; margin: 4px 0 8px; }
</style>
