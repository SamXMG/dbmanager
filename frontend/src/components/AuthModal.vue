<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useConnectionStore } from '@/stores/connection'

const props = defineProps<{ show: boolean; force?: boolean }>()   // force: 强制改密模式(默认账号首改)
const emit = defineEmits<{ close: [] }>()

const authStore = useAuthStore()
const connStore = useConnectionStore()

// 视图切换: login / register / changePwd
const view = ref<'login' | 'register' | 'changePwd'>('login')

// 强制改密模式: 只显示改密视图, 不可关闭/不可切换
watch(
  () => [props.show, props.force],
  ([show, force]) => {
    if (show && force) view.value = 'changePwd'
  },
)

// 登录表单
const loginUser = ref('')
const loginPwd = ref('')
const loginMsg = ref('')
const loginErr = ref(false)
const loginLoading = ref(false)

// 注册表单
const regUser = ref('')
const regPwd = ref('')
const regPwd2 = ref('')
const regMsg = ref('')
const regErr = ref(false)
const regLoading = ref(false)

// 改密表单
const oldPwd = ref('')
const newPwd = ref('')
const pwdMsg = ref('')
const pwdErr = ref(false)
const pwdLoading = ref(false)

const canRegister = computed(() => connStore.registerEnabled)

async function doLogin() {
  loginMsg.value = ''; loginErr.value = false
  if (!loginUser.value || !loginPwd.value) { loginMsg.value = '请填写用户名和密码'; loginErr.value = true; return }
  loginLoading.value = true
  const r = await authStore.doLogin(loginUser.value, loginPwd.value)
  loginLoading.value = false
  if (r.ok) {
    loginPwd.value = ''
    if (authStore.mustChangePwd) {   // 默认账号 → 强制进入改密流程(不关闭弹窗)
      loginUser.value = ''; loginMsg.value = ''; view.value = 'changePwd'
      return
    }
    emit('close')
  }
  else { loginMsg.value = r.error || '登录失败'; loginErr.value = true }
}

async function doRegister() {
  regMsg.value = ''; regErr.value = false
  if (!regUser.value || !regPwd.value) { regMsg.value = '请填写用户名和密码'; regErr.value = true; return }
  if (regPwd.value !== regPwd2.value) { regMsg.value = '两次密码不一致'; regErr.value = true; return }
  regLoading.value = true
  const r = await authStore.doRegister(regUser.value, regPwd.value)
  regLoading.value = false
  if (r.ok) {
    // 注册进入待审批状态, 提示等待管理员审批(局域网一次性部署: 管理员审批放权)
    regMsg.value = r.message || '注册已提交, 等待管理员审批后可登录'; regErr.value = false
    regUser.value = ''; regPwd.value = ''; regPwd2.value = ''
  } else {
    regMsg.value = r.error || '注册失败'; regErr.value = true
  }
}

