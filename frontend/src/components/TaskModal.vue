<script setup lang="ts">
// 调度任务管理弹窗(P2-2): 定时备份任务列表 + 新建/启停/删除/立即执行
import { onMounted, ref } from 'vue'
import { errMsg } from '@/utils/err'
import { confirmDanger } from '@/utils/confirm'
import { useUIStore } from '@/stores/ui'
import { useConnectionStore } from '@/stores/connection'
import { listTasks, createTask, deleteTask, toggleTask, runTask, type TaskInfo } from '@/api/task'
import type { ConnMeta } from '@/api/connection'

const ui = useUIStore()
const connStore = useConnectionStore()

const tasks = ref<TaskInfo[]>([])
const loading = ref(false)
const conns = ref<ConnMeta[]>([])
// 新建表单
const showForm = ref(false)
const fName = ref('')
const fConn = ref('')
const fMin = ref(60)

async function load() {
  loading.value = true
  try {
    const d = await listTasks()
    tasks.value = d.tasks || []
  } catch (e) { ui.toast('加载失败: ' + errMsg(e), true) }
  finally { loading.value = false }
}
onMounted(async () => {
  try {
    if (!connStore.connList.length) await connStore.refreshConnList()
    conns.value = connStore.connList
  } catch { /* */ }
  await load()
})

function fmtTime(t?: number | null): string {
  if (!t) return '-'
  const d = new Date(t * 1000)
  return d.toLocaleString('zh-CN', { hour12: false })
}

async function onCreate() {
  if (!fName.value.trim() || !fConn.value) { ui.toast('请填写任务名并选择连接', true); return }
  try {
    await createTask({ name: fName.value.trim(), conn_name: fConn.value, interval_min: fMin.value })
    ui.toast('已创建任务')
    showForm.value = false
    fName.value = ''
    await load()
  } catch (e) { ui.toast('创建失败: ' + errMsg(e), true) }
}
async function onToggle(t: TaskInfo) {
  try { await toggleTask(t.id, !t.enabled); await load() }
  catch (e) { ui.toast('操作失败: ' + errMsg(e), true) }
}
async function onRun(t: TaskInfo) {
  if (!await confirmDanger(`确认立即执行任务「${t.name}」备份？`)) return
  try {
    const d = await runTask(t.id)
    if (d.error) ui.toast('执行失败: ' + d.error, true)
    else ui.toast('备份完成: ' + (d.file || ''))
    await load()
  } catch (e) { ui.toast('执行失败: ' + errMsg(e), true) }
}
async function onDelete(t: TaskInfo) {
  if (!await confirmDanger(`确认删除任务「${t.name}」？`)) return
  try { await deleteTask(t.id); await load() }
  catch (e) { ui.toast('删除失败: ' + errMsg(e), true) }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="ui.showTasks" class="tk-mask" @click.self="ui.showTasks = false">
      <div class="tk-modal">
        <div class="tk-head">
          <h3>调度任务(定时备份)</h3>
          <button class="primary sm" @click="ui.showTasks = false">关闭</button>
        </div>
        <div class="tk-tip">后台线程每 15s 检查一次, 到点自动备份所选连接整库 SQL 到 backups/ 目录</div>

        <!-- 新建 -->
        <div class="tk-form" v-if="showForm">
          <div class="row2">
            <div class="field"><label>任务名</label><input v-model="fName" placeholder="如 每日备份" /></div>
            <div class="field"><label>连接</label>
              <select v-model="fConn">
                <option value="" disabled>选择已保存连接</option>
                <option v-for="c in conns" :key="c.name" :value="c.name">{{ c.name }} ({{ c.db_type }})</option>
              </select>
            </div>
          </div>
          <div class="row2">
            <div class="field"><label>间隔(分钟)</label><input v-model.number="fMin" type="number" min="1" /></div>
            <div class="field acts2"><button class="sm" @click="showForm = false">取消</button><button class="sm primary" @click="onCreate">创建</button></div>
          </div>
        </div>

        <div class="tk-list">
          <div v-if="!tasks.length && !loading" class="empty2">暂无任务</div>
          <div v-for="t in tasks" :key="t.id" class="tk-item">
            <span class="tk-main">
              <b>{{ t.name }}</b>
              <span class="tk-sub">{{ t.conn_name }} · 每 {{ t.interval_min }} 分钟 · {{ t.action }}</span>
              <span class="tk-sub">上次: {{ fmtTime(t.last_run) }} ({{ t.last_result || '-' }}) · 下次: {{ fmtTime(t.next_run) }}</span>
            </span>
            <span class="tk-state" :class="{ on: t.enabled }">{{ t.enabled ? '运行中' : '已停' }}</span>
            <button class="sm" @click="onRun(t)" title="立即执行一次备份">▶ 执行</button>
            <button class="sm" @click="onToggle(t)">{{ t.enabled ? '停用' : '启用' }}</button>
            <button class="sm danger" @click="onDelete(t)">删除</button>
          </div>
          <div v-if="loading" class="empty2">加载中...</div>
        </div>

        <div class="tk-acts">
          <button class="sm primary" @click="showForm = !showForm">{{ showForm ? '收起' : '+ 新建任务' }}</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.tk-mask { position: fixed; inset: 0; z-index: 9100; background: rgba(0,0,0,0.45); display: flex; align-items: center; justify-content: center; padding: 16px; }
.tk-modal { background: var(--panel, #fff); border-radius: 10px; width: 680px; max-width: 94vw; max-height: 86vh; display: flex; flex-direction: column; padding: 16px 20px 20px; box-shadow: 0 8px 30px rgba(0,0,0,0.2); }
.tk-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.tk-head h3 { margin: 0; font-size: 15px; }
.tk-tip { font-size: 12px; color: var(--text2, #86909c); margin-bottom: 10px; }
.tk-form { border: 1px solid var(--border, #e4e7ed); border-radius: 8px; padding: 10px; margin-bottom: 10px; }
.row2 { display: flex; gap: 8px; margin-bottom: 8px; }
.row2 .field { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.field label { font-size: 12px; color: var(--text2, #86909c); }
.field input, .field select { padding: 5px 8px; border: 1px solid var(--border2, #e5e6eb); border-radius: 5px; font-size: 13px; background: var(--panel, #fff); color: inherit; }
.acts2 { flex-direction: row !important; align-items: flex-end; gap: 6px !important; }
.tk-list { flex: 1; min-height: 0; overflow: auto; display: flex; flex-direction: column; gap: 6px; }
.tk-item { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border: 1px solid var(--border, #e4e7ed); border-radius: 8px; }
.tk-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.tk-sub { font-size: 11px; color: var(--text3, #86909c); }
.tk-state { font-size: 11px; padding: 1px 8px; border-radius: 8px; background: #fcebeb; color: #a32d2d; }
.tk-state.on { background: #e8f7f0; color: #0f6e56; }
.tk-acts { margin-top: 12px; display: flex; justify-content: flex-end; }
.empty2 { color: var(--text3, #999); font-size: 13px; padding: 16px; text-align: center; }
button.sm { padding: 4px 10px; font-size: 12px; }
</style>
