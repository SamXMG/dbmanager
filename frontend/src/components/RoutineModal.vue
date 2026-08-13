<script setup lang="ts">
// 存储过程/函数/触发器编辑器(阶段5 批3): 打开源码 -> 编辑 -> 保存重建/执行(参数收集)/删除
// 对齐旧版 procBar + openRoutine
import { computed, ref, watch } from 'vue'
import { errMsg } from '@/utils/err'
import { confirmDanger } from '@/utils/confirm'
import { useUIStore } from '@/stores/ui'
import { getRoutineSource, getRoutineParams } from '@/api/database'
import { saveRoutine, dropRoutine, executeRoutine } from '@/api/routine'
import Icon from '@/components/Icon.vue'

const ui = useUIStore()
const target = computed(() => ui.routine)

const source = ref('')
const loading = ref(false)
const saving = ref(false)
// 参数(执行时收集)
const params = ref<{ name: string; type: string }[]>([])
const paramVals = ref<Record<string, string>>({})
const executing = ref(false)
const execResult = ref('')

const KIND_LABEL: Record<string, string> = { Procedure: '存储过程', Function: '函数', Trigger: '触发器' }

watch(() => ui.routine, async (r) => {
  if (!r) return
  loading.value = true
  source.value = ''
  execResult.value = ''
  params.value = []
  paramVals.value = {}
  try {
    const d = await getRoutineSource(r.s, r.name, r.kind)
    source.value = (d as { source?: string }).source || ''
    try {
      const ps = await getRoutineParams(r.s, r.name, r.kind) as unknown as { name: string; type: string }[]
      params.value = ps || []
    } catch { params.value = [] }
  } catch (e) {
    ui.toast('加载失败: ' + errMsg(e), true)
  } finally {
    loading.value = false
  }
})

async function doSave() {
  const r = target.value
  if (!r) return
  if (!source.value.trim()) { ui.toast('源码为空', true); return }
  if (!await confirmDanger(`保存并重建 ${r.kind === 'Trigger' ? '触发器' : r.kind}「${r.name}」？(DROP 后重建)`, )) return
  saving.value = true
  try {
    const d = await saveRoutine({ s: r.s, name: r.name, kind: r.kind, source: source.value })
    ui.toast('已保存' + ((d as { message?: string }).message ? ': ' + (d as { message?: string }).message : ''))
  } catch (e) {
    ui.toast('保存失败: ' + errMsg(e), true)
  } finally {
    saving.value = false
  }
}

async function doExecute() {
  const r = target.value
  if (!r) return
  executing.value = true
  execResult.value = ''
  try {
    const payload: Record<string, unknown> = { s: r.s, name: r.name, kind: r.kind }
    const vals: Record<string, unknown> = {}
    params.value.forEach(p => {
      const v = paramVals.value[p.name]
      if (v !== undefined && v !== '') vals[p.name] = v
    })
    if (Object.keys(vals).length) payload.params = vals
    const d = await executeRoutine(payload) as { rows?: Record<string, unknown>[]; columns?: { name: string }[]; message?: string; error?: string }
    if (d.error) throw new Error(d.error)
    if (d.columns?.length) {
      execResult.value = (d.rows || []).slice(0, 20).map(r =>
        d.columns!.map(c => String(r[c.name] ?? '')).join(' | ')).join('\n')
    } else {
      execResult.value = d.message || '执行成功'
    }
  } catch (e) {
    execResult.value = '执行失败: ' + errMsg(e)
  } finally {
    executing.value = false
  }
}

async function doDrop() {
  const r = target.value
  if (!r) return
  if (!await confirmDanger(`确认删除 ${KIND_LABEL[r.kind] || r.kind}「${r.name}」？该操作不可撤销！`)) return
  try {
    await dropRoutine({ s: r.s, name: r.name, kind: r.kind })
    ui.toast('已删除')
    ui.closeRoutine()
  } catch (e) {
    ui.toast('删除失败: ' + errMsg(e), true)
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="ui.routine" class="rt-mask" @click.self="ui.closeRoutine()">
      <div class="rt-modal">
        <div class="rt-head">
          <h3>{{ KIND_LABEL[target?.kind || ''] || target?.kind }}编辑器 · {{ target?.s }}.{{ target?.name }}</h3>
          <button class="primary sm" @click="ui.closeRoutine()">关闭</button>
        </div>
        <div v-if="loading" class="empty2" style="padding:20px;text-align:center">加载中...</div>
        <template v-else>
          <textarea v-model="source" class="rt-src" spellcheck="false"
                    placeholder="编辑源码... 保存将 DROP 后重建"></textarea>
          <!-- 参数(执行时) -->
          <div v-if="params.length" class="rt-params">
            <span class="rt-plbl">执行参数:</span>
            <div v-for="p in params" :key="p.name" class="rt-param">
              <label>{{ p.name }} <span class="rt-ptype">{{ p.type }}</span></label>
              <input v-model="paramVals[p.name]" placeholder="值(可空)" />
            </div>
          </div>
          <pre v-if="execResult" class="rt-result">{{ execResult }}</pre>
          <div class="rt-acts">
            <button class="sm" @click="doExecute" :disabled="executing" title="执行...">▶ 执行</button>
            <button class="sm danger" @click="doDrop" title="DROP 删除"><Icon name="trash" :size="13"/> 删除</button>
            <button class="sm primary" @click="doSave" :disabled="saving" title="DROP 后重建"><Icon name="save" :size="13"/> 保存重建</button>
          </div>
        </template>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.rt-mask {
  position: fixed; inset: 0; z-index: 9100;
  background: rgba(0, 0, 0, 0.45);
  display: flex; align-items: center; justify-content: center; padding: 16px;
}
.rt-modal {
  background: var(--panel, #fff); border-radius: 10px;
  width: 760px; max-width: 94vw; max-height: 88vh;
  display: flex; flex-direction: column;
  padding: 16px 20px 20px; box-shadow: 0 8px 30px rgba(0, 0, 0, 0.2);
}
.rt-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.rt-head h3 { margin: 0; font-size: 15px; }
.rt-src {
  flex: 1; min-height: 200px; resize: none;
  font-family: Consolas, "Cascadia Mono", monospace; font-size: 13px; line-height: 1.5;
  padding: 10px; border: 1px solid var(--border2, #e5e6eb); border-radius: 6px;
  background: var(--panel2, #f7f8fa); color: inherit; outline: none;
}
.rt-params { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 8px; }
.rt-plbl { font-size: 12px; color: var(--text2, #86909c); }
.rt-param { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.rt-param label { color: var(--text2, #86909c); }
.rt-ptype { color: #999; font-size: 11px; }
.rt-param input { width: 130px; padding: 4px 8px; border: 1px solid var(--border2, #e5e6eb); border-radius: 5px; font-size: 12px; background: var(--panel, #fff); color: inherit; }
.rt-result {
  margin: 8px 0 0; padding: 8px 10px; max-height: 160px; overflow: auto;
  background: var(--panel2, #f7f8fa); border-radius: 6px;
  font-family: Consolas, monospace; font-size: 12px; white-space: pre-wrap;
}
.rt-acts { display: flex; gap: 8px; justify-content: flex-end; margin-top: 10px; }
button.sm { padding: 5px 12px; font-size: 12px; }
.empty2 { color: var(--text3, #999); font-size: 13px; }
</style>
