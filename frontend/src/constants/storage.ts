// 前端 localStorage 存储键集中管理(P1-9 去重: 原魔法字符串散落于 ui.ts/AppHeader.vue/grid.ts 等)
export const STORAGE_KEYS = {
  THEME: 'dbm_theme',
  PINNED_TABLES: 'dbm_pinned_tables',
  UI_STATE: 'dbm_ui_state',
  COL_WIDTH_PREFIX: 'dbm_colw|', // 列宽: dbm_colw|<db_type>|<server>|<database>|<schema>|<table>
} as const
