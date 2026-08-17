// 弹窗卡片：可拖拽移动位置 + 右下角可缩放大小。
// 从 GenericModal 的 enhanceCard 抽出为可复用能力，供旧弹窗体系(指令 v-draggable-modal)复用。
// 约束: 设计令牌走 CSS 变量(与全局主题一致)，不硬编码颜色；拖拽手柄为纯 CSS 图形，不使用 emoji 图标。
import type { Directive } from 'vue'

type Cleanup = () => void
interface DraggableEl extends HTMLElement {
  __dmCleanup?: Cleanup
}

// 增强一个卡片元素: 固定定位居中 + 注入拖动条/缩放手柄 + 绑定鼠标事件。
// 返回清理函数(移除监听与注入元素)。同一元素重复调用由 dataset.dragEnhanced 幂等守卫。
export function applyDragResize(card: HTMLElement): Cleanup {
  if (card.dataset.dragEnhanced) return () => {}
  card.dataset.dragEnhanced = '1'

  const vw = window.innerWidth
  const vh = window.innerHeight
  const w = Math.min(card.offsetWidth, vw - 24)
  const h = Math.min(card.offsetHeight, vh * 0.86)
  card.style.position = 'fixed'
  card.style.width = w + 'px'
  card.style.height = h + 'px'
  card.style.maxHeight = 'none'
  card.style.left = Math.max(12, (vw - w) / 2) + 'px'
  card.style.top = Math.max(12, (vh - h) / 2) + 'px'

  // 顶部居中拖动提示条(也可在卡片任意非交互区拖动)
  const hint = document.createElement('div')
  hint.className = 'dm-drag-hint'
  hint.title = '拖动移动窗口'
  card.appendChild(hint)

  // 右下角缩放手柄
  const rz = document.createElement('div')
  rz.className = 'dm-resizer'
  rz.title = '拖动调整大小'
  card.appendChild(rz)

  const el = card
  let mode: 'drag' | 'resize' | null = null
  let sx = 0, sy = 0, ol = 0, ot = 0, ow = 0, oh = 0

  function onDown(e: MouseEvent) {
    const t = e.target as HTMLElement
    if (t.classList.contains('dm-resizer')) mode = 'resize'
    else {
      // 命中交互元素(按钮/输入等)仍走正常交互, 不触发拖动
      if (t.closest('button,input,textarea,select,a,[contenteditable],.tbl-scroll,.scroll,.no-drag')) return
      mode = 'drag'
    }
    sx = e.clientX; sy = e.clientY
    ol = el.offsetLeft; ot = el.offsetTop; ow = el.offsetWidth; oh = el.offsetHeight
    document.body.style.userSelect = 'none'
    e.preventDefault()
  }
  function onMove(e: MouseEvent) {
    if (!mode) return
    if (mode === 'drag') {
      const nl = Math.max(6, Math.min(ol + e.clientX - sx, window.innerWidth - el.offsetWidth - 6))
      const nt = Math.max(6, Math.min(ot + e.clientY - sy, window.innerHeight - el.offsetHeight - 6))
      el.style.left = nl + 'px'; el.style.top = nt + 'px'
    } else {
      const nw = Math.max(320, Math.min(ow + e.clientX - sx, window.innerWidth - 24))
      const nh = Math.max(180, Math.min(oh + e.clientY - sy, window.innerHeight - 24))
      el.style.width = nw + 'px'; el.style.height = nh + 'px'
    }
  }
  function onUp() { mode = null; document.body.style.userSelect = '' }

  el.addEventListener('mousedown', onDown)
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)

  return () => {
    el.removeEventListener('mousedown', onDown)
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
    hint.remove(); rz.remove(); delete card.dataset.dragEnhanced
  }
}

// 全局指令: 挂到任意弹窗卡片根元素即可获得拖动+缩放能力(如 v-draggable-modal)。
export const draggableModal: Directive<HTMLElement> = {
  mounted(el: HTMLElement) {
    // 等下一帧确保布局完成(offsetWidth/offsetHeight 取到真实尺寸)
    requestAnimationFrame(() => {
      ;(el as DraggableEl).__dmCleanup = applyDragResize(el)
    })
  },
  unmounted(el: HTMLElement) {
    ;(el as DraggableEl).__dmCleanup?.()
    delete (el as DraggableEl).__dmCleanup
  },
}
