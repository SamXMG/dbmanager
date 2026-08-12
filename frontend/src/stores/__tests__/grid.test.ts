// 网格核心逻辑单测: 方言引用 / 值转义 / WHERE 注入防护 / 排序组合
// 前端核心防注入逻辑的回归测试
import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useGridStore, quoteIdent, quoteSql } from '@/stores/grid'
import { useConnectionStore } from '@/stores/connection'

describe('quoteIdent 方言列引用', () => {
  it('mssql 用方括号', () => {
    expect(quoteIdent('mssql', 'col')).toBe('[col]')
  })
  it('mysql/mariadb/oceanbase/tidb 用反引号', () => {
    expect(quoteIdent('mysql', 'col')).toBe('`col`')
    expect(quoteIdent('mariadb', 'col')).toBe('`col`')
    expect(quoteIdent('oceanbase', 'col')).toBe('`col`')
    expect(quoteIdent('tidb', 'col')).toBe('`col`')
  })
  it('postgresql/sqlite/oracle/默认 用双引号', () => {
    expect(quoteIdent('postgresql', 'col')).toBe('"col"')
    expect(quoteIdent('sqlite', 'col')).toBe('"col"')
    expect(quoteIdent('oracle', 'col')).toBe('"col"')
    expect(quoteIdent('', 'col')).toBe('"col"')
  })
})

describe('quoteSql 值转义(注入防护)', () => {
  it('普通值包单引号', () => {
    expect(quoteSql('abc')).toBe("'abc'")
  })
  it('单引号翻倍转义', () => {
    expect(quoteSql("O'Reilly")).toBe("'O''Reilly'")
  })
  it('注入载荷被中和(全部单引号翻倍, 无法闭合)', () => {
    const evil = "' OR '1'='1"
    // quoteSql = 包裹引号 + 内容单引号翻倍: 输入以引号开头结尾 → 输出首尾各两个引号
    expect(quoteSql(evil)).toBe("''' OR ''1''=''1'")
    expect(quoteSql(evil).includes("1'='1")).toBe(false)   // 原始注入片段不复现
  })
})

describe('grid store buildWhere 注入防护', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('空筛选返回空串', () => {
    const g = useGridStore()
    expect(g.buildWhere()).toBe('')
  })

  it('eq 条件按方言引用列 + 转义值', () => {
    const connStore = useConnectionStore()
    connStore.conn = { db_type: 'postgresql' } as any   // 双引号方言
    const g = useGridStore()
    g.filters = { name: { op: 'eq', val: "O'Reilly" } }
    expect(g.buildWhere()).toBe('"name" = \'O\'\'Reilly\'')
  })

  it('contains 生成 LIKE 并转义值中的引号', () => {
    const connStore = useConnectionStore()
    connStore.conn = { db_type: 'postgresql' } as any
    const g = useGridStore()
    g.filters = { title: { op: 'contains', val: "a'b" } }
    expect(g.buildWhere()).toBe('"title" LIKE \'%a\'\'b%\'')
  })

  it('isnull/isnotnull 无值注入(方言无关)', () => {
    const g = useGridStore()
    g.filters = { a: { op: 'isnull', val: '' }, b: { op: 'isnotnull', val: '' } }
    const w = g.buildWhere()
    expect(w).toContain('IS NULL')
    expect(w).toContain('IS NOT NULL')
    expect(w).not.toContain("'")   // 无值注入面
  })

  it('mysql 方言走反引号(连接类型联动)', () => {
    const connStore = useConnectionStore()
    connStore.conn = { db_type: 'mysql' } as any
    const g = useGridStore()
    g.filters = { name: { op: 'eq', val: 'x' } }
    expect(g.buildWhere()).toBe('`name` = \'x\'')
  })

  it('buildOrder 输出 col:dir 格式', () => {
    const g = useGridStore()
    expect(g.buildOrder()).toBe('')
    g.sort = { col: 'salary', dir: 'desc' }
    expect(g.buildOrder()).toBe('salary:desc')
    g.sort = { col: 'id', dir: 'asc' }
    expect(g.buildOrder()).toBe('id:asc')
  })
})
