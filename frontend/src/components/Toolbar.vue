<script setup lang="ts">
// 数据浏览工具栏: 刷新/新增行/删除选中/粘贴插入/复制选中/导出 CSV(整表·选中)/统计/Redis 键操作
// (对齐旧版工具栏; Redis 连接显示 新建键/TTL/删除键)
import { computed } from 'vue'
import { useGridStore } from '@/stores/grid'
import { useTabStore } from '@/stores/tab'
import { useAuthStore } from '@/stores/auth'
import { API_BASE, authState } from '@/api/client'
import { useUIStore } from '@/stores/ui'
import { useConnectionStore } from '@/stores/connection'
import { importData, alterTable } from '@/api/schema'

const grid = useGridStore()
const tab = useTabStore()
const auth = useAuthStore()
const ui = useUIStore()
const connStore = useConnectionStore()

const hasTable = computed(() => !!tab.current)
const canWrite = computed(() => auth.canWrite)
const isRedis = computed(() => connStore.conn?.db_type === 'redis')

/** 刷新当前页数据 */
function refresh() { grid.loadData() }

/** 流式加载全部(上限 5 万行, 虚拟滚动渲染) */
async function loadAll() {
  const cur = tab.current
  if (!cur) return
  if (!confirm(`确认加载 ${cur.s}.${cur.t} 全部数据？(上限 5 万行, 可能较慢)`)) return
  const n = await grid.loadAll()
  ui.toast('已加载 ' + n + ' 行')
}

/** 新增行(简版: 弹窗收集列值, 空值用 null) */
async function addRow() {
  const cur = tab.current
  if (!cur) return
  const meta = tab.currentMeta
  const lines = (meta?.columns || []).map(c => {
    return `<div class="row2" style="margin-bottom:6px"><label style="width:120px;flex-shrink:0">${c.name}</label><input id="add_${c.name}" placeholder="${(c.type || '')}" style="flex:1"></div>`
  }).join('')
  ui.showModal(`<h3>新增行 · ${cur.s}.${cur.t}</h3>${lines}<div class="acts"><button onclick="closeModal()">取消</button><button class="primary" id="addOk">插入</button></div>`)
  setTimeout(() => {
    const ok = document.getElementById('addOk')
    if (ok) ok.onclick = async () => {
      const values: Record<string, unknown> = {}
      ;(meta?.columns || []).forEach(c => {
        const el = document.getElementById('add_' + c.name) as HTMLInputElement
        if (el && el.value !== '') values[c.name] = el.value
      })
      const ok2 = await grid.insert(values)
      ui.closeModal()
      ui.toast(ok2 ? '已插入' : '插入失败', !ok2)
    }
  }, 0)
}

/** 删除选中行 */
async function deleteRows() {
  if (!grid.selectedRows.size) { ui.toast('请先选中行', true); return }
  if (!confirm(`确认删除选中的 ${grid.selectedRows.size} 行？`)) return
  const ok = await grid.deleteSelected()
  ui.toast(ok ? '已删除' : '删除失败', !ok)
}

/** 导出 CSV(走后端下载) */
function exportCsv() {
  const cur = tab.current
  if (!cur) return
  const where = grid.buildWhere()
  const url = `${API_BASE}/api/export?s=${encodeURIComponent(cur.s)}&t=${encodeURIComponent(cur.t)}&where=${encodeURIComponent(where)}&fmt=csv`
  window.open(url, '_blank')
}

/** 复制选中行(TSV 带表头) */
async function copySelected() {
  const idxs = [...grid.selectedRows].sort((a, b) => a - b)
  if (!idxs.length) { ui.toast('请先选中行', true); return }
  const rows = idxs.map(i => grid.rows[i]).filter(Boolean)
  const lines = [grid.columns.map(c => c.name).join('\t'),
    ...rows.map(r => grid.columns.map(c => fmtV(r[c.name])).join('\t'))]
  try {
    await navigator.clipboard.writeText(lines.join('\n'))
    ui.toast('已复制 ' + rows.length + ' 行')
  } catch { ui.toast('复制失败', true) }
}
function fmtV(v: unknown): string {
  if (v === null || v === undefined) return ''
  return String(v)
}

