<script setup lang="ts">
// 用户与权限(只读视图): 复刻 tools.ts openDbUsers。
// 弹窗由 GenericModal 在共享遮罩内渲染, 此处只渲染 .g-modal 卡片根。
import { ref, onMounted } from 'vue'
import { useUIStore } from '@/stores/ui'
import { useConnectionStore } from '@/stores/connection'
import { API_BASE, authHeaders } from '@/api/client'
import { errMsg } from '@/utils/err'

const ui = useUIStore()
const connStore = useConnectionStore()

interface DbUserRow { [k: string]: unknown }
interface DbUsersResp {
  supported?: boolean
  logins?: DbUserRow[]
  users?: DbUserRow[]
  roles?: DbUserRow[]
  permissions?: DbUserRow[]
  error?: string
}

const loading = ref(true)
const error = ref('')
const data = ref<DbUsersResp | null>(null)

function cell(v: unknown): string {
  if (v === null || v === undefined) return '-'
  return String(v)
}
function yn(v: unknown): string {
  if (v === true) return '是'
  if (v === false) return '否'
  return '-'
}

onMounted(async () => {
  if (!connStore.connected) { loading.value = false; error.value = '请先连接数据库'; return }
  try {
    const headers = await authHeaders()
    const r = await fetch(API_BASE + '/api/db-users', { headers })
    const d = (await r.json().catch(() => ({}))) as DbUsersResp
    if (d.error) throw new Error(d.error)
    data.value = d
  } catch (e) { error.value = errMsg(e) }
  finally { loading.value = false }
})
</script>

<template>
  <div class="g-modal">
    <h3>用户与权限</h3>
    <div style="color:var(--text3);font-size:12px;margin-bottom:6px">只读视图 — 登录 / 用户 / 角色 / 权限</div>

    <div v-if="loading" class="empty2" style="padding:20px">加载中...</div>
    <div v-else-if="error" class="empty2" style="padding:20px">加载失败: {{ error }}</div>
    <template v-else-if="data">
      <div v-if="!data.supported" class="empty2" style="padding:20px">当前数据库类型不支持用户与权限管理</div>
      <div v-else class="props-body">
        <section v-if="data.logins && data.logins.length">
          <h4 style="margin:10px 0 4px">服务器登录 ({{ data.logins.length }})</h4>
          <table class="p-tbl">
            <thead><tr><th>登录名</th><th>类型</th><th>已禁用</th><th>创建日期</th><th>主机</th><th>有密码</th></tr></thead>
            <tbody>
              <tr v-for="(r, i) in data.logins" :key="'l' + i">
                <td>{{ cell(r.name) }}</td><td>{{ cell(r.type) }}</td><td>{{ yn(r.disabled) }}</td>
                <td>{{ cell(r.created) }}</td><td>{{ cell(r.host) }}</td><td>{{ yn(r.has_pwd) }}</td>
              </tr>
            </tbody>
          </table>
        </section>
        <div v-else class="empty2">服务器登录: 无数据</div>

        <section v-if="data.users && data.users.length">
          <h4 style="margin:10px 0 4px">数据库用户 ({{ data.users.length }})</h4>
          <table class="p-tbl">
            <thead><tr><th>用户名</th><th>类型</th><th>默认架构</th><th>关联登录</th></tr></thead>
            <tbody>
              <tr v-for="(r, i) in data.users" :key="'u' + i">
                <td>{{ cell(r.name) }}</td><td>{{ cell(r.type) }}</td>
                <td>{{ cell(r.default_schema) }}</td><td>{{ cell(r.login) }}</td>
              </tr>
            </tbody>
          </table>
        </section>
        <div v-else class="empty2">数据库用户: 无数据</div>

        <section v-if="data.roles && data.roles.length">
          <h4 style="margin:10px 0 4px">角色成员 ({{ data.roles.length }})</h4>
          <table class="p-tbl">
            <thead><tr><th>角色</th><th>成员</th></tr></thead>
            <tbody>
              <tr v-for="(r, i) in data.roles" :key="'r' + i">
                <td>{{ cell(r.role) }}</td><td>{{ cell(r.member) }}</td>
              </tr>
            </tbody>
          </table>
        </section>
        <div v-else class="empty2">角色成员: 无数据</div>

        <section v-if="data.permissions && data.permissions.length">
          <h4 style="margin:10px 0 4px">显式权限 ({{ data.permissions.length }})</h4>
          <table class="p-tbl">
            <thead><tr><th>授权对象</th><th>权限</th><th>状态</th><th>对象</th></tr></thead>
            <tbody>
              <tr v-for="(r, i) in data.permissions" :key="'p' + i">
                <td>{{ cell(r.grantee) }}</td><td>{{ cell(r.permission) }}</td>
                <td>{{ cell(r.state) }}</td><td>{{ cell(r.object) }}</td>
              </tr>
            </tbody>
          </table>
        </section>
        <div v-else class="empty2">显式权限: 无数据</div>
      </div>
    </template>
    <div class="acts"><button class="primary" @click="ui.closeModal()">关闭</button></div>
  </div>
</template>
