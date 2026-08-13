<script setup lang="ts">
// 单元格详情弹窗(取代旧版单元格双击放大查看)。
// <pre> 展示完整单元格文本, 提供复制按钮(navigator.clipboard)。
// 由 GenericModal 在共享遮罩内渲染, 本组件只渲染 .g-modal 卡片根。
import { useUIStore } from '@/stores/ui'

const props = defineProps<{
  col: string
  text: string
}>()

const ui = useUIStore()

async function copy() {
  try {
    await navigator.clipboard.writeText(props.text)
    ui.toast('已复制')
  } catch {
    ui.toast('复制失败', true)
  }
}
</script>

<template>
  <div class="g-modal" style="width: 560px">
    <h3>单元格内容 · {{ col }}</h3>
    <pre class="cell-pre">{{ text }}</pre>
    <div class="acts">
      <button type="button" @click="ui.closeModal()">关闭</button>
      <button class="primary" type="button" @click="copy">复制</button>
    </div>
  </div>
</template>

<style scoped>
.cell-pre {
  margin: 8px 0; padding: 10px; max-height: 56vh; overflow: auto;
  background: var(--panel2, #f6f7f9); border: 1px solid var(--border); border-radius: 6px;
  font-family: Consolas, monospace; font-size: 12px; line-height: 1.5;
  white-space: pre-wrap; word-break: break-all; color: var(--text);
}
</style>
