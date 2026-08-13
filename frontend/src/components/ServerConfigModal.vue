<script setup lang="ts">
// 服务器配置弹窗(仅 admin): 读/写 dbmanager.conf
// 分组展示 [server]/[auth] 可编辑项; 敏感键(gateway_token/default_pwd/ldap_bindpw)掩码显示;
// 生效类型: instant=保存即生效(LDAP/注册/认证等运行时读取项), restart=需重启(host/port/ssl);
// 支持「立即重启」按钮(admin), 重启期间服务短暂中断, 恢复后需重新登录
import { ref, onMounted } from 'vue'
import Icon from '@/components/Icon.vue'
import { errMsg } from '@/utils/err'
import { confirmDanger } from '@/utils/confirm'
import { getConfigSettings, saveConfigSettings, restartServer, type ConfigSections } from '@/api/account'

const emit = defineEmits<{ close: [] }>()
const sections = ref<ConfigSections>({})
const configFile = ref('')
const loading = ref(true)
const saving = ref(false)
const restarting = ref(false)
const msg = ref('')
const msgErr = ref(false)

const SECTION_LABEL: Record<string, string> = { server: '服务端 [server]', auth: '认证 [auth]' }
const KEY_LABEL: Record<string, string> = {
  host: '监听地址', port: '监听端口', db_file: '数据文件', dev: '开发模式',
  log: '请求日志', no_open: '不自动开浏览器', no_kill: '不接管端口',
  ssl: '启用 HTTPS', ssl_cert: '证书路径', ssl_key: '私钥路径',
  gateway_token: '网关令牌', default_conn: '默认连接',
  default_pwd: '默认密码(仅首建)', allow_register: '自助注册',
  auth_enabled: '强制认证', ldap_url: 'LDAP 地址', ldap_base: 'LDAP 搜索根',
  ldap_binddn: 'LDAP 绑定 DN', ldap_bindpw: 'LDAP 绑定密码', ldap_attr: 'LDAP 用户名属性',
}
const KEY_HINT: Record<string, string> = {
  host: '127.0.0.1=仅本机; 0.0.0.0=开放局域网/公网',
  gateway_token: '留空自动生成并保存 .dbm_gateway',
  default_pwd: '仅首次建库生效, 之后请走页面改密',
}

function showInfo(m: string, err = false) {
  msg.value = m; msgErr.value = err
  setTimeout(() => { if (msg.value === m) msg.value = '' }, 5000)
}

async function load() {
  loading.value = true
  try {
    const r = await getConfigSettings()
    sections.value = r.sections || {}
    configFile.value = r.config_file || ''
  } catch (e) { showInfo('读取失败: ' + errMsg(e), true) }
  loading.value = false
}

async function doSave() {
  saving.value = true
  try {
    const r = await saveConfigSettings(sections.value)
    if (r.restart_required) {
      showInfo((r.message || '已保存，需重启生效') + ' —— 可点下方「立即重启」')
    } else {
      showInfo(r.message || '已保存并即时生效')
    }
  } catch (e) { showInfo(errMsg(e), true) }
  saving.value = false
}

async function doRestart() {
  if (!await confirmDanger('确认立即重启服务？\n重启期间服务将中断约 2~3 秒，恢复后需要重新登录。\n（用于使 host/port/HTTPS 等配置生效）')) return
  restarting.value = true
  try {
    const r = await restartServer()
    showInfo(r.message || '重启中…')
  } catch (e) { showInfo(errMsg(e), true) }
  // 服务重启后本页会话失效: 延迟提示并关闭弹窗
  setTimeout(() => emit('close'), 2500)
  setTimeout(() => { window.location.reload() }, 3000)
  restarting.value = false
}

function isSwitch(key: string): boolean {
  return ['dev', 'log', 'no_open', 'no_kill', 'ssl', 'allow_register', 'auth_enabled'].includes(key)
}
function isSecret(key: string): boolean {
  return ['gateway_token', 'default_pwd', 'ldap_bindpw'].includes(key)
}

onMounted(load)
</script>

