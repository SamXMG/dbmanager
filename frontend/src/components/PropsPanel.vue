<script setup lang="ts">
// 右侧属性面板: 选中表显示对象信息 + 字段表 + 索引(对齐旧版 renderProps)
import { ref, watch, computed } from 'vue'
import { useTabStore } from '@/stores/tab'
import { getColumns, getIndexes } from '@/api/database'
import type { Column } from '@/api/database'

const tabStore = useTabStore()

interface Idx { name?: string; columns?: string; is_unique?: boolean }
const cols = ref<Column[]>([])
const idxs = ref<Idx[]>([])
const loading = ref(false)

const cur = computed(() => tabStore.current)

watch(cur, async (v) => {
  cols.value = []; idxs.value = []
  if (!v) return
  loading.value = true
  try {
    const [c, i] = await Promise.all([
      getColumns(v.s, v.t),
      getIndexes(v.s, v.t).catch(() => [] as Idx[]),
    ])
    cols.value = c
    idxs.value = i as Idx[]
  } catch { /* 无权限等 */ }
  finally { loading.value = false }
}, { immediate: true })
</script>

<template>
  <aside class="props-panel" v-if="cur">
    <div class="p-head">属性</div>
    <div class="p-body">
      <div class="p-item"><label>对象</label><span>{{ cur.t }}</span></div>
      <div class="p-item"><label>Schema</label><span>{{ cur.s || '-' }}</span></div>
      <div class="p-item"><label>数据库</label><span>{{ tabStore.activeTab?.db || '-' }}</span></div>

      <div v-if="loading" class="empty2" style="padding:10px;font-size:12px">加载中...</div>
      <template v-else>
        <div class="p-sec">字段 ({{ cols.length }})</div>
        <table class="p-tbl">
          <thead><tr><th>名</th><th>类型</th><th>可空</th><th>键</th></tr></thead>
          <tbody>
            <tr v-for="c in cols" :key="c.name">
              <td>{{ c.name }}</td><td>{{ c.type || '' }}</td>
              <td>{{ c.nullable ? '是' : '否' }}</td><td>{{ c.is_pk ? 'PK' : '' }}</td>
            </tr>
          </tbody>
        </table>
        <template v-if="idxs.length">
          <div class="p-sec">索引 ({{ idxs.length }})</div>
          <table class="p-tbl">
            <thead><tr><th>名</th><th>字段</th><th>唯一</th></tr></thead>
            <tbody>
              <tr v-for="i in idxs" :key="i.name">
                <td>{{ i.name }}</td><td>{{ i.columns }}</td><td>{{ i.is_unique ? '是' : '' }}</td>
              </tr>
            </tbody>
          </table>
        </template>
      </template>
    </div>
  </aside>
</template>

<style scoped>
.props-panel { width: 240px; flex-shrink: 0; border-left: 1px solid var(--border, var(--border)); display: flex; flex-direction: column; min-height: 0; }
.p-head { padding: 6px 10px; font-weight: 600; font-size: 13px; border-bottom: 1px solid var(--border, var(--border)); }
.p-body { flex: 1; overflow: auto; padding: 8px; }
.p-item { display: flex; justify-content: space-between; gap: 8px; padding: 3px 0; font-size: 13px; }
.p-item label { color: var(--text2, var(--text3)); }
.p-item span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.p-sec { margin: 10px 0 4px; font-size: 12px; color: var(--text2, var(--text3)); font-weight: 600; }
.p-tbl { width: 100%; border-collapse: collapse; font-size: 12px; }
.p-tbl th, .p-tbl td { padding: 3px 4px; border-bottom: 1px solid var(--border, #eee); text-align: left; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.p-tbl th { color: var(--text3, var(--text3)); font-weight: 500; }
.empty2 { color: var(--text3, var(--text3)); font-size: 12px; }
</style>
