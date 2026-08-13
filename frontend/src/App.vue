<script setup lang="ts">
// 根组件: 初始化 store + 全局弹窗(网关/认证) + 路由守卫
import { defineAsyncComponent, onMounted, ref } from 'vue'
import { RouterView, useRouter } from 'vue-router'
import { useConnectionStore } from '@/stores/connection'
import { useAuthStore } from '@/stores/auth'
import type { ConfigResp } from '@/api/connection'
import GatewayModal from '@/components/GatewayModal.vue'
import AuthModal from '@/components/AuthModal.vue'
import AppHeader from '@/components/AppHeader.vue'
import CtxMenu from '@/components/CtxMenu.vue'
import GenericModal from '@/components/GenericModal.vue'
// 复核 P1-9: 低频模态懒加载(打开时才拉取), 首屏只保留网关/登录/通用弹窗
const TableDesignerModal = defineAsyncComponent(() => import('@/components/TableDesignerModal.vue'))
const RoutineModal = defineAsyncComponent(() => import('@/components/RoutineModal.vue'))
const TaskModal = defineAsyncComponent(() => import('@/components/TaskModal.vue'))

const router = useRouter()
const connStore = useConnectionStore()
const authStore = useAuthStore()
const showGateway = ref(false)
const showAuth = ref(false)
const config = ref<ConfigResp | null>(null)

// 401 回调: 弹登录弹窗
authStore.setUnauthorizedHandler(() => { showAuth.value = true })

// 403 强制改密回调: 业务请求被拦截时置位并弹改密窗
authStore.setMustChangeHandler(() => { authStore.mustChangePwd = true; showAuth.value = true })

onMounted(async () => {
  await connStore.initConfig() // 先取配置(网关/认证状态)
  await authStore.restore()    // 恢复登录态(经 /api/config, 令牌不持久化)
  // 网关未验证 → 弹网关弹窗
  if (connStore.gatewayRequired) {
    showGateway.value = true
    return
  }
  // 账号体系启用 & 未登录 → 弹登录弹窗
  if (connStore.authRequired && !authStore.isLoggedIn) {
    showAuth.value = true
  }
  // 已登录但需强制改密(刷新场景) → 弹强制改密窗
  if (authStore.isLoggedIn && authStore.mustChangePwd) {
    showAuth.value = true
  }
})

function onGatewayDone() {
  showGateway.value = false
  // 网关通过后重新加载, 拿到完整 /api/config
  location.reload()
}

function onAuthDone() {
  showAuth.value = false
  connStore.refreshConnList() // 登录后按当前用户重新拉连接列表(可见性过滤)
  // 登录成功, 若未连接则留在连接面板
  if (!connStore.connected) router.push('/')
}
</script>

<template>
  <!-- 全局顶栏(连接页/主界面都有): 标题/我的连接/主题/登录 -->
  <AppHeader />
  <!-- 弹窗组件内部用 :show 控制显隐、emit('close') 关闭(与 App 的 v-if 配合) -->
  <GatewayModal :show="showGateway" @close="showGateway = false" />
  <AuthModal :show="showAuth" :force="authStore.mustChangePwd" @close="onAuthDone" />
  <GenericModal />
  <TableDesignerModal />
  <RoutineModal />
  <TaskModal />
  <CtxMenu />
  <RouterView />
</template>