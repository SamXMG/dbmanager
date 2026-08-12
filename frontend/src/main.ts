import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { useUIStore } from './stores/ui'
import './assets/styles.css' // 现有 css/style.css 原样搬入(CSS 变量 + [data-theme] 主题)

// 迁移版入口: Pinia + Router; 不引框架级 UI 库, 组件手写
const app = createApp(App)
app.use(createPinia())
app.use(router)
// 主题初始化(读 localStorage + 应用 body[data-theme])
const uiStore = useUIStore()
uiStore.initTheme()
// 通用弹窗辅助(showModal 注入的 innerHTML 里 onclick 引用; 迁移过渡期保留)
;(window as any).closeModal = () => uiStore.closeModal()
app.mount('#app')
