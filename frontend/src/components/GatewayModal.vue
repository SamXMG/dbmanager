<script setup lang="ts">
import { ref } from 'vue'
import Icon from '@/components/Icon.vue'
import { useAuthStore } from '@/stores/auth'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ close: [] }>()

const authStore = useAuthStore()
const token = ref('')
const msg = ref('')
const msgErr = ref(false)
const loading = ref(false)

async function doSubmit() {
  msg.value = ''; msgErr.value = false
  if (!token.value.trim()) { msg.value = '请输入访问令牌'; msgErr.value = true; return }
  loading.value = true
  const r = await authStore.doGatewayLogin(token.value.trim())
  loading.value = false
  if (r.ok) { location.reload() }
  else { msg.value = r.error || '验证失败'; msgErr.value = true }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="show" class="modal-mask" @click.self="emit('close')">
      <div class="modal-box" style="max-width:400px" v-draggable-modal>
        <div class="modal-header">
          <h3>公网访问验证</h3>
          <button class="sm" @click="emit('close')"><Icon name="x" :size="14" /></button>
        </div>
        <p class="sub">需要输入网关令牌才能从公网访问本服务。</p>
        <div class="field">
          <label>访问令牌</label>
          <input v-model="token" type="password" placeholder="请输入网关令牌" @keyup.enter="doSubmit" autofocus />
        </div>
        <div v-if="msg" :class="msgErr ? 'err-msg' : 'ok-msg'" style="margin-bottom:8px">{{ msg }}</div>
        <button class="primary" style="width:100%" :disabled="loading" @click="doSubmit">{{ loading ? '验证中...' : '确认' }}</button>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 1000; padding: 16px; box-sizing: border-box; }
.modal-box { background: var(--panel); border-radius: 8px; padding: 20px; width: 90%; max-width: 400px; border: 1px solid var(--border); max-height: 90vh; overflow-y: auto; box-sizing: border-box; }
.modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.modal-header h3 { margin: 0; color: var(--text); }
.sub { font-size: 13px; color: var(--text2); margin-bottom: 12px; }
.field { margin-bottom: 10px; }
.field label { display: block; font-size: 13px; color: var(--text2); margin-bottom: 3px; }
.field input { width: 100%; padding: 6px 8px; border: 1px solid var(--border2); border-radius: 4px; background: var(--panel3); color: var(--text); font-size: 14px; box-sizing: border-box; }
.err-msg { color: var(--danger); font-size: 13px; }
.ok-msg { color: var(--success); font-size: 13px; }
button { padding: 6px 16px; border: 1px solid var(--border); border-radius: 4px; background: var(--panel2); color: var(--text); cursor: pointer; font-size: 13px; }
button.primary { background: var(--primary); color: #fff; border-color: var(--primary); }
button.sm { padding: 4px 10px; font-size: 12px; }
button:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
