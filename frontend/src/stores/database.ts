// 数据库 store(阶段 2 完整): 表/库/存储过程数据 + 树懒加载
// 对应旧前端 tree.js 的 TABLES/FULL_TABLES/DBS/curDb/ROUTINES + treeCache 逻辑
import { defineStore } from 'pinia'
import { getObjects, listRoutines, type TableInfo, type RoutineInfo } from '@/api/database'
import { useConnectionStore } from '@/stores/connection'

export interface DbObjects {
  tables: TableInfo[]
  routines: RoutineInfo[]
}

export const useDatabaseStore = defineStore('database', {
  state: () => ({
    tables: [] as TableInfo[],          // 连接库的表(连接时全量)
    databases: [] as string[],          // 库列表(树一级节点)
    curDb: '' as string,                // 当前选库(SQL 目标库联动)
    routines: [] as RoutineInfo[],      // 连接库的存储过程/函数/触发器
    treeCache: {} as Record<string, DbObjects>, // 按库懒加载缓存
    expanded: new Set<string>(),        // 展开状态(库节点)
  }),
  getters: {
    /** 库对象(缓存命中或空) */
    dbObjects: (s) => (db: string): DbObjects | undefined => s.treeCache[db],
  },
  actions: {
    /** 连接成功后装载表数据(连接库名优先 + 后端全部库, 对齐旧 treeDbList) */
    loadTables(tables: TableInfo[], databases?: string[]) {
      this.tables = tables || []
      const connStore = useConnectionStore()
      const cur = connStore.conn?.database
        || (tables || [])[0]?.schema
        || ''
      // 库列表: 连接库优先 + /api/databases 全部去重; 无则回退 schema 推导
      let dbs: string[] = []
      if (databases && databases.length) dbs = [...databases]
      else dbs = [...new Set((tables || []).map(t => t.schema).filter(Boolean) as string[])]
      if (cur && !dbs.includes(cur)) dbs.unshift(cur)
      this.databases = dbs
      this.curDb = ''
      this.routines = []
      this.treeCache = {}
      this.expanded = new Set()
    },

    /** 树懒加载: 连接库直接用内存 TABLES(秒开); 其他库走 /api/objects(缓存; force=右键刷新强制重拉) */
    async loadObjects(db: string, force = false): Promise<DbObjects | null> {
      const connStore = useConnectionStore()
      const cur = connStore.conn?.database
        || this.tables[0]?.schema
        || ''
      if (db === cur) {
        // 连接库: 内存数据, 不请求
        const obj: DbObjects = { tables: this.tables, routines: this.routines }
        this.treeCache[db] = obj
        return obj
      }
      if (!force && this.treeCache[db]) return this.treeCache[db]
      try {
        const d = await getObjects(db)
        const obj: DbObjects = { tables: d.tables || [], routines: d.routines || [] }
        this.treeCache[db] = obj
        return obj
      } catch {
        this.treeCache[db] = { tables: [], routines: [] }
        return null
      }
    },

    /** 加载连接库的存储过程(树分组用) */
    async loadRoutines() {
      try {
        this.routines = await listRoutines()
      } catch {
        this.routines = []
      }
    },

    /** 切换当前库(SQL 目标库联动) */
    switchDb(db: string) {
      this.curDb = db
    },

    /** 展开/折叠库节点 */
    toggleDb(db: string) {
      if (this.expanded.has(db)) this.expanded.delete(db)
      else this.expanded.add(db)
    },
  },
})

/** 便捷: 从 connection store 同步表数据 */
export function syncTablesFromConnection() {
  const connStore = useConnectionStore()
  const dbStore = useDatabaseStore()
  dbStore.loadTables(connStore.tables, connStore.databases)
}
