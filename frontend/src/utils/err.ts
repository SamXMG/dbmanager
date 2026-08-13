// 统一错误信息提取(优化路线图 2.1 类型契约): catch(e: unknown) 后的类型收窄
export function errMsg(e: unknown, fallback = '操作失败'): string {
  if (e instanceof Error) return e.message
  if (typeof e === 'string' && e) return e
  return fallback
}
