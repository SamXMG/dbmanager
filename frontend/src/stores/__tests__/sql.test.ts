// SQL 工作台纯函数单测: 格式化(关键字换行/AND·OR 缩进/大小写归一)
import { describe, it, expect } from 'vitest'
import { formatSqlText } from '@/stores/sql'

describe('formatSqlText SQL 格式化', () => {
  it('SELECT/FROM/WHERE 各自换行且关键字大写', () => {
    const out = formatSqlText('select id, name from emp where age > 30')
    expect(out).toMatch(/^SELECT\s/m)          // 首行大写
    expect(out).toContain('\nFROM')
    expect(out).toContain('\nWHERE')
    expect(out).toMatch(/\bSELECT\b/)          // 关键字大写归一
  })

  it('复合关键字(LEFT JOIN/ORDER BY)不被拆散', () => {
    const out = formatSqlText('select * from a left join b on a.id = b.id order by a.id')
    expect(out).toContain('\nLEFT JOIN')
    expect(out).not.toMatch(/\nLEFT\b(?! JOIN)/)
    expect(out).toContain('\nORDER BY')
    expect(out).not.toMatch(/\nORDER\b(?! BY)/)
  })

  it('AND/OR 缩进两空格', () => {
    const out = formatSqlText('select * from t where a = 1 and b = 2 or c = 3')
    expect(out).toContain('\n  AND')
    expect(out).toContain('\n  OR')
  })

  it('连续空白与空行收敛', () => {
    const out = formatSqlText('select   id   from  t')
    expect(out).not.toMatch(/[ \t]+\n/)
    expect(out).not.toMatch(/\n{2,}/)
  })

  it('空输入安全返回', () => {
    expect(formatSqlText('')).toBe('')
    expect(formatSqlText('   ')).toBe('')
  })

  it('UPDATE/SET/VALUES 换行', () => {
    const out = formatSqlText('update t set a = 1 where id = 2')
    expect(out).toMatch(/^UPDATE\s/m)
    expect(out).toContain('\nSET')
    expect(out).toContain('\nWHERE')
  })
})
