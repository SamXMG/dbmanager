<script setup lang="ts">
// 还原备份(取代旧版 tools.ts 的 openRestore: HTML 字符串 + window.__rsRun 全局函数)。
// 复刻上传 SQL 脚本 -> /api/restore 的危险操作流程, 改为 Vue 原生组件 + confirmDanger 二次确认。
// 注: 由 GenericModal 在共享遮罩内渲染, 本组件只渲染 .g-modal 卡片根, 不自带 Teleport/遮罩。
import { ref } from 'vue'
import { useUIStore } from '@/stores/ui'
import { confirmDanger } from '@/utils/confirm'
import { restore } from '@/api/schema'
import { errMsg } from '@/utils/err'

const ui = useUIStore()
const loading = ref(false)
// 文件输入(用 ref 而非 getElementById/querySelector)
const fileInput = ref<HTMLInputElement | null>(null)

interface RestoreResult {
  executed?: unknown[]
  failed?: unknown[]
}

async function onRestore() {
  const f = fileInput.value?.files?.[0]
  if (!f) {
    ui.toast('请选择 SQL 文件', true)
    return
  }
  const ok = await confirmDanger(
    '确认还原？将执行文件中的全部 SQL(不可撤销)!',
    '还原备份',
  )
  if (!ok) return
  loading.value = true
  try {
    const sql = await f.text()
    const d = (await restore({ sql })) as RestoreResult
    ui.closeModal()
    ui.toast('还原完成: 成功' + (d.executed?.length ?? 0) + ' / 失败' + (d.failed?.length ?? 0))
  } catch (err) {
    ui.toast('还原失败: ' + errMsg(err), true)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="g-modal">
    <h3>还原备份</h3>

    <p style="color:#d4660a;font-size:12px">
      ⚠ 将执行备份脚本中的 CREATE/INSERT(仅 DDL+DML)。建议先备份当前库。
    </p>

    <div class="field">
      <label>SQL 脚本(.sql / .txt)</label>
      <input ref="fileInput" type="file" accept=".sql,.txt" />
    </div>

    <div v-if="loading" class="empty2">还原中…</div>

    <div class="acts">
      <button type="button" @click="ui.closeModal()">取消</button>
      <button class="primary" type="button" @click="onRestore">还原</button>
    </div>
  </div>
</template>
