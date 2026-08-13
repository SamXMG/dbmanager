<script setup lang="ts">
// 权限配置弹窗(连接/表级细粒度读写): 单用户或批量(多选用户)配置
// 每连接: 读/写开关 + 表范围(全部表 | 指定白名单表 | 黑名单表), 支持拉取真实表名多选
import { ref, reactive, computed, onMounted } from 'vue'
import Icon from '@/components/Icon.vue'
import { errMsg } from '@/utils/err'
import { getUserPerms, saveUserPerms, fetchConnTables, type ConnPerm } from '@/api/account'

const props = defineProps<{ show: boolean; usernames: string[] }>()
const emit = defineEmits<{ close: []; saved: [] }>()

// usernames: string[]; perms: Record<connName, ConnPerm>
const perms = reactive<Record<string, ConnPerm>>({})
const connections = ref<string[]>([])
const loading = ref(false)
const msg = ref('')
const msgErr = ref(false)
const expanded = ref<Record<string, boolean>>({})
const allTables = ref<Record<string, string[]>>({})   // 连接 -> 真实表名(点击"拉取"后缓存)
const fetching = ref('')

const title = computed(() =>
  props.usernames.length > 1 ? `批量设置权限（${props.usernames.length} 个用户）` : `权限配置：${props.usernames[0] || ''}`)

function showInfo(m: string, err = false) {
  msg.value = m; msgErr.value = err
  setTimeout(() => { if (msg.value === m) msg.value = '' }, 3000)
}

function ensureConn(name: string) {
  if (!perms[name]) perms[name] = { read: true, write: false, tables: [], deny_tables: [] }
}

async function loadTables(name: string) {
  fetching.value = name
  try {
    const r = await fetchConnTables(name)
    if (r.ok === false) showInfo(r.error || '拉取表列表失败', true)
    else allTables.value[name] = r.tables || []
    expanded.value[name] = true
  } catch (e) { showInfo(errMsg(e), true) }
  fetching.value = ''
}

/** 表格编辑: 白名单表(逗号分隔文本 <-> 数组) */
function tablesText(name: string): string { return (perms[name]?.tables || []).join(', ') }
function setTablesText(name: string, v: string) {
  ensureConn(name)
  perms[name].tables = v.split(/[,，\s]+/).map(s => s.trim()).filter(Boolean)
}
function setDenyText(name: string, v: string) {
  ensureConn(name)
  perms[name].deny_tables = v.split(/[,，\s]+/).map(s => s.trim()).filter(Boolean)
}
function toggleTablePick(name: string, t: string) {
  ensureConn(name)
  const arr = perms[name].tables || []
  perms[name].tables = arr.includes(t) ? arr.filter(x => x !== t) : [...arr, t]
}
function toggleDeny(name: string, t: string) {
  ensureConn(name)
  const arr = perms[name].deny_tables || []
  perms[name].deny_tables = arr.includes(t) ? arr.filter(x => x !== t) : [...arr, t]
}
/** 表范围: 全部 / 白名单 / 黑名单 */
function scopeOf(name: string): 'all' | 'allow' | 'deny' {
  const p = perms[name]
  if (!p) return 'all'
  if ((p.tables || []).length) return 'allow'
  if ((p.deny_tables || []).length) return 'deny'
  return 'all'
}
function setScope(name: string, s: 'all' | 'allow' | 'deny') {
  ensureConn(name)
  if (s === 'all') { perms[name].tables = []; perms[name].deny_tables = [] }
  else if (s === 'allow') { perms[name].tables = perms[name].tables || []; perms[name].deny_tables = [] }
  else { perms[name].deny_tables = perms[name].deny_tables || []; perms[name].tables = [] }
}

async function doSave() {
  if (!props.usernames.length) return
  loading.value = true
  try {
    const r = await saveUserPerms(props.usernames, perms)
    showInfo(r.message || '已保存')
    emit('saved')
    setTimeout(() => emit('close'), 800)
  } catch (e) { showInfo(errMsg(e), true) }
  loading.value = false
}

onMounted(async () => {
  loading.value = true
  try {
    if (props.usernames.length) {
      const r = await getUserPerms(props.usernames[0])
      connections.value = r.connections || []
      // 批量模式: 以第一个用户的权限为模板(其余用户视为相同初始); 无权限记录则给默认
      for (const c of connections.value) {
        if (r.perms[c]) perms[c] = { read: !!r.perms[c].read, write: !!r.perms[c].write, tables: [...(r.perms[c].tables || [])], deny_tables: [...(r.perms[c].deny_tables || [])] }
        else perms[c] = { read: true, write: false, tables: [], deny_tables: [] }
      }
    }
  } catch (e) { showInfo(errMsg(e), true) }
  loading.value = false
})
</script>

