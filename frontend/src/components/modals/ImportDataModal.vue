<script setup lang="ts">
// 数据导入向导(取代旧版 tools.ts 的 openImport: HTML 字符串 + window.__impRun 全局函数)。
// 复刻解析(CSV 前端 / XLSX 后端)与列映射逻辑, 改为 Vue 原生组件 + v-model 绑定。
// 注: 由 GenericModal 在共享遮罩内渲染, 本组件只渲染 .g-modal 卡片根, 不自带 Teleport/遮罩。
import { ref } from 'vue'
import { useUIStore } from '@/stores/ui'
import { confirmDanger } from '@/utils/confirm'
import { importData } from '@/api/schema'
import { getColumns, type Column } from '@/api/database'
import { API_BASE, authHeaders } from '@/api/client'
import { errMsg } from '@/utils/err'

const props = defineProps<{ s: string; t: string }>()
const ui = useUIStore()

// 文件输入(用 ref 而非 getElementById/querySelector)
const fileInput = ref<HTMLInputElement | null>(null)

// 导入方式: append 追加插入 / replace 清空后导入
const mode = ref<'append' | 'replace'>('append')
const header = ref<string[]>([])
const rows = ref<string[][]>([])
const columns = ref<Column[]>([])
// 列映射: mapping[i] = 第 i 个源列对应的目标列名(空串表示不导入)
const mapping = ref<string[]>([])
const preview = ref('')
const loading = ref(false)

/** 上传 xlsx 到后端解析(原始二进制, 带鉴权头); 同原 uploadXlsx 本地化 */
async function uploadXlsx(file: File): Promise<{ header: string[]; rows: string[][] }> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/octet-stream',
    ...(await authHeaders()),
  }
  const r = await fetch(API_BASE + '/api/import/xlsx', {
    method: 'POST',
    headers,
    body: await file.arrayBuffer(),
  })
  const d = (await r.json().catch(() => ({}))) as { error?: string; header?: string[]; rows?: string[][] }
  if (d.error) throw new Error(d.error)
  return { header: d.header || [], rows: d.rows || [] }
}

/** 解析 CSV 文本(引号包裹, 逗号分隔); 同原 parseCsvText 本地化 */
function parseCsvText(text: string): string[][] {
  const lines = text
    .replace(/\r\n/g, '\n')
    .replace(/﻿/g, '')
    .split('\n')
    .filter((l) => l.trim() !== '')
  return lines.map((l) => {
    const out: string[] = []
    let cur = ''
    let inQ = false
    for (let i = 0; i < l.length; i++) {
      const ch = l[i]
      if (inQ) {
        if (ch === '"' && l[i + 1] === '"') { cur += '"'; i++ }
        else if (ch === '"') inQ = false
        else cur += ch
      } else if (ch === '"') inQ = true
      else if (ch === ',') { out.push(cur); cur = '' }
      else cur += ch
    }
    out.push(cur)
    return out
  })
}

async function onFileChange(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (!f) return
  loading.value = true
  try {
    let h: string[] = []
    let rs: string[][] = []
    if (/\.xlsx?$/i.test(f.name)) {
      const d = await uploadXlsx(f)
      h = d.header
      rs = d.rows
    } else {
      const parsed = parseCsvText(await f.text())
      h = parsed[0] || []
      rs = parsed.slice(1)
    }
    const cols = await getColumns(props.s, props.t)
    columns.value = cols
    header.value = h
    rows.value = rs
    // 默认按同名映射, 未匹配则留空(不导入)
    mapping.value = h.map((name) => cols.find((c) => c.name === name)?.name || '')
    preview.value = `文件 ${rs.length} 行 × ${h.length} 列 → 目标表 ${cols.length} 列`
  } catch (err) {
    ui.toast('解析失败: ' + errMsg(err), true)
  } finally {
    loading.value = false
  }
}

async function onImport() {
  const f = fileInput.value?.files?.[0]
  if (!f || !mapping.value.length || !header.value.length) {
    ui.toast('请先选择文件并映射列', true)
    return
  }
  loading.value = true
  try {
    // 重新解析文件(避免依赖已丢弃的 rows 引用, 保证与最新映射一致)
    let h: string[] = []
    let rs: string[][] = []
    if (/\.xlsx?$/i.test(f.name)) {
      const d = await uploadXlsx(f)
      h = d.header
      rs = d.rows
    } else {
      const parsed = parseCsvText(await f.text())
      h = parsed[0] || []
      rs = parsed.slice(1)
    }
    const cols = mapping.value
    const data = rs.map((r) => {
      const o: Record<string, unknown> = {}
      h.forEach((_, i) => {
        const cn = cols[i]
        if (cn) o[cn] = r[i] !== undefined && r[i] !== '' ? r[i] : null
      })
      return o
    })
    const ok = await confirmDanger(
      `确认导入 ${data.length} 行到 ${props.s}.${props.t}？`,
      '导入数据',
    )
    if (!ok) return
    const d = (await importData({
      s: props.s,
      t: props.t,
      mode: mode.value,
      columns: mapping.value.filter(Boolean),
      rows: data,
    })) as { affected?: number }
    ui.closeModal()
    ui.toast('已导入 ' + (d.affected ?? 0) + ' 行')
  } catch (err) {
    ui.toast('导入失败: ' + errMsg(err), true)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="g-modal">
    <h3>数据导入 · {{ s }}.{{ t }}</h3>

    <div class="field">
      <label>文件(CSV / XLSX)</label>
      <input ref="fileInput" type="file" accept=".csv,.xlsx,.xls" @change="onFileChange" />
    </div>

    <div class="field">
      <label>导入方式</label>
      <select v-model="mode">
        <option value="append">追加插入</option>
        <option value="replace">清空后导入</option>
      </select>
    </div>

    <div style="max-height:200px;overflow:auto;border:1px solid var(--border);border-radius:6px;padding:6px;margin-top:8px">
      <div v-for="(name, i) in header" :key="i" class="row2" style="margin-bottom:4px;align-items:center">
        <label :title="name"
               style="width:110px;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
          {{ name || '(空列' + i + ')' }}
        </label>
        <select v-model="mapping[i]" style="flex:1">
          <option value="">（不导入）</option>
          <option v-for="c in columns" :key="c.name" :value="c.name">
            {{ c.name }} ({{ c.type || '' }})
          </option>
        </select>
      </div>
      <div v-if="!header.length" class="empty2">选择文件后在此映射列</div>
    </div>

    <div v-if="preview" style="color:var(--text3);font-size:12px;margin-top:6px">{{ preview }}</div>
    <div v-if="loading" class="empty2">处理中…</div>

    <div class="acts">
      <button type="button" @click="ui.closeModal()">取消</button>
      <button class="primary" type="button" @click="onImport">导入</button>
    </div>
  </div>
</template>
