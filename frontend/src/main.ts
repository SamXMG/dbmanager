import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { useUIStore } from './stores/ui'
import { setLocale, getLocale } from '@/i18n'
import './assets/styles.css' // 现有 css/style.css 原样搬入(CSS 变量 + [data-theme] 主题)

// 迁移版入口: Pinia + Router; 不引框架级 UI 库, 组件手写
const app = createApp(App)
app.use(createPinia())
app.use(router)
// 主题初始化(读 localStorage + 应用 body[data-theme])
const uiStore = useUIStore()
uiStore.initTheme()
// 应用初始语言到 <html lang>(语言偏好持久化在 localStorage 的 dbm_lang)
setLocale(getLocale())
// 通用弹窗辅助(showModal 注入的 innerHTML 里 data-action="close" 经事件委托关闭; 兼容旧内联引用)
;(window as unknown as Record<string, unknown>).closeModal = () => uiStore.closeModal()
app.mount('#app')