<template>
  <Teleport to="body">
    <div v-if="show" class="modal-mask" @click.self="emit('close')">
      <div class="modal-box" style="max-width:760px">
        <div class="modal-header">
          <h3>{{ title }}</h3>
          <button class="sm" @click="emit('close')"><Icon name="x" :size="14" /></button>
        </div>
        <div v-if="msg" :class="msgErr ? 'err-msg' : 'ok-msg'" style="margin-bottom:8px">{{ msg }}</div>
        <div v-if="loading" class="empty">加载中...</div>

        <template v-else>
          <div class="hint">未配置的连接对该用户不可见、不可访问；admin 不受权限限制。保存后立即生效（已在线用户下次请求即被拦截）。</div>
          <div v-if="connections.length === 0" class="empty">暂无已保存连接，请先在「我的连接」中创建。</div>

          <div v-for="name in connections" :key="name" class="conn-block">
            <div class="conn-head" @click="expanded[name] = !expanded[name]">
              <span class="arrow">{{ expanded[name] ? '▾' : '▸' }}</span>
              <span class="cname">{{ name }}</span>
              <label class="chk" @click.stop><input type="checkbox" v-model="perms[name].read" /> 读</label>
              <label class="chk" @click.stop><input type="checkbox" v-model="perms[name].write" /> 写</label>
              <span class="scope-tag">{{ scopeOf(name) === 'all' ? '全部表' : scopeOf(name) === 'allow' ? `白名单 ${(perms[name].tables || []).length} 表` : `黑名单 ${(perms[name].deny_tables || []).length} 表` }}</span>
            </div>
            <div v-if="expanded[name]" class="conn-body">
              <div class="scope-row">
                <button class="sm" :class="{ on: scopeOf(name) === 'all' }" @click="setScope(name, 'all')">全部表</button>
                <button class="sm" :class="{ on: scopeOf(name) === 'allow' }" @click="setScope(name, 'allow')">仅指定表(白名单)</button>
                <button class="sm" :class="{ on: scopeOf(name) === 'deny' }" @click="setScope(name, 'deny')">禁止指定表(黑名单)</button>
                <button class="sm primary" @click="loadTables(name)">{{ fetching === name ? '拉取中...' : '拉取表列表' }}</button>
              </div>
              <template v-if="scopeOf(name) === 'allow'">
                <div class="tbl-hint">仅以下表对该用户可见、可操作（留空 = 全部表）。也可手动输入表名（逗号分隔）。</div>
                <input class="tbl-input" :value="tablesText(name)" @input="setTablesText(name, ($event.target as HTMLInputElement).value)" placeholder="如: orders, users, product_info" />
                <div v-if="allTables[name]" class="tbl-pick">
                  <label v-for="t in allTables[name]" :key="t" class="chk">
                    <input type="checkbox" :checked="(perms[name].tables || []).includes(t)" @change="toggleTablePick(name, t)" /> {{ t }}
                  </label>
                </div>
              </template>
              <template v-else-if="scopeOf(name) === 'deny'">
                <div class="tbl-hint">以下表对该用户禁止访问（优先于白名单；不填黑名单时白名单外的表均禁止）。</div>
                <input class="tbl-input" :value="(perms[name].deny_tables || []).join(', ')" @input="setDenyText(name, ($event.target as HTMLInputElement).value)" placeholder="如: salary, audit_log" />
                <div v-if="allTables[name]" class="tbl-pick">
                  <label v-for="t in allTables[name]" :key="t" class="chk">
                    <input type="checkbox" :checked="(perms[name].deny_tables || []).includes(t)" @change="toggleDeny(name, t)" /> {{ t }}
                  </label>
                </div>
              </template>
            </div>
          </div>

          <div class="foot">
            <button class="sm" @click="emit('close')">取消</button>
            <button class="sm primary" :disabled="loading" @click="doSave">保存{{ props.usernames.length > 1 ? `到 ${props.usernames.length} 个用户` : '' }}</button>
          </div>
        </template>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 1001; }
.modal-box { background: var(--panel); border-radius: 8px; padding: 20px; width: 94%; max-width: 760px; border: 1px solid var(--border); max-height: 86vh; overflow: auto; }
.modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.modal-header h3 { margin: 0; color: var(--text); }
.hint { font-size: 12px; color: var(--text2); background: var(--panel3); border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; margin-bottom: 10px; }
.empty { font-size: 13px; color: var(--text3); padding: 8px 0; }
.conn-block { border: 1px solid var(--border); border-radius: 6px; margin-bottom: 8px; overflow: hidden; }
.conn-head { display: flex; align-items: center; gap: 10px; padding: 8px 10px; cursor: pointer; background: var(--panel3); }
.conn-head .arrow { color: var(--text3); font-size: 12px; width: 14px; }
.conn-head .cname { flex: 1; font-size: 13px; font-weight: 500; color: var(--text); }
.conn-body { padding: 8px 12px 12px; border-top: 1px dashed var(--border); }
.scope-tag { font-size: 11px; color: var(--text2); background: var(--panel2); border: 1px solid var(--border); padding: 1px 8px; border-radius: 10px; }
.scope-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; }
button { padding: 5px 14px; border: 1px solid var(--border); border-radius: 4px; background: var(--panel2); color: var(--text); cursor: pointer; font-size: 13px; }
button.sm { padding: 3px 10px; font-size: 12px; }
button.primary { background: var(--primary); color: #fff; border-color: var(--primary); }
button.on { background: var(--primary); color: #fff; border-color: var(--primary); }
.chk { display: inline-flex; align-items: center; gap: 4px; font-size: 13px; color: var(--text); cursor: pointer; user-select: none; }
.tbl-hint { font-size: 12px; color: var(--text3); margin-bottom: 6px; }
.tbl-input { width: 100%; padding: 6px 8px; border: 1px solid var(--border2); border-radius: 4px; background: var(--panel3); color: var(--text); font-size: 13px; margin-bottom: 8px; box-sizing: border-box; }
.tbl-pick { display: flex; flex-wrap: wrap; gap: 6px 14px; max-height: 140px; overflow: auto; padding: 6px; background: var(--panel3); border: 1px solid var(--border); border-radius: 4px; }
.tbl-pick .chk { font-size: 12px; }
.foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }
.err-msg { color: var(--danger); font-size: 13px; }
.ok-msg { color: var(--success); font-size: 13px; }
</style>
