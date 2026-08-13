<script setup lang="ts">
// 数据同步弹窗(整合 ObjectTree.openTransfer + openSchemaSync 两个逻辑到单一组件)。
// 由 GenericModal 在共享遮罩内渲染: 本组件只渲染 <div class="g-modal"> 卡片根, 不 Teleport、不渲染遮罩。
// 打开方式(调用方实现): ui.openModal('SyncModal', { s, t }) ; 关闭统一 ui.closeModal()。
import { ref, computed, onMounted } from 'vue'
import { confirmDanger } from '@/utils/confirm'
import { errMsg } from '@/utils/err'
import { useUIStore } from '@/stores/ui'
import { useConnectionStore } from '@/stores/connection'
import { useDatabaseStore } from '@/stores/database'
import { transferData, schemaSync } from '@/api/schema'
import { listConnections, type ConnMeta } from '@/api/connection'

const ui = useUIStore()
const connStore = useConnectionStore()
const dbStore = useDatabaseStore()

const props = defineProps<{ s: string; t: string }>()

type Mode = 'copy' | 'sync'
const mode = ref<Mode>('copy')

// ---- 模式A: 复制到同连接其他库(对应 openTransfer) ----
const curDb = computed(() => connStore.conn?.database || '')
// 目标库选项 = [当前库, ...其他库]
const dbOptions = computed<string[]>(() => {
  const others = dbStore.databases.filter((d) => d && d !== curDb.value)
  return [curDb.value, ...others]
})
const toDb = ref(curDb.value)
const toT = ref(props.t + '_copy')

// ---- 模式B: 同步到目标连接同名表(对应 openSchemaSync) ----
const conns = ref<ConnMeta[]>([])
const dstName = ref('')
const syncMode = ref<'append' | 'replace'>('append')

// 源连接: 优先用当前连接的 name 标识; 否则回退到整个 conn 对象(对齐 openSchemaSync 的 src 推导)
const src = computed(() => {
  const conn = connStore.conn
  return conn && conn.name ? { name: conn.name } : (conn || {})
})

onMounted(async () => {
  try { conns.value = await listConnections() } catch { conns.value = [] }
  if (conns.value.length) dstName.value = conns.value[0].name || ''
})

async function doCopy() {
  const target = toT.value.trim()
  if (!target) { ui.toast('请填写目标表', true); return }
  try {
    const d = await transferData({ s: props.s, t: props.t, to_db: toDb.value, to_t: target })
    ui.closeModal()
    ui.toast('已同步 ' + (d.transferred ?? 0) + ' 行数据')
  } catch (e) { ui.toast('同步失败: ' + errMsg(e), true) }
}

async function doSync() {
  if (!dstName.value) { ui.toast('请选择目标连接', true); return }
  const m = syncMode.value
  if (!await confirmDanger(`确认将 ${props.s}.${props.t} 同步到「${dstName.value}」(${m === 'replace' ? '清空目标后复制' : '追加'})?`)) return
  try {
    const d = (await schemaSync({ src: src.value, dst: { name: dstName.value }, schema: props.s, table: props.t, mode: m })) as { synced?: number }
    ui.closeModal()
    ui.toast(d && d.synced != null ? '同步完成: 复制 ' + d.synced + ' 行' : '同步完成')
  } catch (e) { ui.toast('同步失败: ' + errMsg(e), true) }
}
</script>

<template>
  <div class="g-modal">
    <h3>数据同步 · {{ s }}.{{ t }}</h3>
    <div style="color:var(--text3);font-size:12px;margin-bottom:10px">选择同步方式后填入目标信息并确认。</div>

    <div class="field">
      <label>同步模式</label>
      <div class="mode-row">
        <label class="rd"><input type="radio" value="copy" v-model="mode" /> 复制到同连接其他库</label>
        <label class="rd"><input type="radio" value="sync" v-model="mode" /> 同步到目标连接同名表</label>
      </div>
    </div>

    <!-- 模式A: 复制到同连接其他库 -->
    <template v-if="mode === 'copy'">
      <div class="field">
        <label>目标库</label>
        <select v-model="toDb">
          <option v-for="d in dbOptions" :key="d" :value="d">{{ d }}</option>
        </select>
      </div>
      <div class="field">
        <label>目标表(须已存在)</label>
        <input v-model="toT" :placeholder="t + '_copy'" />
      </div>
      <p style="color:var(--warning);font-size:12px">⚠ 源表全部数据将插入目标表(按同名列交集, 目标自增主键由数据库生成)</p>
      <div class="acts">
        <button @click="ui.closeModal()">取消</button>
        <button class="primary" @click="doCopy">开始同步</button>
      </div>
    </template>

    <!-- 模式B: 同步到目标连接同名表 -->
    <template v-else>
      <div v-if="!conns.length" class="empty2">请先在「我的连接」中保存目标连接</div>
      <template v-else>
        <div class="field">
          <label>目标连接</label>
          <select v-model="dstName">
            <option v-for="c in conns" :key="c.name" :value="c.name">{{ c.name }} ({{ c.db_type }} · {{ c.server || '' }})</option>
          </select>
        </div>
        <div class="field">
          <label>模式</label>
          <select v-model="syncMode">
            <option value="append">追加(不清空目标)</option>
            <option value="replace">清空目标后复制</option>
          </select>
        </div>
        <p style="color:var(--text3);font-size:12px">把当前连接中该表数据复制到目标连接的<b>同名表</b>(按同名列匹配)</p>
        <div class="acts">
          <button @click="ui.closeModal()">取消</button>
          <button class="primary" @click="doSync">开始同步</button>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.mode-row { display: flex; gap: 18px; flex-wrap: wrap; }
.rd { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer; }
</style>
