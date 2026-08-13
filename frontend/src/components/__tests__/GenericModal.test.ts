// @vitest-environment jsdom
// GenericModal 回归测试: 弹窗关闭/取消按钮必须可用(CSP script-src 'self' 禁内联事件处理器后,
// 按钮改 data-action/data-call 声明式 + 组件内事件委托; P0-5 DOMPurify 默认白名单净化)
import { describe, it, expect, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import GenericModal from '@/components/GenericModal.vue'
import { useUIStore } from '@/stores/ui'

describe('GenericModal 事件委托: 按钮可关闭弹窗', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('data-action="close" 关闭按钮可关闭', async () => {
    const ui = useUIStore()
    const w = mount(GenericModal, { global: { stubs: { teleport: true } } })
    ui.showModal('<h3>测试</h3><div class="acts"><button data-action="close">取消</button></div>')
    await flushPromises()
    const btn = w.find('.g-modal button')
    expect(btn.exists()).toBe(true)
    await btn.trigger('click')
    await flushPromises()
    expect(ui.modal).toBeNull()
    w.unmount()
  })

  it('data-call 确认按钮可触发 window 回调并关闭', async () => {
    const ui = useUIStore()
    let called = false
    ;(window as unknown as Record<string, unknown>).__testOk = () => { called = true; ui.closeModal() }
    const w = mount(GenericModal, { global: { stubs: { teleport: true } } })
    ui.showModal('<button data-call="__testOk">确认</button>')
    await flushPromises()
    await w.find('.g-modal button').trigger('click')
    await flushPromises()
    expect(called).toBe(true)
    expect(ui.modal).toBeNull()
    w.unmount()
  })

  it('confirmDanger 取消按钮关闭且不触发确认回调', async () => {
    const ui = useUIStore()
    let ok = false
    ;(window as unknown as Record<string, unknown>).__cfCancel = () => { ui.closeModal() }
    ;(window as unknown as Record<string, unknown>).__cfOk = () => { ok = true; ui.closeModal() }
    const w = mount(GenericModal, { global: { stubs: { teleport: true } } })
    ui.showModal('<div class="acts"><button class="sm" data-call="__cfCancel">取消</button><button data-call="__cfOk">确认执行</button></div>')
    await flushPromises()
    const btns = w.findAll('.g-modal button')
    expect(btns.length).toBe(2)
    await btns[0].trigger('click')
    await flushPromises()
    expect(ui.modal).toBeNull()
    expect(ok).toBe(false)
    w.unmount()
  })

  it('data-action="remove" 删除条件行容器', async () => {
    const ui = useUIStore()
    const w = mount(GenericModal, { global: { stubs: { teleport: true } } })
    ui.showModal('<div class="row2"><button data-action="remove">✕</button></div>')
    await flushPromises()
    await w.find('.g-modal button').trigger('click')
    await flushPromises()
    expect(w.find('.g-modal .row2').exists()).toBe(false)
    w.unmount()
  })

  it('DOMPurify 默认白名单剔除内联事件(script/onclick)但保留按钮', async () => {
    const ui = useUIStore()
    const w = mount(GenericModal, { global: { stubs: { teleport: true } } })
    ui.showModal('<button data-action="close">关</button><script>alert(1)</script><button onclick="alert(1)">X</button>')
    await flushPromises()
    const g = w.find('.g-modal')
    const html = g.html()
    expect(html).not.toContain('<script')
    expect(html).not.toContain('onclick=')
    expect(g.findAll('button').length).toBe(2) // 两个按钮都保留(data-action 与无属性按钮)
    w.unmount()
  })
})