<template>
  <Teleport to="body">
    <div class="modal-mask" @click.self="emit('close')">
      <div class="modal-box">
        <div class="modal-header">
          <h3>服务器配置</h3>
          <button class="sm" @click="emit('close')"><Icon name="x" :size="14" /></button>
        </div>
        <div v-if="msg" :class="msgErr ? 'err-msg' : 'ok-msg'" style="margin-bottom:8px">{{ msg }}</div>
        <div class="hint">
          修改 <code>{{ configFile || 'dbmanager.conf' }}</code>。<span class="tag-instant">即时生效</span>=保存即生效（LDAP/注册/认证等）；
          <span class="tag-restart">需重启</span>=启动期配置（监听地址/端口/HTTPS），保存后可点「立即重启」。敏感项已掩码，留空保持原值。仅管理员可操作。
        </div>

        <div v-if="loading" class="empty">加载中…</div>
        <div v-else>
          <div v-for="(items, section) in sections" :key="section" class="cfg-sec">
            <h4>{{ SECTION_LABEL[section] || section }}</h4>
            <div class="cfg-grid">
              <div v-for="(item, key) in items" :key="section + '.' + key" class="cfg-item">
                <label :title="item.env">
                  {{ KEY_LABEL[key] || key }}
                  <span class="tag" :class="item.apply === 'restart' ? 'tag-restart' : 'tag-instant'">
                    {{ item.apply === 'restart' ? '需重启' : '即时生效' }}
                  </span>
                </label>
                <template v-if="isSwitch(key)">
                  <select v-model="item.value" :disabled="isSecret(key) && item.masked">
                    <option value="">默认</option>
                    <option value="1">开 (1)</option>
                    <option value="0">关 (0)</option>
                  </select>
                </template>
                <template v-else>
                  <input
                    v-model="item.value"
                    type="text"
                    :placeholder="item.default || '留空'"
                    :disabled="isSecret(key) && item.masked"
                  />
                </template>
                <span v-if="KEY_HINT[key]" class="tip">{{ KEY_HINT[key] }}</span>
                <span v-if="isSecret(key) && item.masked" class="tip">已设置（掩码显示，留空保存则保留）</span>
              </div>
            </div>
          </div>
        </div>

        <div class="footer">
          <button class="sm" @click="emit('close')">取消</button>
          <button class="sm danger" :disabled="loading || restarting" @click="doRestart">{{ restarting ? '重启中…' : '立即重启' }}</button>
          <button class="sm primary" :disabled="loading || saving" @click="doSave">{{ saving ? '保存中…' : '保存配置' }}</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 1001; padding: 16px; box-sizing: border-box; }
.modal-box { background: var(--panel); border-radius: 8px; padding: 20px; width: 94%; max-width: 760px; border: 1px solid var(--border); max-height: 86vh; overflow-y: auto; box-sizing: border-box; }
.modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.modal-header h3 { margin: 0; color: var(--text); }
.hint { font-size: 12px; color: var(--text2); background: var(--panel3); border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; margin-bottom: 10px; }
.hint code { background: var(--panel2); padding: 0 4px; border-radius: 3px; }
.empty { font-size: 13px; color: var(--text3); padding: 10px 0; }
.cfg-sec { margin-bottom: 16px; }
.cfg-sec h4 { margin: 0 0 8px; font-size: 13px; font-weight: 600; color: var(--text); }
.cfg-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.cfg-item { display: flex; flex-direction: column; gap: 4px; }
.cfg-item label { font-size: 12px; color: var(--text2); }
.tag { font-size: 10px; padding: 1px 5px; border-radius: 8px; margin-left: 4px; font-weight: 400; }
.tag-instant { background: var(--success-bg); color: var(--success); }
.tag-restart { background: var(--warning-bg); color: var(--warning); }
.cfg-item input, .cfg-item select { width: 100%; box-sizing: border-box; padding: 6px 8px; border: 1px solid var(--border); border-radius: 4px; background: var(--panel2); color: var(--text); font-size: 13px; }
.cfg-item .tip { font-size: 11px; color: var(--text3); }
.footer { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
button { padding: 5px 14px; border: 1px solid var(--border); border-radius: 4px; background: var(--panel2); color: var(--text); cursor: pointer; font-size: 13px; }
button.sm { padding: 3px 10px; font-size: 12px; }
button.primary { background: var(--success); color: #fff; border-color: var(--success); }
button.danger { background: var(--danger-solid); color: #fff; border-color: var(--danger-solid); }
.err-msg { color: var(--danger); font-size: 13px; }
.ok-msg { color: var(--success); font-size: 13px; }
@media (max-width: 560px) { .cfg-grid { grid-template-columns: 1fr; } }
</style>
