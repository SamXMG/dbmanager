import { createRouter, createWebHashHistory } from 'vue-router'

// hash 模式(createWebHashHistory): URL 形如 /v2#/main, 后端只 serve /v2 一个入口,
// 刷新不 404(hash 部分不会发到后端), 后端零改动
const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'conn', component: () => import('@/layouts/ConnPanel.vue') },
    { path: '/main', name: 'main', component: () => import('@/layouts/MainLayout.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

export default router
