<script setup lang="ts">
// CodeMirror 6 SQL 编辑器(阶段 4): v-model + 语法高亮 + 方案 B 补全 + Ctrl+Enter 执行 + 主题切换
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { EditorState, Compartment } from '@codemirror/state'
import { EditorView, keymap, lineNumbers, highlightActiveLine, drawSelection } from '@codemirror/view'
import { defaultKeymap, history, historyKeymap } from '@codemirror/commands'
import { autocompletion, closeBrackets } from '@codemirror/autocomplete'
import { sql, MySQL, PostgreSQL, MSSQL, SQLite } from '@codemirror/lang-sql'
import { createSqlCompletionSource } from '@/completions/sqlCompletion'
import { useConnectionStore } from '@/stores/connection'
import { useDatabaseStore } from '@/stores/database'
import { useTabStore } from '@/stores/tab'
import { useUIStore } from '@/stores/ui'

const props = defineProps<{ modelValue: string; dialect?: string }>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: string): void
  (e: 'exec'): void
  (e: 'format'): void
}>()

const host = ref<HTMLDivElement | null>(null)
let view: EditorView | null = null
const themeComp = new Compartment()

const connStore = useConnectionStore()
const dbStore = useDatabaseStore()
const tabStore = useTabStore()
const uiStore = useUIStore()

// 方言映射: db_type -> lang-sql dialect
function langDialect(d: string) {
  switch ((d || '').toLowerCase()) {
    case 'mssql': return MSSQL
    case 'postgresql': case 'kingbase': return PostgreSQL
    case 'sqlite': return SQLite
    default: return MySQL // mysql/mariadb/oceanbase/tidb
  }
}

// 方案 B 补全数据源: 从 store 动态取(阶段 2/3 填充后自动生效, 当前空数组兜底)
const completionSource = createSqlCompletionSource(() => ({
  dbType: connStore.conn?.db_type || 'mysql',
  tables: dbStore.tables,
  columns: (tabStore.currentMeta?.columns as { name: string; type?: string }[]) || [],
}))

const lightTheme = EditorView.theme({
  '&': { height: '100%', fontSize: '13px' },
  '.cm-scroller': { fontFamily: 'Consolas, "Cascadia Mono", monospace' },
})
const darkTheme = EditorView.theme({
  '&': { height: '100%', fontSize: '13px', backgroundColor: '#1e1e1e', color: '#d4d4d4' },
  '.cm-scroller': { fontFamily: 'Consolas, "Cascadia Mono", monospace' },
  '.cm-gutters': { backgroundColor: '#252526', color: '#858585', border: 'none' },
  '.cm-activeLine': { backgroundColor: 'rgba(255,255,255,0.05)' },
  '.cm-activeLineGutter': { backgroundColor: 'rgba(255,255,255,0.08)' },
})

onMounted(() => {
  if (!host.value) return
  const state = EditorState.create({
    doc: props.modelValue || '',
    extensions: [
      lineNumbers(),
      highlightActiveLine(),
      drawSelection(),
      history(),
      closeBrackets(),
      autocompletion({ override: [completionSource], activateOnTyping: true }),
      sql({ dialect: langDialect(props.dialect || connStore.conn?.db_type || 'mysql') }),
      keymap.of([
        { key: 'Mod-Enter', run: () => { emit('exec'); return true } },
        { key: 'Mod-Shift-f', run: () => { emit('format'); return true } },
        ...defaultKeymap,
        ...historyKeymap,
      ]),
      themeComp.of(uiStore.theme === 'dark' ? darkTheme : lightTheme),
      EditorView.updateListener.of(u => {
        if (u.docChanged) emit('update:modelValue', u.state.doc.toString())
      }),
    ],
  })
  view = new EditorView({ state, parent: host.value })
})

onBeforeUnmount(() => { view?.destroy(); view = null })

// 外部 v-model 变化 -> 编辑器同步(避免光标/选区被重置的循环)
watch(() => props.modelValue, v => {
  if (!view) return
  if (v !== view.state.doc.toString()) {
    view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: v || '' } })
  }
})

// 主题切换: Compartment 动态替换, 不重载编辑器
watch(() => uiStore.theme, t => {
  view?.dispatch({ effects: themeComp.reconfigure(t === 'dark' ? darkTheme : lightTheme) })
})
</script>

<template>
  <div ref="host" class="sql-editor-host"></div>
</template>

<style scoped>
.sql-editor-host {
  height: 100%;
  min-height: 120px;
  overflow: hidden;
  border: 1px solid var(--border, #e4e7ed);
  border-radius: 6px;
}
</style>
