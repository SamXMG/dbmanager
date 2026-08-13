// @vitest-environment jsdom
// GenericModal 回归测试: 验证动态组件渲染架构(ui.openModal(name, props) -> <component :is> 渲染注册组件)。
// 旧版 ui.showModal(html) + data-action/data-call + window.__ 注入机制已彻底移除。
import { describe, it, expect, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import GenericModal from '@/components/GenericModal.vue'
import { useUIStore } from '@/stores/ui'

describe('GenericModal 动态组件渲染', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('未打开弹窗时不渲染任何组件', async () => {
    const ui = useUIStore()
    const w = mount(GenericModal, { global: { stubs: { teleport: true } } })
    await flushPromises()
    expect(ui.modal).toBeNull()
    expect(w.find('.g-modal').exists()).toBe(false)
    w.unmount()
  })

  it('openModal 渲染注册组件 ConfirmModal 且取消按钮关闭并 resolve(false)', async () => {
    const ui = useUIStore()
    const w = mount(GenericModal, { global: { stubs: { teleport: true } } })
    let result: boolean | null = null
    ui.openModal('ConfirmModal', { title: 'T', message: 'M?', danger: true, resolve: (ok: boolean) => { result = ok } })
    await flushPromises()
    expect(w.find('.g-modal').exists()).toBe(true)
    expect(w.text()).toContain('M?')
    const btns = w.findAll('.g-modal button')
    await btns[0].trigger('click') // 取消
    await flushPromises()
    expect(ui.modal).toBeNull()
    expect(result).toBe(false)
    w.unmount()
  })

  it('ConfirmModal 确认按钮触发 resolve(true) 并关闭', async () => {
    const ui = useUIStore()
    const w = mount(GenericModal, { global: { stubs: { teleport: true } } })
    let result: boolean | null = null
    ui.openModal('ConfirmModal', { message: 'M?', resolve: (ok: boolean) => { result = ok } })
    await flushPromises()
    const btns = w.findAll('.g-modal button')
    await btns[btns.length - 1].trigger('click') // 确认执行
    await flushPromises()
    expect(ui.modal).toBeNull()
    expect(result).toBe(true)
    w.unmount()
  })

  it('打开未知组件名时不渲染(防御)', async () => {
    const ui = useUIStore()
    const w = mount(GenericModal, { global: { stubs: { teleport: true } } })
    ui.openModal('__NoSuchModal__', {})
    await flushPromises()
    expect(w.find('.g-modal').exists()).toBe(false)
    ui.closeModal()
    w.unmount()
  })
})
