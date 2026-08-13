// 危险操作确认(P1-10): 替代原生 confirm(), 红色主按钮 + 明确文案 + 二次确认语义。
// 改为 Vue 原生动态组件弹窗: ui.openModal('ConfirmModal', {...}) 渲染 ConfirmModal.vue,
// 彻底消除 HTML 字符串注入。返回 Promise<boolean>。
import { useUIStore } from '@/stores/ui'

export function confirmDanger(message: string, title = '确认操作'): Promise<boolean> {
  const ui = useUIStore()
  return new Promise<boolean>(resolve => {
    ui.openModal('ConfirmModal', { title, message, danger: true, resolve })
  })
}
