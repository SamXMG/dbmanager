<script setup lang="ts">
// CodeMirror 6 SQL 编辑器(阶段 4): v-model + 语法高亮 + 方案 B 补全 + Ctrl+Enter 执行 + 主题切换
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { EditorState, Compartment } from '@codemirror/state'
import { EditorView, keymap, lineNumbers, highlightActiveLine, drawSelection } from '@codemirror/view'
import { defaultKeymap, history, historyKeymap } from '@codemirror/commands'
import { autocompletion, closeBrackets } from '@codemirror/autocomplete'
import { sql, MySQL, PostgreSQL, MSSQL, SQLite } from '@codemirror/lang-sql'
import { HighlightStyle, syntaxHighlighting } from '@codemirror/language'
import { tags as t } from '@lezer/highlight'
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

// 编辑器主题: 显式绑定应用主题 token, 确保浅色/深色下背景与文字都与整体主题一致
// (修复: 旧 lightTheme 不设背景, CodeMirror 在浅色下会继承到深色容器背景)
const lightTheme = EditorView.theme({
  '&': { height: '100%', fontSize: '13px', backgroundColor: 'var(--panel)', color: 'var(--text)' },
  '.cm-scroller': { fontFamily: 'Consolas, "Cascadia Mono", monospace' },
  '.cm-gutters': { backgroundColor: 'var(--panel2)', color: 'var(--text3)', border: 'none' },
  '.cm-activeLine': { backgroundColor: 'var(--panel3)' },
  '.cm-activeLineGutter': { backgroundColor: 'var(--panel3)' },
  '.cm-cursor': { borderLeftColor: 'var(--text)' },
  '.cm-selectionBackground, &.cm-focused .cm-selectionBackground, ::selection': { backgroundColor: 'var(--primary-bg)' },
}, { dark: false })
const darkTheme = EditorView.theme({
  '&': { height: '100%', fontSize: '13px', backgroundColor: 'var(--panel)', color: 'var(--text)' },
  '.cm-scroller': { fontFamily: 'Consolas, "Cascadia Mono", monospace' },
  '.cm-gutters': { backgroundColor: 'var(--panel2)', color: 'var(--text3)', border: 'none' },
  '.cm-activeLine': { backgroundColor: 'var(--panel3)' },
  '.cm-activeLineGutter': { backgroundColor: 'var(--panel3)' },
  '.cm-cursor': { borderLeftColor: 'var(--text)' },
  '.cm-selectionBackground, &.cm-focused .cm-selectionBackground, ::selection': { backgroundColor: 'var(--primary-bg)' },
}, { dark: true })

// 语法高亮(浅色/深色各一套, 经 Compartment 随主题切换)
const lightHighlight = HighlightStyle.define([
  { tag: t.keyword, color: '#1677ff', fontWeight: '600' },
  { tag: [t.string, t.special(t.string)], color: '#389e0d' },
  { tag: [t.number, t.bool, t.null], color: '#d4380d' },
  { tag: t.comment, color: '#8c8c8c', fontStyle: 'italic' },
  { tag: [t.operator, t.punctuation], color: '#595959' },
  { tag: [t.typeName, t.className], color: '#531dab' },
  { tag: [t.function(t.variableName), t.labelName], color: '#08979c' },
])
const darkHighlight = HighlightStyle.define([
  { tag: t.keyword, color: '#6ea8fe', fontWeight: '600' },
  { tag: [t.string, t.special(t.string)], color: '#7ee787' },
  { tag: [t.number, t.bool, t.null], color: '#ffa657' },
  { tag: t.comment, color: '#8b949e', fontStyle: 'italic' },
  { tag: [t.operator, t.punctuation], color: '#c9d1d9' },
  { tag: [t.typeName, t.className], color: '#d2a8ff' },
  { tag: [t.function(t.variableName), t.labelName], color: '#56d4dd' },
])

function themesFor(theme: 'light' | 'dark') {
  return theme === 'dark'
    ? [darkTheme, syntaxHighlighting(darkHighlight)]
    : [lightTheme, syntaxHighlighting(lightHighlight)]
}

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
      themeComp.of(themesFor(uiStore.theme)),
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
  view?.dispatch({ effects: themeComp.reconfigure(themesFor(t)) })
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
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel);
}
</style>
