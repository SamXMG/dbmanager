// UI store: theme/transactionMode + toast/modal/ctxMenu 状态
import { defineStore } from 'pinia'

export interface Toast { id: number; msg: string; err?: boolean }

/** 右键菜单项: sep=分隔线; danger=红色危险项(对齐旧版 cm-item/cm-sep) */
export interface CtxItem {
  label?: string
  fn?: () => void
  danger?: boolean
  sep?: boolean
}

export const useUIStore = defineStore('ui', {
  state: () => ({
    theme: 'light' as 'light' | 'dark',
    transactionMode: false,
    view: 'browse' as 'browse' | 'sql',   // 主内容视图: 数据浏览 / SQL 工作台(对齐旧版 switchView)
    toasts: [] as Toast[],
    toastSeq: 0,
    modal: null as { name: string; props?: Record<string, unknown> } | null,  // 动态组件弹窗(GenericModal 按 name 渲染注册组件)
    ctxMenu: null as { x: number; y: number; items: CtxItem[] } | null,
    designer: null as { s: string; t: string } | null,  // 表设计器(TableDesignerModal 渲染)
    routine: null as { s: string; name: string; kind: string } | null,  // 存储过程/函数/触发器编辑器
    showTasks: false,  // 调度任务管理弹窗(TaskModal.vue)
    queryBuilder: false,  // 查询构建器模态(QueryBuilderModal.vue 消费)
    sqlEditorH: Number(localStorage.getItem('dbm_sql_ed_h') || 0),  // SQL 工作台编辑器高度(px, 0=用默认 30% 比例)
  }),
  actions: {
    /** 初始化主题(读 localStorage + 应用到 body) */
    initTheme() {
      try {
        this.theme = (localStorage.getItem('dbm_theme') as 'light' | 'dark') || 'light'
      } catch { /* 隐私模式 */ }
      document.body.dataset.theme = this.theme === 'dark' ? 'dark' : ''
    },
    toggleTheme() {
      this.theme = this.theme === 'dark' ? 'light' : 'dark'
      try { localStorage.setItem('dbm_theme', this.theme) } catch { /* */ }
      document.body.dataset.theme = this.theme === 'dark' ? 'dark' : ''
    },
    toggleTx() { this.transactionMode = !this.transactionMode },
    switchView(v: 'browse' | 'sql') { this.view = v },
    toast(msg: string, err = false) {
      const id = ++this.toastSeq
      this.toasts.push({ id, msg, err })
      setTimeout(() => {
        this.toasts = this.toasts.filter(t => t.id !== id)
      }, 2600)
    },
    /** 打开动态组件弹窗(取代旧版 ui.showModal(html) 注入式弹窗) */
    openModal(name: string, props?: Record<string, unknown>) { this.modal = { name, props } },
    closeModal() { this.modal = null },
    showCtxMenu(x: number, y: number, items: CtxItem[]) {
      this.ctxMenu = { x, y, items }
    },
    closeCtxMenu() { this.ctxMenu = null },

    /** 表设计器开关(TableDesignerModal.vue 消费) */
    openDesigner(s: string, t: string) { this.designer = { s, t } },
    closeDesigner() { this.designer = null },

    /** 存储过程/函数/触发器编辑器(RoutineModal.vue 消费) */
    openRoutine(s: string, name: string, kind: string) { this.routine = { s, name, kind } },
    closeRoutine() { this.routine = null },

    /** 查询构建器开关(QueryBuilderModal.vue 消费, 对齐 designer/routine 模式) */
    openQueryBuilder() { this.queryBuilder = true },
    closeQueryBuilder() { this.queryBuilder = false },

    /** SQL 工作台编辑器高度(px): 持久化, 切换视图/刷新不丢失; 0 表示使用默认 30% 比例 */
    setSqlEditorH(h: number) {
      this.sqlEditorH = Math.round(h)
      try { localStorage.setItem('dbm_sql_ed_h', String(this.sqlEditorH)) } catch { /* 隐私模式 */ }
    },
  },
})
