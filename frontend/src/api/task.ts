// 调度任务 API(P2-2): 定时备份
import { get, post } from './client'

export interface TaskInfo {
  id: number
  name: string
  action: string
  conn_name: string
  interval_min: number
  enabled: boolean
  last_run?: number | null
  last_result?: string | null
  next_run?: number | null
}

export const listTasks = () => get<{ tasks: TaskInfo[] }>('/api/tasks')
export const createTask = (body: { name: string; conn_name: string; interval_min: number; action?: string }) =>
  post<TaskInfo>('/api/tasks', body)
export const deleteTask = (id: number) => post<{ ok?: boolean }>('/api/tasks/delete', { id })
export const toggleTask = (id: number, enabled: boolean) =>
  post<{ ok?: boolean }>('/api/tasks/toggle', { id, enabled })
export const runTask = (id: number) =>
  post<{ ok?: boolean; error?: string; file?: string }>('/api/tasks/run', { id })
