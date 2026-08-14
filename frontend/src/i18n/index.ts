// 轻量 i18n(无第三方依赖): 语言持久化到 localStorage(dbm_lang), 默认 zh-CN。
// 用法: import { tr, getLocale, setLocale } from '@/i18n'
//   tr('header.login')            // 当前语言
//   tr('common.deleted_n', { n: 3 }) // 带参数替换 {n}
// 新增文案: 加 key 到 locales/zh-CN.ts(源) 与 locales/en.ts(译文), 模板用 tr('key') 取代硬编码串。
// 注意: 函数命名为 tr(而非 t), 因为 t 在本项目常作"表名"参数/循环变量, 易遮蔽。
import { ref } from 'vue'
import { zhCN } from './locales/zh-CN'
import { en } from './locales/en'

export type Lang = 'zh-CN' | 'en'
const SUPPORTED: Lang[] = ['zh-CN', 'en']
const STORAGE_KEY = 'dbm_lang'
const FALLBACK: Lang = 'zh-CN'

const catalogs: Record<Lang, Record<string, string>> = {
  'zh-CN': zhCN,
  en,
}

function loadInitial(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY) as Lang | null
    if (saved && (SUPPORTED as string[]).includes(saved)) return saved
  } catch {
    /* localStorage 不可用(隐私模式等)时回退默认 */
  }
  return FALLBACK
}

// ref 使语言切换触发使用 t() 的组件重新渲染
const current = ref<Lang>(loadInitial())

export function getLocale(): Lang {
  return current.value
}

export function setLocale(lang: Lang): void {
  if (!(SUPPORTED as string[]).includes(lang)) return
  current.value = lang
  try {
    localStorage.setItem(STORAGE_KEY, lang)
  } catch {
    /* 忽略持久化失败 */
  }
  document.documentElement.lang = lang === 'en' ? 'en' : 'zh-CN'
}

export function tr(key: string, params?: Record<string, string | number>): string {
  const cat = catalogs[current.value] || catalogs[FALLBACK]
  let text = cat[key] ?? catalogs[FALLBACK][key] ?? key
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      text = text.replace(new RegExp(`\\{${k}\\}`, 'g'), String(v))
    }
  }
  return text
}