/** 导出选中行 CSV(前端生成带 BOM) */
function exportSelected() {
  const idxs = [...grid.selectedRows].sort((a, b) => a - b)
  if (!idxs.length) { ui.toast('请先选中行', true); return }
  const rows = idxs.map(i => grid.rows[i]).filter(Boolean)
  let csv = '\ufeff' + grid.columns.map(c => '"' + String(c.name).replace(/"/g, '""') + '"').join(',') + '\r\n'
  rows.forEach(r => {
    csv += grid.columns.map(c => {
      const v = r[c.name]
      if (v == null) return ''
      return '"' + String(v).replace(/"/g, '""') + '"'
    }).join(',') + '\r\n'
  })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
  a.download = 'selected_rows.csv'
  document.body.appendChild(a); a.click(); a.remove()
  URL.revokeObjectURL(a.href)
  ui.toast('已导出选中 ' + rows.length + ' 行')
}

/** Excel/CSV 批量粘贴插入: 粘贴到弹窗 -> 解析 TSV/CSV -> 列映射 -> /api/import(事务感知) */
function pasteInsert() {
  const cur = tab.current
  const meta = tab.currentMeta
  if (!cur || !meta) return
  ui.showModal(`<h3>批量粘贴插入 · ${cur.s}.${cur.t}</h3>
    <p style="color:#86909c;font-size:12px;margin:4px 0 8px">从 Excel/表格复制数据后粘贴到下方(第一行为列名, 或直接数据), 按列顺序映射</p>
    <textarea id="piText" style="width:100%;height:140px;box-sizing:border-box;padding:8px;font-family:Consolas,monospace;font-size:12px" placeholder="粘贴 Excel 复制的单元格..."></textarea>
    <div class="acts"><button onclick="closeModal()">取消</button><button class="primary" id="piGo">导入 {{ meta.columns.length }} 列</button></div>`)
  setTimeout(() => {
    const go = document.getElementById('piGo')
    if (go) go.onclick = async () => {
      const raw = (document.getElementById('piText') as HTMLTextAreaElement).value
      if (!raw.trim()) { ui.toast('请先粘贴数据', true); return }
      const rows = parsePaste(raw)
      if (!rows.length) { ui.toast('未解析到数据', true); return }
      const cols = meta.columns.map(c => c.name)
      const mapped = rows.map(r => {
        const o: Record<string, unknown> = {}
        cols.forEach((c, i) => { if (r[i] !== undefined && r[i] !== '') o[c] = r[i] })
        return o
      })
      if (!confirm(`确认插入 ${mapped.length} 行到 ${cur.s}.${cur.t}？`)) return
      try {
        const payload: Record<string, unknown> = { s: cur.s, t: cur.t, columns: cols, rows: mapped }
        if (ui.transactionMode) payload.transaction = true
        const d = await importData(payload)
        ui.closeModal()
        ui.toast('已导入 ' + (d as { affected?: number }).affected + ' 行')
        grid.loadData(1)
      } catch (e) { ui.toast('导入失败: ' + (e as Error).message, true) }
    }
  }, 0)
}
/** 解析粘贴文本: TSV/CSV(引号包裹的逗号值) */
function parsePaste(raw: string): string[][] {
  const lines = raw.replace(/\r\n/g, '\n').split('\n').filter(l => l.trim() !== '')
  const isTsv = lines[0].includes('\t')
  return lines.map(l => {
    if (isTsv) return l.split('\t')
    // CSV: 处理引号
    const out: string[] = []
    let cur = '', inQ = false
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

/** 列统计(简版: 弹窗选列) */
function showStats() {
  const cur = tab.current
  const meta = tab.currentMeta
  if (!cur || !meta) return
  const opts = (meta.columns || []).map(c => `<option value="${c.name}">${c.name}</option>`).join('')
  ui.showModal(`<h3>列统计 · ${cur.s}.${cur.t}</h3>
    <div class="field"><label>列</label><select id="stCol">${opts}</select></div>
    <div class="acts"><button onclick="closeModal()">取消</button><button class="primary" id="stGo">统计</button></div>`)
  setTimeout(() => {
    const go = document.getElementById('stGo')
    if (go) go.onclick = async () => {
      const col = (document.getElementById('stCol') as HTMLSelectElement).value
      const d = await statsCol(col)
      ui.closeModal()
      if (!d) { ui.toast('统计失败', true); return }
      let rows = `<tr><td>COUNT</td><td>${d.count}</td></tr>
        <tr><td>MIN</td><td>${d.min ?? '-'}</td></tr>
        <tr><td>MAX</td><td>${d.max ?? '-'}</td></tr>`
      if ('sum' in d) rows += `<tr><td>SUM</td><td>${d.sum ?? '-'}</td></tr>`
      if ('avg' in d) rows += `<tr><td>AVG</td><td>${d.avg ?? '-'}</td></tr>`
      ui.showModal(`<h3>统计: ${col}</h3><table class="p-tbl"><tbody>${rows}</tbody></table>
        <div class="acts"><button onclick="closeModal()">关闭</button></div>`)
    }
  }, 0)
}

import { statsColumn } from '@/api/data'
async function statsCol(col: string) {
  const cur = tab.current
  if (!cur) return null
  try { return await statsColumn({ s: cur.s, t: cur.t, col, where: grid.buildWhere() }) }
  catch { return null }
}

// ---- Redis 键操作(对齐旧版 redisNewKey/redisTtl/redisDelKey: 全走 /api/alter) ----
function redisAlter(action: string, payload: Record<string, unknown>) {
  const cur = tab.current
  if (!cur) return Promise.reject(new Error('无当前键'))
  return alterTable({ s: cur.s, t: cur.t, action, payload })
}
function redisNewKey() {
  const cur = tab.current
  if (!cur) return
  ui.showModal(`<h3>新建 Redis 键</h3>
    <div class="field"><label>键名</label><input id="rkName" placeholder="如 user:1001"></div>
    <div class="field"><label>类型</label><select id="rkType">
      <option value="string">String</option><option value="hash">Hash</option>
      <option value="list">List</option><option value="set">Set</option><option value="zset">ZSet</option>
    </select></div>
    <div class="field"><label>初始值</label><input id="rkVal" placeholder="String 为值; Hash/List/Set 为单个元素; ZSet 为成员(score=0)"></div>
    <div class="field"><label>过期秒数(留空=永久)</label><input id="rkTtl" type="number" placeholder="如 3600"></div>
    <div class="acts"><button onclick="closeModal()">取消</button><button class="primary" id="rkGo">创建</button></div>`)
  setTimeout(() => {
    const go = document.getElementById('rkGo')
    if (go) go.onclick = async () => {
      const name = (document.getElementById('rkName') as HTMLInputElement).value.trim()
      if (!name) { ui.toast('请填写键名', true); return }
      const type = (document.getElementById('rkType') as HTMLSelectElement).value
      const value = (document.getElementById('rkVal') as HTMLInputElement).value
      const ttl = (document.getElementById('rkTtl') as HTMLInputElement).value
      try {
        await redisAlter('create', { type, value, ttl: ttl ? parseInt(ttl, 10) : 0 })
        ui.closeModal()
        ui.toast('已创建键 ' + name)
      } catch (e) { ui.toast('创建失败: ' + (e as Error).message, true) }
    }
  }, 0)
}
async function redisTtl() {
  const cur = tab.current
  if (!cur) return
  let now = '(获取失败)'
  try {
    const d = await redisAlter('set_ttl', {}) as { ttl?: number }
    now = d.ttl != null && d.ttl > 0 ? d.ttl + ' 秒' : '永久(-1)'
  } catch { /* */ }
  ui.showModal(`<h3>键 ${cur.t} 的 TTL</h3>
    <div class="field"><label>当前过期时间</label><div style="color:var(--text2)">${now}</div></div>
    <div class="field"><label>新过期秒数(0=永久)</label><input id="rtTtl" type="number" placeholder="如 3600"></div>
    <div class="acts"><button onclick="closeModal()">取消</button><button class="primary" id="rtGo">应用</button></div>`)
  setTimeout(() => {
    const go = document.getElementById('rtGo')
    if (go) go.onclick = async () => {
      const v = (document.getElementById('rtTtl') as HTMLInputElement).value
      if (v === '') { ui.toast('请输入过期秒数(0=永久)', true); return }
      try {
        await redisAlter('set_ttl', { ttl: parseInt(v, 10) })
        ui.closeModal()
        ui.toast('TTL 已更新')
      } catch (e) { ui.toast('设置失败: ' + (e as Error).message, true) }
    }
  }, 0)
}
async function redisDelKey() {
  const cur = tab.current
  if (!cur) return
  if (!confirm(`⚠️ 将删除整个键 "${cur.t}"，该键下所有数据不可恢复！\n确定继续吗？`)) return
  try {
    await redisAlter('drop', {})
    ui.toast('已删除键 ' + cur.t)
    tab.closeTab(tab.activeId ?? -1)
  } catch (e) { ui.toast('删除失败: ' + (e as Error).message, true) }
}
</script>

<template>
  <div class="toolbar" v-if="hasTable">
    <button class="sm" @click="refresh" title="刷新当前数据 (Ctrl+R)">刷新</button>
    <button class="sm" @click="loadAll" title="流式加载全部数据(上限 5 万行, 虚拟滚动)">加载全部</button>
    <button v-if="canWrite" class="sm" @click="addRow">新增行</button>
    <button v-if="canWrite" class="sm" @click="pasteInsert" title="从 Excel/CSV 粘贴批量插入">粘贴插入</button>
    <button v-if="canWrite" class="sm danger" @click="deleteRows"
            :disabled="!grid.selectedRows.size">删除选中{{ grid.selectedRows.size ? `(${grid.selectedRows.size})` : '' }}</button>
    <button class="sm" @click="copySelected" :disabled="!grid.selectedRows.size"
            title="复制选中行(TSV 带表头)">复制选中</button>
    <button class="sm" @click="exportSelected" :disabled="!grid.selectedRows.size"
            title="导出选中行为 CSV">导出选中</button>
    <button class="sm" @click="exportCsv">导出 CSV</button>
    <button class="sm" @click="showStats">统计</button>
    <template v-if="isRedis">
      <button v-if="canWrite" class="sm" @click="redisNewKey" title="新建 Redis 键">新建键</button>
      <button v-if="canWrite" class="sm" @click="redisTtl" title="设置键过期时间">TTL</button>
      <button v-if="canWrite" class="sm danger" @click="redisDelKey" title="删除整个键">删除键</button>
    </template>
    <span class="spacer"></span>
    <span class="count" v-if="grid.total">共 {{ grid.total }} 行 · 第 {{ grid.page }} 页</span>
  </div>
</template>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 6px; padding: 6px 10px; border-bottom: 1px solid var(--border, #e4e7ed); flex-shrink: 0; }
.spacer { flex: 1; }
.count { font-size: 12px; color: var(--text2, #86909c); }
button.sm { padding: 4px 10px; font-size: 12px; }
</style>
