// @vitest-environment jsdom
// 回归测试: 验证查询构建器打开后, "选择列"区域的列名确实渲染进 DOM(.qb-col-name 文本存在)。
// 用于区分"数据层未填充(列名根本没渲染)" vs "样式层文字色与背景同色(渲染了但看不见)"。
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import QueryBuilderModal from '@/components/QueryBuilderModal.vue'
import { useUIStore } from '@/stores/ui'
import { useDatabaseStore } from '@/stores/database'

vi.mock('@/api/database', () => ({
  getColumns: vi.fn(async () => [
    { name: 'id', type: 'INTEGER' },
    { name: 'username', type: 'TEXT' },
    { name: 'created_at', type: 'DATETIME' },
  ]),
}))

describe('QueryBuilderModal 列名渲染', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('打开后选择列区域渲染列名文本', async () => {
    const ui = useUIStore()
    const db = useDatabaseStore()
    db.$patch({ tables: [{ schema: '', name: 'users', type: 'Table' }] })
    const w = mount(QueryBuilderModal, { global: { stubs: { teleport: true } } })
    ui.queryBuilder = true
    await nextTick()
    await flushPromises()
    await nextTick()
    const names = w.findAll('.qb-col-name').map((e) => e.text())
    // eslint-disable-next-line no-console
    console.log('RENDERED qb-col-name texts:', JSON.stringify(names))
    expect(names).toContain('id')
    expect(names).toContain('username')
    expect(names).toContain('created_at')
    w.unmount()
  })

  it('空 schema(sQLite 等)也能加载列(s!= 非空不再拦截)', async () => {
    const ui = useUIStore()
    const db = useDatabaseStore()
    db.$patch({ tables: [{ schema: '', name: 'users', type: 'Table' }] })
    const w = mount(QueryBuilderModal, { global: { stubs: { teleport: true } } })
    ui.queryBuilder = true
    await nextTick()
    await flushPromises()
    await nextTick()
    const names = w.findAll('.qb-col-name').map((e) => e.text())
    expect(names.length).toBe(3)
    w.unmount()
  })
})
