// 危险操作确认(P1-10): 替代原生 confirm(), 红色主按钮 + 明确文案 + 二次确认语义。
// 复用 ui.showModal(GenericModal 渲染, DOMPurify 净化), 返回 Promise<boolean>。
import { useUIStore } from '@/stores/ui'
import { esc } from '@/utils/sqlIdent'

export function confirmDanger(message: string, title = '确认操作'): Promise<boolean> {
  const ui = useUIStore()
  return new Promise(resolve => {
    ui.showModal(`<h3>${esc(title)}</h3>
      <p style="color:var(--text2,#86909c);font-size:13px;margin:8px 0 16px;white-space:pre-wrap">${esc(message)}</p>
      <div class="acts">
        <button class="sm" data-call="__cfCancel">取消</button>
        <button class="sm danger" style="background:#d54941;border-color:#d54941;color:#fff" data-call="__cfOk">确认执行</button>
      </div>`)
    ;(window as unknown as Record<string, unknown>).__cfCancel = () => { ui.closeModal(); resolve(false) }
    ;(window as unknown as Record<string, unknown>).__cfOk = () => { ui.closeModal(); resolve(true) }
  })
}