async function doChangePwd() {
  pwdMsg.value = ''; pwdErr.value = false
  if (!oldPwd.value || !newPwd.value) { pwdMsg.value = '请填写旧密码和新密码'; pwdErr.value = true; return }
  pwdLoading.value = true
  const r = await authStore.doChangePwd(oldPwd.value, newPwd.value)
  pwdLoading.value = false
  if (r.ok) {
    pwdMsg.value = '密码已更新'; pwdErr.value = false; oldPwd.value = ''; newPwd.value = ''
    if (props.force) emit('close')   // 强制模式: 改密成功即解除拦截并关闭
  }
  else { pwdMsg.value = r.error || '改密失败'; pwdErr.value = true }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="show" class="modal-mask" @click.self="!props.force && emit('close')">
      <div class="modal-box" style="max-width:400px">
        <div class="modal-header">
          <h3>{{ view === 'login' ? '登录' : view === 'register' ? '注册' : props.force ? '修改密码（首次登录必须修改默认密码）' : '修改密码' }}</h3>
          <button v-if="!props.force" class="sm" @click="emit('close')">✕</button>
        </div>

        <!-- 登录视图 -->
        <div v-if="view === 'login'">
          <div class="field"><label>用户名</label><input v-model="loginUser" @keyup.enter="doLogin" autofocus /></div>
          <div class="field"><label>密码</label><input v-model="loginPwd" type="password" @keyup.enter="doLogin" /></div>
          <div v-if="loginMsg" :class="loginErr ? 'err-msg' : 'ok-msg'" style="margin-bottom:8px">{{ loginMsg }}</div>
          <button class="primary" style="width:100%" :disabled="loginLoading" @click="doLogin">{{ loginLoading ? '登录中...' : '登录' }}</button>
          <div v-if="canRegister" class="link-row">没有账号？<a href="#" @click.prevent="view = 'register'">注册</a></div>
          <div v-if="authStore.isLoggedIn" class="link-row"><a href="#" @click.prevent="view = 'changePwd'">修改密码</a></div>
        </div>

        <!-- 注册视图 -->
        <div v-else-if="view === 'register'">
          <div class="field"><label>用户名</label><input v-model="regUser" @keyup.enter="doRegister" autofocus /></div>
          <div class="field"><label>密码</label><input v-model="regPwd" type="password" /></div>
          <div class="field"><label>确认密码</label><input v-model="regPwd2" type="password" @keyup.enter="doRegister" /></div>
          <div v-if="regMsg" :class="regErr ? 'err-msg' : 'ok-msg'" style="margin-bottom:8px">{{ regMsg }}</div>
          <button class="primary" style="width:100%" :disabled="regLoading" @click="doRegister">{{ regLoading ? '注册中...' : '注册' }}</button>
          <div class="link-row">已有账号？<a href="#" @click.prevent="view = 'login'">登录</a></div>
        </div>

        <!-- 改密视图 -->
        <div v-else>
          <div class="field"><label>旧密码</label><input v-model="oldPwd" type="password" /></div>
          <div class="field"><label>新密码（至少6位）</label><input v-model="newPwd" type="password" @keyup.enter="doChangePwd" /></div>
          <div v-if="pwdMsg" :class="pwdErr ? 'err-msg' : 'ok-msg'" style="margin-bottom:8px">{{ pwdMsg }}</div>
          <button class="primary" style="width:100%" :disabled="pwdLoading" @click="doChangePwd">{{ pwdLoading ? '提交中...' : '确认修改' }}</button>
          <div v-if="!props.force" class="link-row"><a href="#" @click.prevent="view = 'login'">返回登录</a></div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 1000; padding: 16px; box-sizing: border-box; }
.modal-box { background: var(--panel); border-radius: 8px; padding: 20px; width: 90%; max-width: 400px; border: 1px solid var(--border); max-height: 90vh; overflow-y: auto; box-sizing: border-box; }
.modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.modal-header h3 { margin: 0; color: var(--text); }
.field { margin-bottom: 10px; }
.field label { display: block; font-size: 13px; color: var(--text2); margin-bottom: 3px; }
.field input { width: 100%; padding: 6px 8px; border: 1px solid var(--border2); border-radius: 4px; background: var(--panel3); color: var(--text); font-size: 14px; box-sizing: border-box; }
.err-msg { color: #e54d42; font-size: 13px; }
.ok-msg { color: #00b42a; font-size: 13px; }
.link-row { text-align: center; margin-top: 10px; font-size: 13px; color: var(--text2); }
.link-row a { color: var(--primary); text-decoration: none; }
.link-row a:hover { text-decoration: underline; }
button { padding: 6px 16px; border: 1px solid var(--border); border-radius: 4px; background: var(--panel2); color: var(--text); cursor: pointer; font-size: 13px; }
button.primary { background: var(--primary); color: #fff; border-color: var(--primary); }
button.sm { padding: 4px 10px; font-size: 12px; }
button:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
